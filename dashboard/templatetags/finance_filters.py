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


@register.filter
def month_name_es(value):
    """Given a month number (1-12) or numeric string, return the Spanish month name capitalized."""
    month_names = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    try:
        m = int(value)
    except (ValueError, TypeError):
        return value
    if 1 <= m <= 12:
        return month_names[m - 1].capitalize()
    return value
