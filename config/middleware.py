from django.http import HttpResponsePermanentRedirect

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