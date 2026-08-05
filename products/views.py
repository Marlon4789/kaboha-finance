from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Product
from .forms import ProductForm


def product_list(request):
    products = Product.objects.order_by('-created_at')
    return render(request, 'products/list.html', {'products': products})


def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(reverse('product_list'))
    else:
        form = ProductForm()
    return render(request, 'products/form.html', {'form': form, 'title': 'Nuevo producto'})


def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect(reverse('product_list'))
    else:
        form = ProductForm(instance=product)
    return render(request, 'products/form.html', {'form': form, 'title': 'Editar producto'})


def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        return redirect(reverse('product_list'))
    return render(request, 'confirm_delete.html', {
        'object_name': product.name,
        'cancel_url': reverse('product_list'),
    })
