from django import template

register = template.Library()

@register.filter
def status_color(status):
    color_map = {
        'pending': 'warning',
        'processing': 'info',
        'shipped': 'primary',
        'out_for_delivery': 'success',
        'delivered': 'secondary',
        'cancelled': 'danger'
    }
    return color_map.get(status.lower(), 'secondary')

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return '' 