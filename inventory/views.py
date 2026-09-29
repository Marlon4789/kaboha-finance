from django.shortcuts import render

from .models import InventoryEntry
from .services import InventoryService
from products.models import Product


def inventory_list(request):
    entries = InventoryEntry.objects.order_by('-date', '-created_at')
    stock_rows = [
        {
            'product': product,
            'quantity': InventoryService.get_stock(product),
        }
        for product in Product.objects.filter(is_stock_tracked=True).order_by('name')
    ]

    context = {
        'historical_entries': entries,
        'stock_rows': stock_rows,
    }
    return render(request, 'inventory/list.html', context)
