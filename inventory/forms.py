from django import forms
from .models import InventoryEntry


class InventoryEntryForm(forms.ModelForm):
    class Meta:
        model = InventoryEntry
        fields = ['date', 'bags_added', 'kilos_added', 'kilos_pergamino', 'notes']
        labels = {
            'date': 'Fecha',
            'bags_added': 'Bolsas ingresadas',
            'kilos_added': 'Kilos de café molido',
            'kilos_pergamino': 'Kilos de café pergamino',
            'notes': 'Notas',
        }
        help_texts = {
            'kilos_added': 'Cantidad de café ya molido.',
            'kilos_pergamino': 'Cantidad de café pergamino.',
        }
        widgets = {
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
