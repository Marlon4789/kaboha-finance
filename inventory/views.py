from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum, F, FloatField
from django.utils import timezone

from .models import InventoryEntry
from .forms import InventoryEntryForm
from sales.models import SaleItem


def inventory_list(request):
    today = timezone.localdate()
    first_day_month = today.replace(day=1)

    entries = InventoryEntry.objects.order_by('-date', '-created_at')
    totals = InventoryEntry.objects.aggregate(
        total_bags=Sum('bags_added'),
        total_kilos=Sum('kilos_added'),
    )
    monthly_totals = InventoryEntry.objects.filter(date__gte=first_day_month).aggregate(
        month_bags=Sum('bags_added'),
        month_kilos=Sum('kilos_added'),
    )

    sold_totals = SaleItem.objects.aggregate(
        sold_bags=Sum('quantity'),
        sold_kilos=Sum(F('quantity') * F('product__weight_grams') / 1000.0, output_field=FloatField()),
    )
    sold_monthly = SaleItem.objects.filter(sale__sale_date__gte=first_day_month).aggregate(
        sold_bags=Sum('quantity'),
        sold_kilos=Sum(F('quantity') * F('product__weight_grams') / 1000.0, output_field=FloatField()),
    )

    total_bags = totals['total_bags'] or 0
    total_kilos = totals['total_kilos'] or 0
    sold_bags_total = sold_totals['sold_bags'] or 0
    sold_kilos_total = sold_totals['sold_kilos'] or 0
    month_bags = monthly_totals['month_bags'] or 0
    month_kilos = monthly_totals['month_kilos'] or 0
    sold_bags_month = sold_monthly['sold_bags'] or 0
    sold_kilos_month = sold_monthly['sold_kilos'] or 0

    stock_bags = total_bags - sold_bags_total
    stock_kilos = total_kilos - sold_kilos_total

    context = {
        'entries': entries,
        'total_bags': total_bags,
        'total_kilos': total_kilos,
        'sold_bags_total': sold_bags_total,
        'sold_kilos_total': sold_kilos_total,
        'month_bags': month_bags,
        'month_kilos': month_kilos,
        'sold_bags_month': sold_bags_month,
        'sold_kilos_month': sold_kilos_month,
        'stock_bags': stock_bags,
        'stock_kilos': stock_kilos,
    }
    return render(request, 'inventory/list.html', context)


def inventory_create(request):
    if request.method == 'POST':
        form = InventoryEntryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(reverse('inventory_list'))
    else:
        form = InventoryEntryForm()
    return render(request, 'inventory/form.html', {'form': form, 'title': 'Nueva entrada de inventario'})


def inventory_edit(request, pk):
    entry = get_object_or_404(InventoryEntry, pk=pk)
    if request.method == 'POST':
        form = InventoryEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            return redirect(reverse('inventory_list'))
    else:
        form = InventoryEntryForm(instance=entry)
    return render(request, 'inventory/form.html', {'form': form, 'title': 'Editar entrada de inventario'})


def inventory_delete(request, pk):
    entry = get_object_or_404(InventoryEntry, pk=pk)
    if request.method == 'POST':
        entry.delete()
        return redirect(reverse('inventory_list'))
    return render(request, 'confirm_delete.html', {
        'object_name': f'Inventario {entry.date}',
        'cancel_url': reverse('inventory_list'),
    })
