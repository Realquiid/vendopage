
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import Lower
from sellers.models import Seller

class Command(BaseCommand):
    help = 'Fix duplicate emails, usernames, and phone numbers before migration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n🔧 FIXING DUPLICATE DATA\n'))
        
        # Fix duplicate emails
        self.fix_duplicate_emails()
        
        # Fix duplicate usernames
        self.fix_duplicate_usernames()
        
        # Fix duplicate phone numbers
        self.fix_duplicate_phones()
        
        # Normalize existing emails to lowercase
        self.normalize_emails()
        
        self.stdout.write(self.style.SUCCESS('\n✅ All duplicates fixed! Now run: python manage.py migrate\n'))
    
    def fix_duplicate_emails(self):
        self.stdout.write('\n📧 Checking for duplicate emails...')
        
        # Find duplicate emails (case-insensitive)
        duplicates = Seller.objects.values(
            lower_email=Lower('email')
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        if not duplicates:
            self.stdout.write(self.style.SUCCESS('   ✅ No duplicate emails found'))
            return
        
        self.stdout.write(self.style.WARNING(f'   Found {len(duplicates)} duplicate email groups'))
        
        for dup in duplicates:
            email_lower = dup['lower_email']
            sellers = Seller.objects.filter(email__iexact=email_lower).order_by('id')
            
            # Keep the first one, modify others
            first = sellers.first()
            others = sellers[1:]
            
            self.stdout.write(f'\n   Email: {email_lower} (found {sellers.count()} times)')
            self.stdout.write(f'   ✓ Keeping: {first.username} (ID: {first.id})')
            
            for i, seller in enumerate(others, 1):
                # Change email to make it unique
                new_email = f"{email_lower.split('@')[0]}_duplicate{i}@{email_lower.split('@')[1]}"
                old_email = seller.email
                seller.email = new_email
                seller.save()
                self.stdout.write(f'   → Changed: {seller.username} (ID: {seller.id})')
                self.stdout.write(f'     {old_email} → {new_email}')
    
    def fix_duplicate_usernames(self):
        self.stdout.write('\n👤 Checking for duplicate usernames...')
        
        # Find duplicate usernames (case-insensitive)
        duplicates = Seller.objects.values(
            lower_username=Lower('username')
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        if not duplicates:
            self.stdout.write(self.style.SUCCESS('   ✅ No duplicate usernames found'))
            return
        
        self.stdout.write(self.style.WARNING(f'   Found {len(duplicates)} duplicate username groups'))
        
        for dup in duplicates:
            username_lower = dup['lower_username']
            sellers = Seller.objects.filter(username__iexact=username_lower).order_by('id')
            
            # Keep the first one, modify others
            first = sellers.first()
            others = sellers[1:]
            
            self.stdout.write(f'\n   Username: {username_lower} (found {sellers.count()} times)')
            self.stdout.write(f'   ✓ Keeping: {first.username} (ID: {first.id})')
            
            for i, seller in enumerate(others, 1):
                # Change username to make it unique
                new_username = f"{username_lower}_{i}"
                counter = 1
                while Seller.objects.filter(username=new_username).exists():
                    new_username = f"{username_lower}_{i}_{counter}"
                    counter += 1
                
                old_username = seller.username
                seller.username = new_username
                seller.save()
                self.stdout.write(f'   → Changed: ID {seller.id}')
                self.stdout.write(f'     {old_username} → {new_username}')
    
    def fix_duplicate_phones(self):
        self.stdout.write('\n📱 Checking for duplicate phone numbers...')
        
        # Find duplicate phone numbers
        duplicates = Seller.objects.values('whatsapp_number').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        if not duplicates:
            self.stdout.write(self.style.SUCCESS('   ✅ No duplicate phone numbers found'))
            return
        
        self.stdout.write(self.style.WARNING(f'   Found {len(duplicates)} duplicate phone groups'))
        
        for dup in duplicates:
            phone = dup['whatsapp_number']
            sellers = Seller.objects.filter(whatsapp_number=phone).order_by('id')
            
            # Keep the first one, modify others
            first = sellers.first()
            others = sellers[1:]
            
            self.stdout.write(f'\n   Phone: {phone} (found {sellers.count()} times)')
            self.stdout.write(f'   ✓ Keeping: {first.username} (ID: {first.id})')
            
            for i, seller in enumerate(others, 1):
                # Change phone to make it unique (add suffix)
                new_phone = f"{phone}_{i}"
                old_phone = seller.whatsapp_number
                seller.whatsapp_number = new_phone
                seller.save()
                self.stdout.write(f'   → Changed: {seller.username} (ID: {seller.id})')
                self.stdout.write(f'     {old_phone} → {new_phone}')
                self.stdout.write(self.style.WARNING(f'     ⚠️  User needs to update their phone number!'))
    
    def normalize_emails(self):
        self.stdout.write('\n🔄 Normalizing all emails to lowercase...')
        
        sellers_to_update = []
        for seller in Seller.objects.all():
            if seller.email != seller.email.lower():
                seller.email = seller.email.lower()
                sellers_to_update.append(seller)
        
        if sellers_to_update:
            Seller.objects.bulk_update(sellers_to_update, ['email'])
            self.stdout.write(self.style.SUCCESS(f'   ✅ Normalized {len(sellers_to_update)} emails'))
        else:
            self.stdout.write(self.style.SUCCESS('   ✅ All emails already lowercase'))

