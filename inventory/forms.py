from django import forms
from .models import InventoryEntry


class InventoryEntryForm(forms.ModelForm):
    class Meta:
        model = InventoryEntry
        fields = ['date', 'bags_added', 'kilos_added', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
