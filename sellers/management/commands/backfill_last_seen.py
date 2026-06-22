# sellers/management/commands/backfill_last_seen.py
from django.core.management.base import BaseCommand
from django.db.models import F
from sellers.models import Seller


class Command(BaseCommand):
    help = "Backfill last_seen using each seller's real last_login date, falling back to created_at only if they've never logged in."

    def handle(self, *args, **options):
        # Sellers who've logged in before — use their actual last_login timestamp
        from_login = Seller.objects.filter(
            last_seen__isnull=True,
            last_login__isnull=False,
        ).update(last_seen=F('last_login'))

        # Sellers who registered but never logged back in — fall back to created_at
        from_created = Seller.objects.filter(
            last_seen__isnull=True,
            last_login__isnull=True,
        ).update(last_seen=F('created_at'))

        self.stdout.write(self.style.SUCCESS(
            f"✅ Backfilled {from_login} seller(s) from last_login, "
            f"{from_created} from created_at (never logged in since signup)."
        ))
        