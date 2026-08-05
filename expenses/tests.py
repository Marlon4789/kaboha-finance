from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Expense, ExpenseCategory


class ExpenseTests(TestCase):
    def test_expense_creation_and_list_view(self):
        category = ExpenseCategory.objects.create(name='Producción')
        Expense.objects.create(date=timezone.localdate(), category=category, description='Costo materia prima', amount=25000)

        response = self.client.get(reverse('expense_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Costo materia prima')
