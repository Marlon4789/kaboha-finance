from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from sales.models import Sale, SaleItem
from expenses.models import Expense, ExpenseCategory
from inventory.models import InventoryEntry
from .models import MonthlySummary


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
        InventoryEntry.objects.create(date=timezone.localdate(), bags_added=3, kilos_added=10)

        response = self.client.get(reverse('dashboard_home'))
        self.assertContains(response, '$70.000 COP')
        self.assertContains(response, '$20.000 COP')
        self.assertContains(response, '$50.000 COP')
        self.assertContains(response, 'Objetivo de venta')
        self.assertContains(response, '$35.000 COP')
        self.assertContains(response, 'Bolsas disponibles: 1')
        self.assertContains(response, 'Valor del stock no vendido multiplicado por el precio promedio por bolsa.')

    def test_sales_objective_calculates_with_partial_sales(self):
        product = Product.objects.create(
            name='Café Prueba 3',
            description='Café especial',
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        sale = Sale.objects.create(sale_date=timezone.localdate(), payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=35000)
        InventoryEntry.objects.create(date=timezone.localdate(), bags_added=16, kilos_added=8)

        response = self.client.get(reverse('dashboard_home'))
        self.assertContains(response, 'Objetivo de venta')
        self.assertContains(response, '$490.000 COP')
        self.assertContains(response, 'Bolsas disponibles: 14')

    def test_sales_objective_with_no_previous_sales(self):
        product = Product.objects.create(
            name='Café Prueba 2',
            description='Café especial',
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        InventoryEntry.objects.create(date=timezone.localdate(), bags_added=16, kilos_added=8)

        response = self.client.get(reverse('dashboard_home'))
        self.assertContains(response, 'Objetivo de venta')
        self.assertContains(response, '$560.000 COP')
        self.assertContains(response, 'Bolsas disponibles: 16')

    def test_home_refreshes_existing_monthly_summary(self):
        today = timezone.localdate()
        if today.month == 1:
            prev_year = today.year - 1
            prev_month = 12
        else:
            prev_year = today.year
            prev_month = today.month - 1

        summary = MonthlySummary.objects.create(
            year=prev_year,
            month=prev_month,
            sales_total=0,
            expenses_total=0,
            profit_total=0,
            bags_sold=0,
        )

        product = Product.objects.create(
            name='Café Historial',
            description='Café para historial',
            weight_grams=500,
            sale_price=30000,
            production_cost=12000,
            active=True,
        )
        sale = Sale.objects.create(
            sale_date=date(prev_year, prev_month, 12),
            payment_method='Efectivo',
        )
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=30000)

        self.client.get(reverse('dashboard_home'))

        summary.refresh_from_db()
        self.assertEqual(summary.bags_sold, 2)
        self.assertEqual(summary.sales_total, 60000)

    def test_home_shows_past_sales_months_but_hides_future_months(self):
        today = timezone.localdate()
        if today.month == 1:
            prev_year = today.year - 1
            prev_month = 12
        else:
            prev_year = today.year
            prev_month = today.month - 1

        month_names_es = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

        MonthlySummary.objects.create(
            year=prev_year,
            month=prev_month,
            sales_total=5000,
            expenses_total=1000,
            profit_total=4000,
            bags_sold=1,
        )

        product = Product.objects.create(
            name='Café Meses',
            description='Café para prueba de meses',
            weight_grams=500,
            sale_price=25000,
            production_cost=10000,
            active=True,
        )
        sale = Sale.objects.create(
            sale_date=date(prev_year, prev_month, 10),
            payment_method='Efectivo',
        )
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=25000)

        future_month = today.month + 1
        future_year = today.year
        if future_month == 13:
            future_month = 1
            future_year += 1
        MonthlySummary.objects.create(
            year=future_year,
            month=future_month,
            sales_total=90000,
            expenses_total=1000,
            profit_total=89000,
            bags_sold=4,
        )

        response = self.client.get(reverse('dashboard_home'))

        records = response.context['monthly_records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].year, prev_year)
        self.assertEqual(records[0].month, prev_month)
        self.assertContains(response, f"{month_names_es[prev_month - 1].capitalize()} {prev_year}")
        self.assertNotContains(response, f"{month_names_es[future_month - 1].capitalize()} {future_year}")

