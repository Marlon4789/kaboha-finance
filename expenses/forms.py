from django import forms
from .models import Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date', 'category', 'description', 'amount']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
