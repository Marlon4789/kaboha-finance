from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'weight_grams', 'sale_price', 'production_cost', 'active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
