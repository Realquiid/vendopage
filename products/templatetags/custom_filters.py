from django import template
register = template.Library()
 
@register.filter
def dict_get(d, key):
    """Usage: {{ my_dict|dict_get:variable_key }}"""
    if isinstance(d, dict):
        return d.get(key, 0)
    return 0



@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)