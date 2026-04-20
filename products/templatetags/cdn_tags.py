from django import template

register = template.Library()

@register.filter
def cdn_url(url, width=600):
    if not url or '/upload/' not in url:
        return url
    return url.replace('/upload/', f'/upload/f_auto,q_auto,w_{width},c_limit/')