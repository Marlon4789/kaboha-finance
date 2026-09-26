from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    item_type = forms.ChoiceField(choices=Product.ItemType.choices, required=True)

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'item_type', 'coffee_stage', 'base_unit',
            'sale_unit_quantity', 'is_sellable', 'is_stock_tracked', 'sale_price',
            'production_cost', 'active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
