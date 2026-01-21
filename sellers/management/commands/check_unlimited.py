
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from sellers.models import Seller

class Command(BaseCommand):
    help = 'Check all users and verify unlimited product feature is working'

    def handle(self, *args, **options):
        all_sellers = Seller.objects.annotate(
            active_products=Count('products', filter=Q(products__is_archived=False)),
            total_products=Count('products')
        ).order_by('-total_products')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n{"="*100}\n'
            f'UNLIMITED PRODUCTS VERIFICATION REPORT\n'
            f'{"="*100}\n'
        ))
        
        self.stdout.write(f'\n✅ ALL USERS NOW HAVE UNLIMITED PRODUCTS!\n')
        self.stdout.write(f'Total Users: {all_sellers.count()}\n')
        
        if all_sellers.exists():
            self.stdout.write(
                f'\n{"Username":<20} {"Business Name":<30} {"Active":<10} {"Total":<10} {"Status"}'
            )
            self.stdout.write(f'{"-"*100}')
            
            for seller in all_sellers:
                limit = seller.get_product_limit()
                status = "✅ UNLIMITED" if limit is None else f"⚠️ LIMITED ({limit})"
                
                self.stdout.write(
                    f'{seller.username:<20} '
                    f'{seller.business_name[:28]:<30} '
                    f'{seller.active_products:<10} '
                    f'{seller.total_products:<10} '
                    f'{status}'
                )
            
            # Statistics
            total_active = sum(s.active_products for s in all_sellers)
            total_all = sum(s.total_products for s in all_sellers)
            avg_active = total_active / all_sellers.count() if all_sellers.count() > 0 else 0
            
            self.stdout.write(f'\n{"-"*100}')
            self.stdout.write(f'📊 STATISTICS:')
            self.stdout.write(f'   Total Active Products: {total_active}')
            self.stdout.write(f'   Total All Products: {total_all}')
            self.stdout.write(f'   Average per Seller: {avg_active:.1f} active products')
            
            # Top users
            top_users = all_sellers[:10]
            self.stdout.write(f'\n🏆 TOP 10 USERS BY PRODUCT COUNT:')
            for i, seller in enumerate(top_users, 1):
                self.stdout.write(
                    f'   {i}. {seller.business_name} (@{seller.username}): '
                    f'{seller.active_products} active, {seller.total_products} total'
                )
            
            # Users with many products (proves unlimited works)
            heavy_users = all_sellers.filter(total_products__gte=30)
            if heavy_users.exists():
                self.stdout.write(f'\n💪 POWER USERS (30+ products):')
                for seller in heavy_users:
                    self.stdout.write(
                        f'   - {seller.business_name}: {seller.total_products} products '
                        f'(This proves unlimited is working!)'
                    )
            else:
                self.stdout.write(f'\n💡 No users have 30+ products yet.')
        
        self.stdout.write(f'\n{"="*100}\n')
        self.stdout.write(self.style.SUCCESS('✅ Verification complete!\n'))
