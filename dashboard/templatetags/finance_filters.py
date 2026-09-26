from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def co_currency(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    if amount == amount.to_integral_value():
        formatted = f'{int(amount):,}'.replace(',', '.')
        return f'${formatted} COP'
    formatted = f'{amount:,.2f}'
    formatted = formatted.replace(',', '@').replace('.', ',').replace('@', '.')
    return f'${formatted} COP'


@register.filter
def co_grams(value):
    try:
        grams = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    if grams == grams.to_integral_value():
        formatted = f'{int(grams):,}'.replace(',', '.')
    else:
        formatted = f'{grams:,.3f}'.rstrip('0').rstrip('.')
        formatted = formatted.replace(',', '@').replace('.', ',').replace('@', '.')
    return f'{formatted} g'


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
