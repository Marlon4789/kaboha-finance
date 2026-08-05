from django import forms
from django.forms import inlineformset_factory
from .models import Sale, SaleItem


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['sale_date', 'customer_name', 'payment_method', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    fields=['product', 'quantity', 'unit_price'],
    extra=1,
    can_delete=True,
)
