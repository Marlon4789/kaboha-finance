from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from agriculture.forms import HarvestCreateForm, HarvestInventoryForm
from agriculture.models import Harvest
from agriculture.services import (
    HarvestAlreadyRegisteredError,
    HarvestRegistrationError,
    register_harvest_inventory,
)


@login_required
def harvest_list(request):
    harvests = Harvest.objects.filter(crop_cycle__lot__farm__owner=request.user).select_related(
        'crop_cycle', 'crop_cycle__lot', 'crop_cycle__lot__farm', 'inventory_movement',
    ).annotate(inventory_movement_id=F('inventory_movement__pk')).order_by(
        '-harvested_on', '-created_at',
    )
    return render(request, 'agriculture/harvest_list.html', {'harvests': harvests})


@login_required
def harvest_create(request):
    if request.method == 'POST':
        form = HarvestCreateForm(request.POST, user=request.user)
        if form.is_valid():
            harvest = Harvest.objects.create(
                crop_cycle=form.cleaned_data['crop_cycle'],
                harvested_on=form.cleaned_data['harvested_on'],
                notes=form.cleaned_data['notes'],
            )
            messages.info(request, 'Cosecha creada como pendiente; registra su cantidad para confirmarla en inventario.')
            return redirect('harvest_inventory_register', pk=harvest.pk)
    else:
        form = HarvestCreateForm(initial={'harvested_on': timezone.localdate()}, user=request.user)
    return render(request, 'agriculture/harvest_form.html', {'form': form})


@login_required
def harvest_register_inventory(request, pk):
    harvest = get_object_or_404(
        Harvest.objects.select_related('crop_cycle', 'crop_cycle__lot', 'crop_cycle__lot__farm'),
        pk=pk,
        crop_cycle__lot__farm__owner=request.user,
    )
    if hasattr(harvest, 'inventory_movement'):
        messages.warning(request, 'Esta cosecha ya fue registrada en inventario.')
        return redirect('harvest_list')

    if request.method == 'POST':
        form = HarvestInventoryForm(request.POST)
        if form.is_valid():
            try:
                movement = register_harvest_inventory(
                    harvest,
                    form.cleaned_data['product'],
                    form.cleaned_data['quantity_kg'],
                    created_by=request.user,
                )
            except HarvestAlreadyRegisteredError as exc:
                messages.warning(request, str(exc))
                return redirect('harvest_list')
            except HarvestRegistrationError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    f'Cosecha registrada: {movement.quantity} g de {movement.product.name} ingresaron al inventario.',
                )
                return redirect('harvest_list')
    else:
        form = HarvestInventoryForm()

    return render(request, 'agriculture/harvest_register.html', {
        'harvest': harvest,
        'form': form,
        'has_cherry_products': form.fields['product'].queryset.exists(),
    })
