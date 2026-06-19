
"""
management/commands/process_payouts.py

VendoPage Daily Escrow Payout — Flutterwave (NGN)
==================================================

Payout Logic
────────────
1. Weekend guard: exits immediately on Saturday/Sunday — FLW doesn't settle
   on weekends so our balance may only contain our own 5% revenue, not buyer funds.
2. Query Flutterwave /v3/balances/NGN for available (spendable) balance
3. Fetch ALL orders where:
      - status = 'RECEIVED'           (buyer explicitly clicked "I received my product")
      - delivered_at < today midnight  (confirmed before end of yesterday — T+1 cleared)
      - payout_triggered = False
      - is_disputed = False            ← BRAKE: disputed orders are NEVER paid out by cron
   Sorted by delivered_at ASC — 3 PM order paid before 4 PM order, fair queue
4. Walk the queue oldest-first:
      - Running balance check: if remaining spendable < this order's vendor_payout → SKIP
      - Send vendor_payout via Flutterwave Transfer API (already net of 5% — stored at checkout)
      - On success → status='completed', payout_triggered=True
      - On gateway error → status='FAILED_PAYOUT' (retries tomorrow)
5. The 5% platform fee NEVER moves — it already sits in our Flutterwave balance
   as accumulated revenue. The cron ONLY sends order.vendor_payout, nothing more.

Key rules:
  - Never runs on Saturday or Sunday (FLW weekend settlement gap).
  - Monday 6AM pays everyone queued from Friday + Saturday + Sunday at once.
  - If buyer has NOT clicked received, the order is NEVER paid out.
  - If is_disputed=True, the order is NEVER paid out by cron.

Telegram notifications:
  - On every live (non-dry-run) run, a summary is sent to the founder's Telegram
    via TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (set in .env).

Usage
─────
  python manage.py process_payouts            # live run
  python manage.py process_payouts --dry-run  # simulate, zero API calls
"""

import logging
from decimal import Decimal
from itertools import chain

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from sellers.flutterwave import FlutterwavePayment
from sellers.models import Order
from sellers.telegram import notify_telegram

logger = logging.getLogger(__name__)
CURRENCY = "NGN"


class Command(BaseCommand):
    help = (
        "Daily escrow payout. Skips weekends (FLW settlement gap). "
        "Pays all sellers whose buyers clicked 'received' before midnight yesterday, "
        "oldest-first, until balance is exhausted. Never re-deducts the 5%% fee. "
        "Disputed orders are completely skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate — no API calls, no DB writes.",
        )

    # ── Entry point ────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        label = "[DRY RUN] " if dry_run else ""
        now   = timezone.now()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'='*64}\n"
            f"  {label}VENDOPAGE DAILY PAYOUT — {now.strftime('%A %d %B %Y, %I:%M %p')}\n"
            f"{'='*64}"
        ))

        # ── Weekend guard ──────────────────────────────────────────────────────
        if now.weekday() in (5, 6) and not dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n  ⏸  WEEKEND SKIP — today is {now.strftime('%A')}.\n"
                f"     Flutterwave does not settle payments on Sat/Sun.\n"
                f"     All queued orders will be paid on Monday 6 AM.\n"
                f"     No DB changes made.\n"
            ))
            logger.info(
                "PAYOUT SKIPPED — weekend (%s). "
                "FLW settlement resumes Monday. Orders stay in queue.",
                now.strftime('%A'),
            )
            return

        flw = FlutterwavePayment()

        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── Build payout queue (disputed orders excluded) ──────────────────────
        eligible = (
            Order.objects
            .filter(
                status="RECEIVED",
                delivered_at__lt=today_midnight,
                payout_triggered=False,
                is_disputed=False,
            )
            .select_related("seller", "seller__bank_account")
            .order_by("delivered_at")
        )

        failed_retry = (
            Order.objects
            .filter(
                status="FAILED_PAYOUT",
                delivered_at__lt=today_midnight,
                payout_triggered=False,
                is_disputed=False,
            )
            .select_related("seller", "seller__bank_account")
            .order_by("delivered_at")
        )

        disputed_count = Order.objects.filter(
            status__in=["RECEIVED", "FAILED_PAYOUT"],
            delivered_at__lt=today_midnight,
            payout_triggered=False,
            is_disputed=True,
        ).count()

        if disputed_count:
            self.stdout.write(self.style.WARNING(
                f"\n  ⚠  {disputed_count} disputed order(s) in queue — "
                f"SKIPPED (money locked until admin resolves).\n"
            ))
            logger.warning(
                "PAYOUT CRON: %d disputed order(s) skipped — locked pending admin resolution.",
                disputed_count,
            )

        queue = sorted(
            chain(eligible, failed_retry),
            key=lambda o: o.delivered_at or now,
        )

        if not queue:
            self.stdout.write(self.style.SUCCESS(
                "\n  No eligible orders in the payout queue.\n"
                "  (Only orders where the buyer clicked 'I received my product'\n"
                "   before midnight yesterday AND have no active dispute are processed.)\n"
                "  Exiting cleanly.\n"
            ))
            return

        total_owed = sum(o.vendor_payout for o in queue)

        self.stdout.write(
            f"\n  Orders in queue      : {len(queue)}\n"
            f"  Total owed to sellers: ₦{total_owed:,.2f}  (5% already retained at checkout)\n"
            f"  Cutoff               : buyer confirmed before {today_midnight.strftime('%d %b %Y 00:00')}\n"
        )

        # ── Flutterwave balance check ──────────────────────────────────────────
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  [DRY RUN] Skipping live balance check — assuming sufficient funds.\n"
            ))
            spendable = total_owed
        else:
            self.stdout.write("  Checking Flutterwave spendable balance …\n")
            spendable = self._get_balance(flw)
            self.stdout.write(f"  Flutterwave balance  : ₦{spendable:,.2f}\n")

        if spendable <= Decimal("0"):
            self._abort(
                "Flutterwave balance is ₦0. No payouts possible today. "
                "All orders remain in queue for tomorrow."
            )
            if not dry_run:
                notify_telegram(
                    "⚠️ <b>Vendopage Payout Run</b>\n"
                    f"{now.strftime('%a %d %b, %I:%M %p')}\n\n"
                    "Balance is ₦0 — no payouts possible today.\n"
                    f"{len(queue)} order(s) still queued, total owed ₦{total_owed:,.2f}"
                )
            return

        if spendable < total_owed:
            self.stdout.write(self.style.WARNING(
                f"  ⚠  Balance (₦{spendable:,.2f}) is less than total owed "
                f"(₦{total_owed:,.2f}).\n"
                f"     Will pay oldest-first until balance is exhausted.\n"
                f"     Remaining orders retry tomorrow.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Balance covers full queue. Processing all {len(queue)} orders.\n"
            ))

        # ── Payout loop ────────────────────────────────────────────────────────
        remaining_balance = spendable
        success_count  = 0
        skipped_count  = 0
        failure_count  = 0

        self.stdout.write(f"  {'─'*60}")

        for order in queue:
            seller_amount = order.vendor_payout
            ref_short     = str(order.order_ref)[:8].upper()
            confirmed_at  = (
                order.delivered_at.strftime("%d %b %Y %I:%M %p")
                if order.delivered_at else "unknown"
            )

            self.stdout.write(
                f"\n  Order #{ref_short} | "
                f"Seller: {order.seller.business_name}\n"
                f"  Buyer confirmed: {confirmed_at} | "
                f"Payout: ₦{seller_amount:,.2f}"
            )

            if remaining_balance < seller_amount:
                self.stdout.write(self.style.WARNING(
                    f"  ⏭  SKIPPED — remaining balance ₦{remaining_balance:,.2f} "
                    f"cannot cover ₦{seller_amount:,.2f}. Will pay tomorrow."
                ))
                logger.warning(
                    "PAYOUT SKIPPED (balance exhausted) | order=%s | seller=%s | "
                    "needed=₦%s | remaining=₦%s",
                    ref_short, order.seller.business_name,
                    seller_amount, remaining_balance,
                )
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  [DRY RUN] Would transfer ₦{seller_amount:,.2f} to "
                    f"{order.seller.business_name} — skipped."
                ))
                remaining_balance -= seller_amount
                success_count += 1
                continue

            ok = self._execute_transfer(order, flw)
            if ok:
                remaining_balance -= seller_amount
                success_count += 1
            else:
                failure_count += 1

        # ── Summary ────────────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'='*64}\n"
            f"  {label}PAYOUT RUN COMPLETE\n"
            f"  Paid out    : {success_count} order(s)\n"
            f"  Skipped     : {skipped_count} order(s)  (balance exhausted — retry tomorrow)\n"
            f"  Failed      : {failure_count} order(s)  (gateway error — retry tomorrow)\n"
            f"  Disputed    : {disputed_count} order(s)  (locked — awaiting admin decision)\n"
            f"  Balance left: ₦{remaining_balance:,.2f}  (includes your 5% revenue)\n"
            f"{'='*64}\n"
        ))

        if skipped_count or failure_count:
            logger.warning(
                "PAYOUT RUN | success=%d | skipped=%d | failed=%d | disputed=%d | "
                "remaining_balance=₦%s",
                success_count, skipped_count, failure_count, disputed_count, remaining_balance,
            )

        if not dry_run:
            emoji = "✅" if (success_count and not failure_count and not skipped_count) else (
                "⚠️" if skipped_count or failure_count else "ℹ️"
            )
            notify_telegram(
                f"{emoji} <b>Vendopage Payout Run</b>\n"
                f"{now.strftime('%a %d %b, %I:%M %p')}\n\n"
                f"Paid: {success_count} | Skipped: {skipped_count} | Failed: {failure_count}\n"
                f"Disputed (locked): {disputed_count}\n"
                f"Balance left: ₦{remaining_balance:,.2f}"
            )

    # ── Flutterwave balance ────────────────────────────────────────────────────
    def _get_balance(self, flw: FlutterwavePayment) -> Decimal:
        try:
            resp = requests.get(
                f"{flw.BASE_URL}/balances/{CURRENCY}",
                headers=flw._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException as exc:
            raise CommandError(
                f"[BALANCE CHECK] Flutterwave balance API unreachable: {exc}"
            ) from exc

        if body.get("status") != "success":
            raise CommandError(f"[BALANCE CHECK] Unexpected response: {body}")

        available = body.get("data", {}).get("available_balance", 0)
        return Decimal(str(available))

    # ── Single order transfer ──────────────────────────────────────────────────
    def _execute_transfer(self, order: Order, flw: FlutterwavePayment) -> bool:
        ref_short = str(order.order_ref)[:8].upper()


        # Flutterwave minimum transfer is ₦100
        if order.vendor_payout < Decimal("100.00"):
            self.stdout.write(self.style.WARNING(
                f"  ⏭  SKIPPED — vendor_payout ₦{order.vendor_payout} is below "
                f"Flutterwave's ₦100 minimum. Marking completed to clear queue."
            ))
            logger.warning(
                "PAYOUT BELOW MINIMUM | order=%s | amount=₦%s — marking completed",
                ref_short, order.vendor_payout,
            )
            order.payout_triggered = True
            order.payout_at = timezone.now()
            order.status = "completed"
            order.save(update_fields=["payout_triggered", "payout_at", "status"])
            return True  # don't retry — it will never pass ₦100 minimum

        try:
            with transaction.atomic():
                result = flw.transfer_to_vendor(order)

                if result.get("status") != "success":
                    raise ValueError(f"Flutterwave returned non-success: {result}")

                order.payout_triggered        = True
                order.payout_at               = timezone.now()
                order.status                  = "completed"
                order.flutterwave_transfer_id = str(
                    result.get("data", {}).get("id", "")
                )
                order.save(update_fields=[
                    "payout_triggered", "payout_at",
                    "status", "flutterwave_transfer_id",
                ])

            self.stdout.write(self.style.SUCCESS(
                f"  ✅ Paid — FLW transfer id: {order.flutterwave_transfer_id}"
            ))
            logger.info(
                "PAYOUT SUCCESS | order=%s | seller=%s | amount=₦%s | "
                "confirmed_at=%s | transfer_id=%s",
                ref_short, order.seller.business_name,
                order.vendor_payout, order.delivered_at,
                order.flutterwave_transfer_id,
            )
            return True

        except (requests.RequestException, ValueError, Exception) as exc:
            logger.error(
                "PAYOUT FAILED | order=%s | seller=%s | error=%s",
                ref_short, order.seller.business_name, exc,
                exc_info=True,
            )
            order.status = "FAILED_PAYOUT"
            order.save(update_fields=["status"])
            self.stdout.write(self.style.ERROR(
                f"  ❌ Transfer failed — marked FAILED_PAYOUT. Error: {exc}"
            ))
            return False

    def _abort(self, reason: str):
        logger.warning("PAYOUT ABORTED — %s", reason)
        self.stdout.write(self.style.ERROR(f"\n  ⚠  ABORT: {reason}\n"))
