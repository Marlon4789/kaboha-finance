from django import forms
from django.forms import inlineformset_factory
from .models import Sale, SaleItem
from .services import SalesOperationError, SalesService


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['sale_date', 'customer_name', 'payment_method', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class SaleCreateForm(SaleForm):
    operation_key = forms.UUIDField(widget=forms.HiddenInput)


class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price']

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        if product is None or cleaned_data.get('DELETE'):
            return cleaned_data

        current_product_id = self.instance.product_id if self.instance.pk else None
        if current_product_id == product.pk:
            return cleaned_data

        try:
            SalesService.validate_product_eligibility(product)
        except SalesOperationError as exc:
            self.add_error('product', str(exc))
        return cleaned_data


SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    extra=1,
    can_delete=True,
)
