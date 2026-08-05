from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from sales.models import Sale, SaleItem
from expenses.models import Expense, ExpenseCategory


class DashboardTests(TestCase):
    def test_home_page_status_code(self):
        response = self.client.get(reverse('dashboard_home'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_metrics_with_sales_and_expenses(self):
        product = Product.objects.create(
            name='Café Prueba',
            description='Café especial',
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        sale = Sale.objects.create(sale_date=timezone.localdate(), payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=35000)
        category = ExpenseCategory.objects.create(name='Producción')
        Expense.objects.create(date=timezone.localdate(), category=category, description='Materia prima', amount=20000)

        response = self.client.get(reverse('dashboard_home'))
        self.assertContains(response, '$70.000 COP')
        self.assertContains(response, '$20.000 COP')
        self.assertContains(response, '$50.000 COP')
