import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Sale
from .forms import SaleCreateForm, SaleForm, SaleItemFormSet
from .services import SalesOperationError, SalesService
from inventory.services import InventoryOperationError


def sale_list(request):
    sales = Sale.objects.order_by('-sale_date')
    return render(request, 'sales/list.html', {'sales': sales})


def sale_create(request):
    sale = Sale()
    if request.method == 'POST':
        form = SaleCreateForm(request.POST)
        formset = SaleItemFormSet(request.POST, instance=sale)
        if form.is_valid() and formset.is_valid():
            lines = [
                {
                    'product': item_form.cleaned_data['product'],
                    'quantity': item_form.cleaned_data['quantity'],
                    'unit_price': item_form.cleaned_data['unit_price'],
                }
                for item_form in formset.forms
                if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False)
                and item_form.cleaned_data.get('product')
            ]
            try:
                sale, created = SalesService.create_integrated_sale(
                    form.cleaned_data, lines,
                    operation_key=form.cleaned_data['operation_key'],
                    actor=request.user if request.user.is_authenticated else None,
                )
            except (SalesOperationError, InventoryOperationError) as exc:
                form.add_error(None, str(exc))
            else:
                message = 'Venta registrada e inventario actualizado.' if created else 'Esta venta ya había sido registrada.'
                messages.success(request, message)
                return redirect(reverse('sale_list'))
    else:
        form = SaleCreateForm(initial={'operation_key': uuid.uuid4()})
        formset = SaleItemFormSet(instance=sale)
    return render(request, 'sales/form.html', {'form': form, 'formset': formset, 'title': 'Nueva venta'})


def sale_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if sale.has_inventory_movements():
        messages.error(request, 'Esta venta ya afectó inventario y no puede modificarse.')
        return redirect(reverse('sale_list'))
    if request.method == 'POST':
        form = SaleForm(request.POST, instance=sale)
        formset = SaleItemFormSet(request.POST, instance=sale)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect(reverse('sale_list'))
    else:
        form = SaleForm(instance=sale)
        formset = SaleItemFormSet(instance=sale)
    return render(request, 'sales/form.html', {'form': form, 'formset': formset, 'title': 'Editar venta'})


def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if sale.has_inventory_movements():
        messages.error(request, 'Esta venta ya afectó inventario y no puede eliminarse.')
        return redirect(reverse('sale_list'))
    if request.method == 'POST':
        try:
            sale.delete()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return redirect(reverse('sale_list'))
        return redirect(reverse('sale_list'))
    return render(request, 'confirm_delete.html', {
        'object_name': f'Venta {sale.id}',
        'cancel_url': reverse('sale_list'),
    })
