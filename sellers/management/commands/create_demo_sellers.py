"""
Management command: create_demo_sellers
=======================================
Creates two realistic demo seller accounts with products and orders.

Place at: sellers/management/commands/create_demo_sellers.py

Usage:
    python manage.py create_demo_sellers
    python manage.py create_demo_sellers --reset
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from decimal import Decimal
from datetime import timedelta
import random
import uuid

from sellers.models import Seller, VendorBankAccount, Order, OrderItem
from products.models import Product, ProductImage


# ── COUTURE COLLECTION — 15 Men's Fashion Products ──────────────────────────
COUTURE_PRODUCTS = [
    {'name': 'Slim Fit Oxford Button-Down Shirt',        'price': Decimal('18500')},
    {'name': 'Premium Slim-Cut Chinos — Stone',          'price': Decimal('22000')},
    {'name': 'Luxury Chronograph Watch — Silver',        'price': Decimal('95000')},
    {'name': 'Stretch Denim Jeans — Midnight Blue',      'price': Decimal('27500')},
    {'name': 'Italian Linen Polo Shirt — White',         'price': Decimal('15000')},
    {'name': 'Plain Tapered Trousers — Charcoal Grey',   'price': Decimal('19500')},
    {'name': 'Classic Crew-Neck Knit Sweater — Navy',    'price': Decimal('24000')},
    {'name': 'Minimalist Leather Strap Watch — Black',   'price': Decimal('58000')},
    {'name': 'Structured Blazer — Dark Navy',            'price': Decimal('65000')},
    {'name': 'Straight-Cut Plain Joggers — Olive',       'price': Decimal('12500')},
    {'name': 'Graphic Print Oversized Tee',              'price': Decimal('9500')},
    {'name': 'Cotton Henley Long-Sleeve Top — Grey',     'price': Decimal('13000')},
    {'name': 'Stretch Denim Jeans — Classic Black',      'price': Decimal('29500')},
    {'name': 'Luxury Rose Gold Dress Watch',             'price': Decimal('112000')},
    {'name': 'Formal Plain Trousers — Ash Grey',         'price': Decimal('17500')},
]

# ── PEAKFORM SPORTS — 12 Sportswear Products ─────────────────────────────────
PEAKFORM_PRODUCTS = [
    {'name': 'Pro-Dry Training Jersey — Black',          'price': Decimal('14500')},
    {'name': 'Compression Gym Shorts — Navy',            'price': Decimal('11000')},
    {'name': 'Lightweight Running Trainers — White',     'price': Decimal('42000')},
    {'name': 'Moisture-Wicking Gym T-Shirt — Grey',      'price': Decimal('8500')},
    {'name': 'Slim-Fit Track Joggers — Black',           'price': Decimal('16000')},
    {'name': 'Insulated Sports Water Bottle 1L',         'price': Decimal('7500')},
    {'name': 'Full-Zip Performance Hoodie — Charcoal',   'price': Decimal('32000')},
    {'name': 'Football Training Shorts — Green',         'price': Decimal('9000')},
    {'name': 'Woven Windbreaker Jacket — Navy',          'price': Decimal('38000')},
    {'name': 'Padded Gym Gloves — Black',                'price': Decimal('6500')},
    {'name': 'Pro Basketball Socks 3-Pack',              'price': Decimal('4500')},
    {'name': 'Adjustable Sports Cap — Black',            'price': Decimal('5500')},
]

# ── Nigerian buyer names & details ───────────────────────────────────────────
BUYERS = [
    ('Emeka Okafor',      'emeka.okafor@gmail.com',      '08012345678'),
    ('Chioma Nwosu',      'chioma.nwosu@yahoo.com',      '08023456789'),
    ('Tunde Adeleke',     'tunde.adeleke@gmail.com',     '08034567890'),
    ('Amaka Eze',         'amaka.eze@outlook.com',       '08045678901'),
    ('Seun Adebayo',      'seun.adebayo@gmail.com',      '08056789012'),
    ('Ngozi Obi',         'ngozi.obi@yahoo.com',         '08067890123'),
    ('Chidi Nnamdi',      'chidi.nnamdi@gmail.com',      '08078901234'),
    ('Funmilayo Bello',   'funmi.bello@gmail.com',       '08089012345'),
    ('Rotimi Fashola',    'rotimi.f@hotmail.com',        '08090123456'),
    ('Adaeze Chukwu',     'adaeze.c@gmail.com',          '08001234567'),
    ('Kelechi Ibe',       'kelechi.ibe@gmail.com',       '08112345678'),
    ('Yetunde Afolabi',   'yetunde.a@yahoo.com',         '08123456789'),
    ('Ifeanyi Onuoha',    'ifeanyi.o@gmail.com',         '08134567890'),
    ('Bimpe Coker',       'bimpe.coker@gmail.com',       '08145678901'),
    ('Obinna Dike',       'obinna.dike@outlook.com',     '08156789012'),
    ('Sade Olawale',      'sade.olawale@gmail.com',      '08167890123'),
    ('Damilola Akin',     'damilola.a@gmail.com',        '08178901234'),
    ('Precious Onyeka',   'precious.o@yahoo.com',        '08189012345'),
    ('Tobi Lawson',       'tobi.lawson@gmail.com',       '08190123456'),
    ('Chiamaka Uche',     'chiamaka.u@gmail.com',        '08101234567'),
    ('Biodun Oladele',    'biodun.o@gmail.com',          '08021234567'),
    ('Nkechi Anozie',     'nkechi.a@yahoo.com',          '08032345678'),
    ('Gbenga Martins',    'gbenga.m@gmail.com',          '08043456789'),
    ('Zainab Usman',      'zainab.u@gmail.com',          '08054567890'),
    ('Chukwuemeka Obi',   'chukwuemeka.o@gmail.com',     '08065678901'),
]

ADDRESSES = [
    ('14 Broad Street, Lagos Island',           'Lagos'),
    ('7 Adetokunbo Ademola Street, VI',         'Lagos'),
    ('22 Allen Avenue, Ikeja',                  'Lagos'),
    ('5 Okonjo-Iweala Way, Wuse 2',             'Abuja'),
    ('31 Agodi Gate Road',                      'Ibadan'),
    ('10 Rumuola Road',                         'Port Harcourt'),
    ('3 Ogui Road',                             'Enugu'),
    ('18 Sapele Road',                          'Benin City'),
    ('9 Zaria Road',                            'Kaduna'),
    ('45 Aba Road',                             'Port Harcourt'),
    ('12 Bode Thomas Street, Surulere',         'Lagos'),
    ('8 Ikorodu Road, Maryland',                'Lagos'),
    ('20 Ahmadu Bello Way',                     'Abuja'),
    ('6 Trans-Amadi Industrial Layout',         'Port Harcourt'),
    ('33 New Market Road',                      'Onitsha'),
]

COURIERS = [
    'GIG Logistics', 'DHL Nigeria', 'Kwik Delivery',
    'Sendbox', 'Jumia Logistics', 'RedStar Express',
    'Kobo360', 'Pathfinder Logistics',
]


def get_buyer(idx):
    b = BUYERS[idx % len(BUYERS)]
    a = ADDRESSES[idx % len(ADDRESSES)]
    return {
        'name':    b[0],
        'email':   b[1],
        'phone':   b[2],
        'address': a[0],
        'city':    a[1],
    }


def make_tx_ref():
    return f"VDP-ORD-{uuid.uuid4().hex[:12].upper()}"


def make_flw_id():
    return str(random.randint(4000000, 9999999))


def make_order(seller, buyer, prod, qty, status, created_at, **kwargs):
    order = Order(
        seller=seller,
        flutterwave_tx_ref=make_tx_ref(),
        flutterwave_tx_id=make_flw_id(),
        buyer_name=buyer['name'],
        buyer_email=buyer['email'],
        buyer_phone=buyer['phone'],
        delivery_address=buyer['address'],
        delivery_city=buyer['city'],
        subtotal=prod['price'] * qty,
        currency='NGN',
        payment_type='escrow',
        payment_verified=True,
        created_at=created_at,
        status=status,
        **kwargs,
    )
    order.calculate_fees()
    order.save()

    OrderItem.objects.create(
        order=order,
        product_id=prod['id'],
        product_name=prod['name'],
        product_image_url='',
        price=prod['price'],
        quantity=qty,
    )
    return order


class Command(BaseCommand):
    help = 'Creates two demo seller accounts with products and realistic orders'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing demo sellers and recreate',
        )

    def handle(self, *args, **options):
        if options['reset']:
            for slug in ['couture-collection', 'peakform-sports']:
                try:
                    Seller.objects.get(slug=slug).delete()
                    self.stdout.write(f'  Deleted: {slug}')
                except Seller.DoesNotExist:
                    pass

        self._create_seller(
            business_name='Couture Collections',
            username='couturecollection',
            email='couture.collection.ng@gmail.com',
            whatsapp='2348012345678',
            slug='couture-collection',
            category='fashion',
            bio='Premium menswear for the modern Nigerian man. We stock the finest shirts, trousers, jeans, and luxury watches. Quality you can feel.',
            products_data=COUTURE_PRODUCTS,
        )

        self._create_seller(
            business_name='PeakForm Sports',
            username='peakformsports',
            email='peakform.sports.ng@gmail.com',
            whatsapp='2348098765432',
            slug='peakform-sports',
            category='sports',
            bio='Your go-to store for premium sportswear and fitness gear in Nigeria. From gym to field, we keep you performing at your peak.',
            products_data=PEAKFORM_PRODUCTS,
        )

        self.stdout.write(self.style.SUCCESS('\n✅ Done!'))
        self.stdout.write('   Couture Collections → vendopage.com/couture-collections')
        self.stdout.write('   PeakForm Sports    → vendopage.com/peakform-sports')
        self.stdout.write('   Password for both  → DemoSeller2024!')

    def _create_seller(self, business_name, username, email,
                       whatsapp, slug, category, bio, products_data):

        self.stdout.write(f'\nCreating {business_name}...')

        if Seller.objects.filter(email=email).exists():
            self.stdout.write('  Already exists — skipping.')
            return

        # ── Seller ───────────────────────────────────────────────────────
        seller = Seller(
            username=username,
            email=email,
            business_name=business_name,
            whatsapp_number=whatsapp,
            slug=slug,
            category=category,
            bio=bio,
            currency_code='NGN',
            currency_symbol='₦',
            country_code='+234',
            store_mode=True,
            store_mode_enabled_at=timezone.now() - timedelta(days=120),
            is_active=True,
            email_verified=True,
            subscription_type='premium',
            subscription_tier='growth',
            subscription_expires=timezone.now() + timedelta(days=300),
            is_featured=True,
            total_page_views=random.randint(2400, 5800),
            weekly_page_views=random.randint(180, 420),
            weekly_whatsapp_clicks=random.randint(60, 160),
            monthly_volume_processed=Decimal(str(random.randint(600000, 1800000))),
            last_analytics_reset=timezone.now() - timedelta(days=2),
            watermark_enabled=True,
            password=make_password('DemoSeller2024!'),
        )
        seller.save()
        self.stdout.write(f'  ✓ Seller created: @{username}')

        # ── Bank account ─────────────────────────────────────────────────
        VendorBankAccount.objects.create(
            seller=seller,
            account_number='0123456789',
            bank_name='Guaranty Trust Bank (GTB)',
            bank_code='058',
            account_name=business_name,
            is_verified=True,
        )
        self.stdout.write('  ✓ Bank account added')

        # ── Products ──────────────────────────────────────────────────────
        products = []
        for p_data in products_data:
            product = Product.objects.create(
                seller=seller,
                name=p_data['name'],
                description=p_data['name'],
                price=p_data['price'],
                views=random.randint(60, 800),
                whatsapp_clicks=random.randint(8, 90),
            )
            products.append({
                'id':    product.id,
                'name':  p_data['name'],
                'price': p_data['price'],
            })

        self.stdout.write(f'  ✓ {len(products)} products created')

        # ── Orders ───────────────────────────────────────────────────────
        buyer_idx = 0

        # 1. COMPLETED — paid out (15 orders) ─────────────────────────────
        for i in range(15):
            buyer    = get_buyer(buyer_idx); buyer_idx += 1
            days_ago = random.randint(4, 100)
            created  = timezone.now() - timedelta(days=days_ago)
            paid_at  = created + timedelta(hours=random.randint(1, 4))
            shipped  = paid_at + timedelta(hours=random.randint(10, 30))
            delivered = shipped + timedelta(hours=random.randint(24, 60))
            payout_at = delivered + timedelta(hours=random.randint(14, 28))
            prod     = random.choice(products)
            qty      = random.randint(1, 3)

            make_order(
                seller=seller, buyer=buyer, prod=prod, qty=qty,
                status='completed', created_at=created,
                paid_at=paid_at, shipped_at=shipped,
                delivered_at=delivered, payout_triggered=True,
                payout_at=payout_at,
                flutterwave_transfer_id=make_flw_id(),
                tracking_info=f"GIG{random.randint(100000,999999)}",
                courier_name=random.choice(COURIERS),
            )

        self.stdout.write('  ✓ 15 completed/paid-out orders')

        # 2. RECEIVED — buyer confirmed, payout next business day (4 orders)
        for i in range(4):
            buyer    = get_buyer(buyer_idx); buyer_idx += 1
            created  = timezone.now() - timedelta(days=random.randint(1, 3))
            paid_at  = created + timedelta(hours=2)
            shipped  = paid_at + timedelta(hours=random.randint(10, 20))
            delivered = shipped + timedelta(hours=random.randint(18, 32))
            prod     = random.choice(products)

            make_order(
                seller=seller, buyer=buyer, prod=prod, qty=1,
                status='RECEIVED', created_at=created,
                paid_at=paid_at, shipped_at=shipped,
                delivered_at=delivered, payout_triggered=False,
                tracking_info=f"GIG{random.randint(100000,999999)}",
                courier_name=random.choice(COURIERS),
            )

        self.stdout.write('  ✓ 4 RECEIVED orders (payout pending)')

        # 3. SHIPPED — in transit (3 orders) ──────────────────────────────
        for i in range(3):
            buyer   = get_buyer(buyer_idx); buyer_idx += 1
            created = timezone.now() - timedelta(days=random.randint(1, 3))
            paid_at = created + timedelta(hours=2)
            shipped = paid_at + timedelta(hours=random.randint(8, 24))
            prod    = random.choice(products)

            make_order(
                seller=seller, buyer=buyer, prod=prod,
                qty=random.randint(1, 2),
                status='shipped', created_at=created,
                paid_at=paid_at, shipped_at=shipped,
                payout_triggered=False,
                tracking_info=f"GIG{random.randint(100000,999999)}",
                courier_name=random.choice(COURIERS),
            )

        self.stdout.write('  ✓ 3 shipped orders')

        # 4. PAID — awaiting shipment (2 orders) ──────────────────────────
        for i in range(2):
            buyer   = get_buyer(buyer_idx); buyer_idx += 1
            created = timezone.now() - timedelta(hours=random.randint(2, 18))
            paid_at = created + timedelta(hours=1)
            prod    = random.choice(products)

            make_order(
                seller=seller, buyer=buyer, prod=prod,
                qty=random.randint(1, 2),
                status='paid', created_at=created,
                paid_at=paid_at, payout_triggered=False,
            )

        self.stdout.write('  ✓ 2 in-escrow (just paid) orders')

        # 5. REFUNDED (3 orders) ───────────────────────────────────────────
        for i in range(3):
            buyer    = get_buyer(buyer_idx); buyer_idx += 1
            days_ago = random.randint(8, 50)
            created  = timezone.now() - timedelta(days=days_ago)
            paid_at  = created + timedelta(hours=1)
            prod     = random.choice(products)

            make_order(
                seller=seller, buyer=buyer, prod=prod, qty=1,
                status='refunded', created_at=created,
                paid_at=paid_at, payout_triggered=False,
                is_disputed=False,
                refund_initiated_at=paid_at + timedelta(days=random.randint(2, 6)),
            )

        self.stdout.write('  ✓ 3 refunded orders')

        # 6. FAILED PAYOUT — retrying (1 order) ───────────────────────────
        buyer    = get_buyer(buyer_idx); buyer_idx += 1
        created  = timezone.now() - timedelta(days=2)
        paid_at  = created + timedelta(hours=1)
        shipped  = paid_at + timedelta(hours=14)
        delivered = shipped + timedelta(hours=26)
        prod     = random.choice(products)

        make_order(
            seller=seller, buyer=buyer, prod=prod, qty=1,
            status='FAILED_PAYOUT', created_at=created,
            paid_at=paid_at, shipped_at=shipped,
            delivered_at=delivered, payout_triggered=False,
            tracking_info=f"GIG{random.randint(100000,999999)}",
            courier_name=random.choice(COURIERS),
        )

        self.stdout.write('  ✓ 1 failed payout order')

        total = Order.objects.filter(seller=seller).count()
        self.stdout.write(f'  ✓ Total: {total} orders for {business_name}')