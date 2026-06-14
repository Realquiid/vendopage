from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Seller

class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return [
            'home',
            'register',
            'login',
            'sellers_directory',
            'about',
            'privacy',
            'terms',
            'contact',
            'faq',
        ]

    def location(self, item):
        return reverse(item)


class SellerSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9

    def items(self):
        return Seller.objects.filter(email_verified=True)

    def location(self, obj):
        return f'/{obj.slug}/'