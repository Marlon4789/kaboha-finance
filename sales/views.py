from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Sale
from .forms import SaleForm, SaleItemFormSet


def sale_list(request):
    sales = Sale.objects.order_by('-sale_date')
    return render(request, 'sales/list.html', {'sales': sales})


def sale_create(request):
    sale = Sale()
    if request.method == 'POST':
        form = SaleForm(request.POST)
        formset = SaleItemFormSet(request.POST, instance=sale)
        if form.is_valid() and formset.is_valid():
            sale = form.save()
            formset.instance = sale
            formset.save()
            return redirect(reverse('sale_list'))
    else:
        form = SaleForm()
        formset = SaleItemFormSet(instance=sale)
    return render(request, 'sales/form.html', {'form': form, 'formset': formset, 'title': 'Nueva venta'})


def sale_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
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
    if request.method == 'POST':
        sale.delete()
        return redirect(reverse('sale_list'))
    return render(request, 'confirm_delete.html', {
        'object_name': f'Venta {sale.id}',
        'cancel_url': reverse('sale_list'),
    })
