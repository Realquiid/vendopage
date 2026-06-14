from django.http import HttpResponsePermanentRedirect
from django.utils import timezone

# config/middleware.py
class RedirectToWWWMiddleware:
    """
    Redirect vendopage.com to www.vendopage.com
    Makes www.vendopage.com the primary domain
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        host = request.get_host().lower()
        
        # Only redirect in production
        if host == 'vendopage.com':
            # Redirect non-www → www
            new_url = request.build_absolute_uri().replace(
                '://vendopage.com',
                '://www.vendopage.com',
                1
            )
            return HttpResponsePermanentRedirect(new_url)
        
        return self.get_response(request)
    
class LastSeenMiddleware:
    """
    Updates seller.last_seen on every authenticated request.
    Throttled to once every 5 minutes to avoid a DB write on every click.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            now = timezone.now()
            last = getattr(request.user, 'last_seen', None)

            if last is None or (now - last).total_seconds() > 300:
                from sellers.models import Seller
                Seller.objects.filter(pk=request.user.pk).update(last_seen=now)
                request.user.last_seen = now

        return response