"""
management/commands/process_payouts.py

VendoPage Daily Escrow Payout — Flutterwave (NGN)
==================================================

Payout Logic
────────────
1. Query Flutterwave /v3/balances/NGN for available (spendable) balance
2. Fetch ALL orders where:
      - status = 'RECEIVED'           (buyer explicitly clicked "I received my product")
      - delivered_at < today midnight  (confirmed before end of yesterday — T+1 cleared)
      - payout_triggered = False
   Sorted by delivered_at ASC — 3 PM order paid before 4 PM order, fair queue
3. Walk the queue oldest-first:
      - Running balance check: if remaining spendable < this order's vendor_payout → SKIP (carry to tomorrow)
      - Send vendor_payout via Flutterwave Transfer API (already net of 5% — stored at checkout)
      - On success → status='completed', payout_triggered=True
      - On gateway error → status='FAILED_PAYOUT' (retries tomorrow)
4. The 5% platform fee NEVER moves — it already sits in our Flutterwave balance
   as accumulated revenue. The cron ONLY sends order.vendor_payout, nothing more.

Key rule: if buyer has NOT clicked received, the order is NEVER paid out,
even if 24h have passed. No auto-assumptions.

Usage
─────
  python manage.py process_payouts            # live run
  python manage.py process_payouts --dry-run  # simulate, zero API calls

Settings required
─────────────────
  FLUTTERWAVE_SECRET_KEY  (already in your codebase)
"""

import logging
from datetime import time as dt_time
from decimal import Decimal

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from sellers.flutterwave import FlutterwavePayment
from sellers.models import Order

logger = logging.getLogger(__name__)
CURRENCY = "NGN"


class Command(BaseCommand):
    help = (
        "Daily escrow payout. Pays all sellers whose buyers clicked 'received' "
        "before midnight yesterday, oldest delivery confirmation first, "
        "until Flutterwave balance is exhausted. Never re-deducts the 5%% fee."
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

        flw = FlutterwavePayment()

        # ── Build the eligible queue ───────────────────────────────────────────
        # Midnight at the start of today (WAT / server local time)
        # Any buyer who clicked "received" before midnight yesterday is eligible.
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        eligible = (
            Order.objects
            .filter(
                status="RECEIVED",              # buyer MUST have clicked received
                delivered_at__lt=today_midnight, # confirmed before midnight yesterday
                payout_triggered=False,
            )
            .select_related("seller", "seller__bank_account")
            .order_by("delivered_at")           # 3 PM before 4 PM — time-fair queue
        )

        # Also include FAILED_PAYOUT orders (gateway failures from a previous run)
        # so they retry today — same time-priority ordering
        failed_retry = (
            Order.objects
            .filter(
                status="FAILED_PAYOUT",
                delivered_at__lt=today_midnight,
                payout_triggered=False,
            )
            .select_related("seller", "seller__bank_account")
            .order_by("delivered_at")
        )

        # Combine: process fresh RECEIVED first (in time order),
        # then retries (also in time order). Both sorted by delivered_at.
        from itertools import chain
        queue = sorted(
            chain(eligible, failed_retry),
            key=lambda o: o.delivered_at or now,
        )

        if not queue:
            self.stdout.write(self.style.SUCCESS(
                "\n  No eligible orders in the payout queue.\n"
                "  (Only orders where the buyer has clicked 'I received my product'\n"
                "   before midnight yesterday are processed.)\n"
                "  Exiting cleanly.\n"
            ))
            return

        # Total owed = sum of vendor_payout across queue
        # This is ALREADY net of 5% (stored by calculate_fees() at checkout).
        # We DO NOT subtract 5% again here — that would double-charge the seller.
        total_owed = sum(o.vendor_payout for o in queue)

        self.stdout.write(
            f"\n  Orders in queue      : {len(queue)}\n"
            f"  Total owed to sellers: ₦{total_owed:,.2f}  (5% already retained at checkout)\n"
            f"  Cutoff               : buyer confirmed before {today_midnight.strftime('%d %b %Y 00:00')}\n"
        )

        # ── Safety Layer 1: Flutterwave balance check ──────────────────────────
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  [DRY RUN] Skipping live balance check — assuming sufficient funds.\n"
            ))
            spendable = total_owed
        else:
            self.stdout.write("  Checking Flutterwave spendable balance …")
            spendable = self._get_balance(flw)
            self.stdout.write(
                f"  Flutterwave balance  : ₦{spendable:,.2f}\n"
            )

        if spendable <= Decimal("0"):
            self._abort("Flutterwave balance is ₦0. No payouts possible today. "
                        "All orders remain in queue for tomorrow.")
            return

        if spendable < total_owed:
            self.stdout.write(self.style.WARNING(
                f"  ⚠  Balance (₦{spendable:,.2f}) is less than total owed "
                f"(₦{total_owed:,.2f}).\n"
                f"     Will pay oldest-first until balance is exhausted.\n"
                f"     Unpaid orders remain in queue — they run first tomorrow.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Balance covers full queue. Processing all {len(queue)} orders.\n"
            ))

        # ── Payout loop — oldest delivered_at first ────────────────────────────
        remaining_balance = spendable
        success_count  = 0
        skipped_count  = 0   # balance ran out mid-queue
        failure_count  = 0   # gateway errors

        self.stdout.write(f"  {'─'*60}")

        for order in queue:
            seller_amount = order.vendor_payout   # already net of 5% — DO NOT touch
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

            # Balance check per order — skip if we can't cover this one
            if remaining_balance < seller_amount:
                self.stdout.write(self.style.WARNING(
                    f"  ⏭  SKIPPED — remaining balance ₦{remaining_balance:,.2f} "
                    f"cannot cover ₦{seller_amount:,.2f}. "
                    f"Will pay tomorrow."
                ))
                logger.warning(
                    "PAYOUT SKIPPED (balance exhausted) | order=%s | seller=%s | "
                    "needed=₦%s | remaining=₦%s",
                    ref_short, order.seller.business_name,
                    seller_amount, remaining_balance,
                )
                skipped_count += 1
                # Don't change order status — stays RECEIVED, retries tomorrow
                continue

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  [DRY RUN] Would transfer ₦{seller_amount:,.2f} to "
                    f"{order.seller.business_name} — skipped."
                ))
                remaining_balance -= seller_amount
                success_count += 1
                continue

            # ── Execute transfer ───────────────────────────────────────────────
            ok = self._execute_transfer(order, flw)
            if ok:
                remaining_balance -= seller_amount
                success_count += 1
            else:
                failure_count += 1
                # Note: we do NOT deduct from remaining_balance on failure
                # because the money never left our account

        # ── Summary ────────────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'='*64}\n"
            f"  {label}PAYOUT RUN COMPLETE\n"
            f"  Paid out    : {success_count} order(s)\n"
            f"  Skipped     : {skipped_count} order(s)  (balance exhausted — retry tomorrow)\n"
            f"  Failed      : {failure_count} order(s)  (gateway error — retry tomorrow)\n"
            f"  Balance left: ₦{remaining_balance:,.2f}  (includes your 5% revenue)\n"
            f"{'='*64}\n"
        ))

        if skipped_count or failure_count:
            logger.warning(
                "PAYOUT RUN | success=%d | skipped=%d | failed=%d | "
                "remaining_balance=₦%s",
                success_count, skipped_count, failure_count, remaining_balance,
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
        """
        Sends order.vendor_payout to the seller.
        vendor_payout = subtotal - 5% fee  (calculated once at checkout, stored on order).
        We transfer this exact amount. The 5% never moves — it stays in our balance.
        Returns True on success, False on any error.
        """
        ref_short = str(order.order_ref)[:8].upper()

        try:
            with transaction.atomic():
                result = flw.transfer_to_vendor(order)

                if result.get("status") != "success":
                    raise ValueError(
                        f"Flutterwave returned non-success: {result}"
                    )

                order.payout_triggered        = True
                order.payout_at               = timezone.now()
                order.status                  = "completed"
                order.flutterwave_transfer_id = str(
                    result.get("data", {}).get("id", "")
                )
                order.save(update_fields=[
                    "payout_triggered",
                    "payout_at",
                    "status",
                    "flutterwave_transfer_id",
                ])

            self.stdout.write(self.style.SUCCESS(
                f"  ✅ Paid — FLW transfer id: {order.flutterwave_transfer_id}"
            ))
            logger.info(
                "PAYOUT SUCCESS | order=%s | seller=%s | amount=₦%s | "
                "confirmed_at=%s | transfer_id=%s",
                ref_short,
                order.seller.business_name,
                order.vendor_payout,
                order.delivered_at,
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
                f"  ❌ Transfer failed — marked FAILED_PAYOUT (retries tomorrow). "
                f"Error: {exc}"
            ))
            return False

    def _abort(self, reason: str):
        logger.warning("PAYOUT ABORTED — %s", reason)
        self.stdout.write(self.style.ERROR(f"\n  ⚠  ABORT: {reason}\n"))