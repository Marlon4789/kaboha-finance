from django import template

register = template.Library()


@register.filter
def co_currency(value):
    try:
        amount = int(value)
    except (ValueError, TypeError):
        return value
    formatted = f"${amount:,.0f} COP".replace(',', '.')
    return formatted


@register.filter
def co_grams(value):
    try:
        grams = int(value)
    except (ValueError, TypeError):
        return value
    return f'{grams:,}'.replace(',', '.') + ' g'


@register.filter
def co_kilos(value):
    try:
        kilos = float(value)
    except (ValueError, TypeError):
        return value
    return f'{kilos:,.2f}'.replace(',', '.') + ' kg'
