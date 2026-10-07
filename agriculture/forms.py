from decimal import Decimal

from django import forms

from agriculture.models import CropCycle
from products.models import Product


class HarvestCreateForm(forms.Form):
    crop_cycle = forms.ModelChoiceField(
        queryset=CropCycle.objects.none(),
        label='Ciclo de cultivo',
    )
    harvested_on = forms.DateField(
        label='Fecha de cosecha',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    notes = forms.CharField(
        label='Notas',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['crop_cycle'].queryset = CropCycle.objects.filter(
            lot__farm__owner=user,
        ).select_related('lot', 'lot__farm').order_by('-start_date')


class HarvestInventoryForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.CHERRY,
            base_unit=Product.BaseUnit.G,
            is_stock_tracked=True,
        ).order_by('name'),
        label='Producto de café cereza',
        empty_label='Selecciona café cereza',
        help_text='Debe ser café cereza inventariable con unidad base en gramos.',
    )
    quantity_kg = forms.DecimalField(
        label='Cantidad recolectada (kg)',
        max_digits=15,
        decimal_places=3,
        min_value=Decimal('0.001'),
        help_text='Se convertirá explícitamente a gramos para el inventario.',
        widget=forms.NumberInput(attrs={'min': '0.001', 'step': '0.001'}),
    )
