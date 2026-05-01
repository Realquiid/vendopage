"""
sellers/geo_currency.py

Detects the visitor's country from their IP address using ipapi.co (free, no key needed).
Falls back to the seller's stored currency if detection fails.

Usage in views:
    from sellers.geo_currency import detect_currency

    def cart_view(request, slug):
        seller = ...
        currency = detect_currency(request, seller)
        return render(request, 'store/cart.html', {'currency': currency['symbol'], ...})
"""

import requests
import logging

logger = logging.getLogger(__name__)

# ── Complete country → currency mapping ──────────────────────────────────────
# Format: 'ISO_COUNTRY_CODE': {'code': 'CURRENCY_CODE', 'symbol': 'SYMBOL', 'name': 'Currency Name'}

COUNTRY_CURRENCY_MAP = {
    # ── Africa ───────────────────────────────────────────────────────────
    'NG': {'code': 'NGN', 'symbol': '₦',  'name': 'Nigerian Naira'},
    'GH': {'code': 'GHS', 'symbol': 'GH₵','name': 'Ghanaian Cedi'},
    'KE': {'code': 'KES', 'symbol': 'KSh','name': 'Kenyan Shilling'},
    'ZA': {'code': 'ZAR', 'symbol': 'R',  'name': 'South African Rand'},
    'EG': {'code': 'EGP', 'symbol': '£',  'name': 'Egyptian Pound'},
    'ET': {'code': 'ETB', 'symbol': 'Br', 'name': 'Ethiopian Birr'},
    'TZ': {'code': 'TZS', 'symbol': 'TSh','name': 'Tanzanian Shilling'},
    'UG': {'code': 'UGX', 'symbol': 'USh','name': 'Ugandan Shilling'},
    'RW': {'code': 'RWF', 'symbol': 'Fr', 'name': 'Rwandan Franc'},
    'ZM': {'code': 'ZMW', 'symbol': 'ZK', 'name': 'Zambian Kwacha'},
    'ZW': {'code': 'ZWL', 'symbol': 'Z$', 'name': 'Zimbabwean Dollar'},
    'CM': {'code': 'XAF', 'symbol': 'Fr', 'name': 'Central African CFA Franc'},
    'CI': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'SN': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'ML': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'BF': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'NE': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'TD': {'code': 'XAF', 'symbol': 'Fr', 'name': 'Central African CFA Franc'},
    'GA': {'code': 'XAF', 'symbol': 'Fr', 'name': 'Central African CFA Franc'},
    'CG': {'code': 'XAF', 'symbol': 'Fr', 'name': 'Central African CFA Franc'},
    'CD': {'code': 'CDF', 'symbol': 'Fr', 'name': 'Congolese Franc'},
    'AO': {'code': 'AOA', 'symbol': 'Kz', 'name': 'Angolan Kwanza'},
    'MZ': {'code': 'MZN', 'symbol': 'MT', 'name': 'Mozambican Metical'},
    'MG': {'code': 'MGA', 'symbol': 'Ar', 'name': 'Malagasy Ariary'},
    'MU': {'code': 'MUR', 'symbol': '₨', 'name': 'Mauritian Rupee'},
    'SD': {'code': 'SDG', 'symbol': 'ج.س','name': 'Sudanese Pound'},
    'SS': {'code': 'SSP', 'symbol': '£',  'name': 'South Sudanese Pound'},
    'SO': {'code': 'SOS', 'symbol': 'Sh', 'name': 'Somali Shilling'},
    'ER': {'code': 'ERN', 'symbol': 'Nfk','name': 'Eritrean Nakfa'},
    'DJ': {'code': 'DJF', 'symbol': 'Fr', 'name': 'Djiboutian Franc'},
    'BJ': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'TG': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'GN': {'code': 'GNF', 'symbol': 'Fr', 'name': 'Guinean Franc'},
    'GW': {'code': 'XOF', 'symbol': 'Fr', 'name': 'West African CFA Franc'},
    'SL': {'code': 'SLL', 'symbol': 'Le', 'name': 'Sierra Leonean Leone'},
    'LR': {'code': 'LRD', 'symbol': '$',  'name': 'Liberian Dollar'},
    'MR': {'code': 'MRU', 'symbol': 'UM', 'name': 'Mauritanian Ouguiya'},
    'GM': {'code': 'GMD', 'symbol': 'D',  'name': 'Gambian Dalasi'},
    'CV': {'code': 'CVE', 'symbol': '$',  'name': 'Cape Verdean Escudo'},
    'ST': {'code': 'STN', 'symbol': 'Db', 'name': 'São Tomé and Príncipe Dobra'},
    'GQ': {'code': 'XAF', 'symbol': 'Fr', 'name': 'Central African CFA Franc'},
    'CF': {'code': 'XAF', 'symbol': 'Fr', 'name': 'Central African CFA Franc'},
    'BI': {'code': 'BIF', 'symbol': 'Fr', 'name': 'Burundian Franc'},
    'KM': {'code': 'KMF', 'symbol': 'Fr', 'name': 'Comorian Franc'},
    'MW': {'code': 'MWK', 'symbol': 'MK', 'name': 'Malawian Kwacha'},
    'BW': {'code': 'BWP', 'symbol': 'P',  'name': 'Botswana Pula'},
    'NA': {'code': 'NAD', 'symbol': '$',  'name': 'Namibian Dollar'},
    'SZ': {'code': 'SZL', 'symbol': 'L',  'name': 'Swazi Lilangeni'},
    'LS': {'code': 'LSL', 'symbol': 'L',  'name': 'Lesotho Loti'},
    'LY': {'code': 'LYD', 'symbol': 'ل.د','name': 'Libyan Dinar'},
    'TN': {'code': 'TND', 'symbol': 'د.ت','name': 'Tunisian Dinar'},
    'DZ': {'code': 'DZD', 'symbol': 'دج', 'name': 'Algerian Dinar'},
    'MA': {'code': 'MAD', 'symbol': 'د.م.','name': 'Moroccan Dirham'},

    # ── Europe ───────────────────────────────────────────────────────────
    'GB': {'code': 'GBP', 'symbol': '£',  'name': 'British Pound'},
    'DE': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'FR': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'IT': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'ES': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'PT': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'NL': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'BE': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'AT': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'IE': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'FI': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'GR': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'SE': {'code': 'SEK', 'symbol': 'kr', 'name': 'Swedish Krona'},
    'NO': {'code': 'NOK', 'symbol': 'kr', 'name': 'Norwegian Krone'},
    'DK': {'code': 'DKK', 'symbol': 'kr', 'name': 'Danish Krone'},
    'CH': {'code': 'CHF', 'symbol': 'Fr', 'name': 'Swiss Franc'},
    'PL': {'code': 'PLN', 'symbol': 'zł', 'name': 'Polish Zloty'},
    'CZ': {'code': 'CZK', 'symbol': 'Kč', 'name': 'Czech Koruna'},
    'HU': {'code': 'HUF', 'symbol': 'Ft', 'name': 'Hungarian Forint'},
    'RO': {'code': 'RON', 'symbol': 'lei','name': 'Romanian Leu'},
    'BG': {'code': 'BGN', 'symbol': 'лв', 'name': 'Bulgarian Lev'},
    'HR': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'SK': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'SI': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'LT': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'LV': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'EE': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'RU': {'code': 'RUB', 'symbol': '₽',  'name': 'Russian Ruble'},
    'UA': {'code': 'UAH', 'symbol': '₴',  'name': 'Ukrainian Hryvnia'},
    'TR': {'code': 'TRY', 'symbol': '₺',  'name': 'Turkish Lira'},
    'RS': {'code': 'RSD', 'symbol': 'din','name': 'Serbian Dinar'},
    'AL': {'code': 'ALL', 'symbol': 'L',  'name': 'Albanian Lek'},
    'MK': {'code': 'MKD', 'symbol': 'ден','name': 'Macedonian Denar'},
    'BA': {'code': 'BAM', 'symbol': 'KM', 'name': 'Bosnia-Herzegovina Convertible Mark'},
    'ME': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},
    'XK': {'code': 'EUR', 'symbol': '€',  'name': 'Euro'},

    # ── Americas ─────────────────────────────────────────────────────────
    'US': {'code': 'USD', 'symbol': '$',  'name': 'US Dollar'},
    'CA': {'code': 'CAD', 'symbol': 'CA$','name': 'Canadian Dollar'},
    'MX': {'code': 'MXN', 'symbol': '$',  'name': 'Mexican Peso'},
    'BR': {'code': 'BRL', 'symbol': 'R$', 'name': 'Brazilian Real'},
    'AR': {'code': 'ARS', 'symbol': '$',  'name': 'Argentine Peso'},
    'CL': {'code': 'CLP', 'symbol': '$',  'name': 'Chilean Peso'},
    'CO': {'code': 'COP', 'symbol': '$',  'name': 'Colombian Peso'},
    'PE': {'code': 'PEN', 'symbol': 'S/', 'name': 'Peruvian Sol'},
    'VE': {'code': 'VES', 'symbol': 'Bs.S','name': 'Venezuelan Bolívar'},
    'EC': {'code': 'USD', 'symbol': '$',  'name': 'US Dollar'},
    'BO': {'code': 'BOB', 'symbol': 'Bs', 'name': 'Bolivian Boliviano'},
    'PY': {'code': 'PYG', 'symbol': '₲',  'name': 'Paraguayan Guaraní'},
    'UY': {'code': 'UYU', 'symbol': '$',  'name': 'Uruguayan Peso'},
    'GY': {'code': 'GYD', 'symbol': '$',  'name': 'Guyanese Dollar'},
    'SR': {'code': 'SRD', 'symbol': '$',  'name': 'Surinamese Dollar'},
    'JM': {'code': 'JMD', 'symbol': '$',  'name': 'Jamaican Dollar'},
    'TT': {'code': 'TTD', 'symbol': '$',  'name': 'Trinidad and Tobago Dollar'},
    'BB': {'code': 'BBD', 'symbol': '$',  'name': 'Barbadian Dollar'},
    'BS': {'code': 'BSD', 'symbol': '$',  'name': 'Bahamian Dollar'},
    'HT': {'code': 'HTG', 'symbol': 'G',  'name': 'Haitian Gourde'},
    'CU': {'code': 'CUP', 'symbol': '$',  'name': 'Cuban Peso'},
    'DO': {'code': 'DOP', 'symbol': 'RD$','name': 'Dominican Peso'},
    'GT': {'code': 'GTQ', 'symbol': 'Q',  'name': 'Guatemalan Quetzal'},
    'HN': {'code': 'HNL', 'symbol': 'L',  'name': 'Honduran Lempira'},
    'SV': {'code': 'USD', 'symbol': '$',  'name': 'US Dollar'},
    'NI': {'code': 'NIO', 'symbol': 'C$', 'name': 'Nicaraguan Córdoba'},
    'CR': {'code': 'CRC', 'symbol': '₡',  'name': 'Costa Rican Colón'},
    'PA': {'code': 'PAB', 'symbol': 'B/.','name': 'Panamanian Balboa'},

    # ── Middle East ──────────────────────────────────────────────────────
    'SA': {'code': 'SAR', 'symbol': '﷼',  'name': 'Saudi Riyal'},
    'AE': {'code': 'AED', 'symbol': 'د.إ','name': 'UAE Dirham'},
    'QA': {'code': 'QAR', 'symbol': '﷼',  'name': 'Qatari Riyal'},
    'KW': {'code': 'KWD', 'symbol': 'د.ك','name': 'Kuwaiti Dinar'},
    'BH': {'code': 'BHD', 'symbol': '.د.ب','name': 'Bahraini Dinar'},
    'OM': {'code': 'OMR', 'symbol': '﷼',  'name': 'Omani Rial'},
    'IL': {'code': 'ILS', 'symbol': '₪',  'name': 'Israeli Shekel'},
    'JO': {'code': 'JOD', 'symbol': 'د.ا','name': 'Jordanian Dinar'},
    'LB': {'code': 'LBP', 'symbol': '£',  'name': 'Lebanese Pound'},
    'IQ': {'code': 'IQD', 'symbol': 'ع.د','name': 'Iraqi Dinar'},
    'IR': {'code': 'IRR', 'symbol': '﷼',  'name': 'Iranian Rial'},
    'YE': {'code': 'YER', 'symbol': '﷼',  'name': 'Yemeni Rial'},
    'SY': {'code': 'SYP', 'symbol': '£',  'name': 'Syrian Pound'},

    # ── Asia ─────────────────────────────────────────────────────────────
    'CN': {'code': 'CNY', 'symbol': '¥',  'name': 'Chinese Yuan'},
    'JP': {'code': 'JPY', 'symbol': '¥',  'name': 'Japanese Yen'},
    'KR': {'code': 'KRW', 'symbol': '₩',  'name': 'South Korean Won'},
    'IN': {'code': 'INR', 'symbol': '₹',  'name': 'Indian Rupee'},
    'PK': {'code': 'PKR', 'symbol': '₨',  'name': 'Pakistani Rupee'},
    'BD': {'code': 'BDT', 'symbol': '৳',  'name': 'Bangladeshi Taka'},
    'LK': {'code': 'LKR', 'symbol': '₨',  'name': 'Sri Lankan Rupee'},
    'NP': {'code': 'NPR', 'symbol': '₨',  'name': 'Nepalese Rupee'},
    'MM': {'code': 'MMK', 'symbol': 'K',  'name': 'Myanmar Kyat'},
    'TH': {'code': 'THB', 'symbol': '฿',  'name': 'Thai Baht'},
    'VN': {'code': 'VND', 'symbol': '₫',  'name': 'Vietnamese Dong'},
    'ID': {'code': 'IDR', 'symbol': 'Rp', 'name': 'Indonesian Rupiah'},
    'MY': {'code': 'MYR', 'symbol': 'RM', 'name': 'Malaysian Ringgit'},
    'PH': {'code': 'PHP', 'symbol': '₱',  'name': 'Philippine Peso'},
    'SG': {'code': 'SGD', 'symbol': 'S$', 'name': 'Singapore Dollar'},
    'HK': {'code': 'HKD', 'symbol': 'HK$','name': 'Hong Kong Dollar'},
    'TW': {'code': 'TWD', 'symbol': 'NT$','name': 'New Taiwan Dollar'},
    'MN': {'code': 'MNT', 'symbol': '₮',  'name': 'Mongolian Tögrög'},
    'KH': {'code': 'KHR', 'symbol': '៛',  'name': 'Cambodian Riel'},
    'LA': {'code': 'LAK', 'symbol': '₭',  'name': 'Lao Kip'},
    'AF': {'code': 'AFN', 'symbol': '؋',  'name': 'Afghan Afghani'},
    'UZ': {'code': 'UZS', 'symbol': 'лв', 'name': 'Uzbekistani Som'},
    'KZ': {'code': 'KZT', 'symbol': '₸',  'name': 'Kazakhstani Tenge'},
    'AZ': {'code': 'AZN', 'symbol': '₼',  'name': 'Azerbaijani Manat'},
    'GE': {'code': 'GEL', 'symbol': '₾',  'name': 'Georgian Lari'},
    'AM': {'code': 'AMD', 'symbol': '֏',  'name': 'Armenian Dram'},

    # ── Oceania ──────────────────────────────────────────────────────────
    'AU': {'code': 'AUD', 'symbol': 'A$', 'name': 'Australian Dollar'},
    'NZ': {'code': 'NZD', 'symbol': 'NZ$','name': 'New Zealand Dollar'},
    'FJ': {'code': 'FJD', 'symbol': '$',  'name': 'Fijian Dollar'},
    'PG': {'code': 'PGK', 'symbol': 'K',  'name': 'Papua New Guinean Kina'},
    'TO': {'code': 'TOP', 'symbol': 'T$', 'name': 'Tongan Paʻanga'},
    'WS': {'code': 'WST', 'symbol': 'T',  'name': 'Samoan Tālā'},
}

# ── Default / fallback ───────────────────────────────────────────────────────
DEFAULT_CURRENCY = {'code': 'USD', 'symbol': '$', 'name': 'US Dollar'}


def get_client_ip(request) -> str:
    """Extract real IP, handling proxies and Cloudflare."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def lookup_country_from_ip(ip: str) -> str | None:
    """
    Returns ISO country code from IP via ipapi.co (free, 1k req/day no key).
    Returns None on failure.
    """
    if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
        return None
    try:
        r = requests.get(
            f'https://ipapi.co/{ip}/country/',
            timeout=2,
            headers={'User-Agent': 'VendoPage/1.0'},
        )
        if r.status_code == 200:
            country = r.text.strip().upper()
            if len(country) == 2 and country.isalpha():
                return country
    except Exception as e:
        logger.debug(f"IP lookup failed for {ip}: {e}")
    return None


def detect_currency(request, seller=None) -> dict:
    """
    Main entry point. Call this in cart/checkout views.

    Priority:
      1. User manually chose a currency (stored in session)
      2. IP-based geolocation
      3. Seller's stored currency_code
      4. USD fallback

    Returns:
        {'code': 'NGN', 'symbol': '₦', 'name': 'Nigerian Naira'}
    """
    # 1. Session override (user picked manually)
    session_currency = request.session.get('selected_currency')
    if session_currency and session_currency in {v['code'] for v in COUNTRY_CURRENCY_MAP.values()}:
        for c in COUNTRY_CURRENCY_MAP.values():
            if c['code'] == session_currency:
                return c

    # 2. IP lookup
    ip      = get_client_ip(request)
    country = lookup_country_from_ip(ip)
    if country and country in COUNTRY_CURRENCY_MAP:
        return COUNTRY_CURRENCY_MAP[country]

    # 3. Seller's stored currency
    if seller and seller.currency_code:
        for c in COUNTRY_CURRENCY_MAP.values():
            if c['code'] == seller.currency_code.upper():
                return c

    # 4. Fallback
    return DEFAULT_CURRENCY


def get_all_currencies() -> list[dict]:
    """
    Returns a deduplicated list of all currencies for a currency picker dropdown.
    Sorted alphabetically by name.
    """
    seen_codes = set()
    result = []
    for c in COUNTRY_CURRENCY_MAP.values():
        if c['code'] not in seen_codes:
            seen_codes.add(c['code'])
            result.append(c)
    return sorted(result, key=lambda x: x['name'])