from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from sales.models import Sale, SaleItem
from expenses.models import Expense, ExpenseCategory
from inventory.models import InventoryEntry, InventoryMovement
from inventory.services import InventoryService
from .models import MonthlySummary


class DashboardTests(TestCase):
    def make_product(self, name):
        return Product.objects.create(
            name=name,
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )

    def make_sale_item(self, product, sale_date, *, quantity=1, unit_price=35000):
        sale = Sale.objects.create(sale_date=sale_date, payment_method='Efectivo')
        item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
        )
        return sale, item

    def make_expense(self, expense_date, amount):
        category, _created = ExpenseCategory.objects.get_or_create(name='Producción')
        return Expense.objects.create(
            date=expense_date,
            category=category,
            description='Gasto de prueba',
            amount=amount,
        )

    @staticmethod
    def month_start_before(today, months=1):
        month_start = today.replace(day=1)
        for _ in range(months):
            month_start -= timedelta(days=1)
            month_start = month_start.replace(day=1)
        return month_start

    def test_home_page_status_code(self):
        response = self.client.get(reverse('dashboard_home'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_metrics_with_sales_and_expenses(self):
        product = Product.objects.create(
            name='Café Prueba',
            description='Café especial',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        sale = Sale.objects.create(sale_date=timezone.localdate(), payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=35000)
        category = ExpenseCategory.objects.create(name='Producción')
        Expense.objects.create(date=timezone.localdate(), category=category, description='Materia prima', amount=20000)
        # Legacy entries are retained for history only and cannot inflate stock.
        InventoryEntry.objects.create(date=timezone.localdate(), bags_added=3, kilos_added=10)
        InventoryService.record_incoming(
            product, 500, movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
        )

        response = self.client.get(reverse('dashboard_home'))
        self.assertContains(response, '$70.000 COP')
        self.assertContains(response, '$20.000 COP')
        self.assertContains(response, '$50.000 COP')
        self.assertContains(response, 'Objetivo de venta')
        self.assertContains(response, '$35.000 COP')
        self.assertContains(response, '1 disponibles')
        self.assertContains(response, 'Valor del stock operativo multiplicado por el precio promedio por bolsa.')
        summary = MonthlySummary.objects.get(year=timezone.localdate().year, month=timezone.localdate().month)
        self.assertEqual(summary.sales_total, 70000)
        self.assertEqual(summary.expenses_total, 20000)
        self.assertEqual(summary.profit_total, 50000)

    def test_sales_objective_calculates_with_partial_sales(self):
        product = Product.objects.create(
            name='Café Prueba 3',
            description='Café especial',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        sale = Sale.objects.create(sale_date=timezone.localdate(), payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=35000)
        InventoryService.record_incoming(
            product, 7000, movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
        )

        response = self.client.get(reverse('dashboard_home'))
        self.assertContains(response, 'Objetivo de venta')
        self.assertContains(response, '$490.000 COP')
        self.assertContains(response, 'Bolsas disponibles: 14')
        summary = MonthlySummary.objects.get(year=timezone.localdate().year, month=timezone.localdate().month)
        self.assertEqual(summary.sales_total, 70000)
        self.assertEqual(summary.expenses_total, 0)
        self.assertEqual(summary.profit_total, 70000)

    def test_sales_objective_with_no_previous_sales(self):
        product = Product.objects.create(
            name='Café Prueba 2',
            description='Café especial',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        InventoryService.record_incoming(
            product, 8000, movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
        )

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
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
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
        category = ExpenseCategory.objects.create(name='Gasto histórico')
        Expense.objects.create(
            date=date(prev_year, prev_month, 13),
            category=category,
            amount=7000,
        )

        self.client.get(reverse('dashboard_home'))

        summary.refresh_from_db()
        self.assertEqual(summary.bags_sold, 2)
        self.assertEqual(summary.sales_total, 60000)
        self.assertEqual(summary.expenses_total, 7000)
        self.assertEqual(summary.profit_total, 53000)

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
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
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

    def test_home_uses_selected_month_for_dashboard_indicators(self):
        today = timezone.localdate()
        month_names_es = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        if today.month == 1:
            selected_year = today.year - 1
            selected_month = 12
        else:
            selected_year = today.year
            selected_month = today.month - 1

        product = Product.objects.create(
            name='Café Selector',
            description='Café para selector mensual',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=40000,
            production_cost=15000,
            active=True,
        )
        sale = Sale.objects.create(
            sale_date=date(selected_year, selected_month, 8),
            payment_method='Efectivo',
        )
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=40000)

        response = self.client.get(
            reverse('dashboard_home'),
            {'month': f'{selected_year:04d}-{selected_month:02d}'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_month'], f'{selected_year:04d}-{selected_month:02d}')
        self.assertEqual(response.context['current_month_display'], f'{month_names_es[selected_month - 1].capitalize()} {selected_year}')
        self.assertContains(response, '$80.000 COP')
        self.assertContains(response, f'{month_names_es[selected_month - 1].capitalize()} {selected_year}')

    def test_year_indicators_use_current_year_through_today_and_ignore_selected_month(self):
        today = timezone.localdate()
        historical_date = date(today.year - 1, 12, 15)
        future_date = today + timedelta(days=1)
        product = self.make_product('Café periodo anual')

        self.make_sale_item(product, historical_date, quantity=3, unit_price=30000)
        self.make_sale_item(product, today, quantity=2, unit_price=25000)
        self.make_sale_item(product, future_date, quantity=4, unit_price=50000)
        self.make_expense(historical_date, 40000)
        self.make_expense(today, 15000)
        self.make_expense(future_date, 90000)

        selected_periods = (
            f'{historical_date.year:04d}-{historical_date.month:02d}',
            f'{today.year:04d}-{today.month:02d}',
        )
        responses = [
            self.client.get(reverse('dashboard_home'), {'month': selected_period})
            for selected_period in selected_periods
        ]

        for response in responses:
            self.assertEqual(response.context['current_year'], today.year)
            self.assertEqual(response.context['sales_total_year'], '$50.000 COP')
            self.assertEqual(response.context['expenses_total_year'], '$15.000 COP')
            self.assertEqual(response.context['profit_year'], '$35.000 COP')
            self.assertContains(response, f'Ventas del año {today.year}')
            self.assertContains(response, f'Gastos del año {today.year}')
            self.assertContains(response, f'Utilidad del año {today.year}')
            self.assertNotContains(response, 'Total global')

        self.assertEqual(
            [response.context['sales_total_year'] for response in responses],
            ['$50.000 COP', '$50.000 COP'],
        )

    def test_monthly_summary_includes_expense_only_period_in_history(self):
        expense_date = self.month_start_before(timezone.localdate(), months=1).replace(day=15)
        self.make_expense(expense_date, 12000)

        response = self.client.get(reverse('dashboard_home'))

        summary = MonthlySummary.objects.get(year=expense_date.year, month=expense_date.month)
        self.assertEqual(summary.sales_total, 0)
        self.assertEqual(summary.expenses_total, 12000)
        self.assertEqual(summary.profit_total, -12000)
        self.assertEqual(summary.bags_sold, 0)
        self.assertIn(summary, response.context['monthly_records'])

    def test_monthly_summary_reconciles_expense_edits_and_deletions(self):
        expense_date = self.month_start_before(timezone.localdate(), months=1).replace(day=15)
        expense = self.make_expense(expense_date, 10000)
        self.client.get(reverse('dashboard_home'))

        expense.amount = 25000
        expense.save()
        self.client.get(reverse('dashboard_home'))
        summary = MonthlySummary.objects.get(year=expense_date.year, month=expense_date.month)
        self.assertEqual(summary.expenses_total, 25000)
        self.assertEqual(summary.profit_total, -25000)

        expense.delete()
        self.client.get(reverse('dashboard_home'))
        self.assertFalse(
            MonthlySummary.objects.filter(year=expense_date.year, month=expense_date.month).exists(),
        )

    def test_monthly_summary_removes_stale_period_after_last_sale_is_deleted(self):
        sale_date = self.month_start_before(timezone.localdate(), months=1).replace(day=15)
        product = self.make_product('Café venta eliminada')
        sale, _item = self.make_sale_item(product, sale_date, quantity=2, unit_price=20000)
        self.client.get(reverse('dashboard_home'))
        self.assertTrue(
            MonthlySummary.objects.filter(year=sale_date.year, month=sale_date.month).exists(),
        )

        sale.delete()
        response = self.client.get(reverse('dashboard_home'))

        self.assertFalse(
            MonthlySummary.objects.filter(year=sale_date.year, month=sale_date.month).exists(),
        )
        self.assertFalse(
            any(
                (record.year, record.month) == (sale_date.year, sale_date.month)
                for record in response.context['monthly_records']
            ),
        )

    def test_monthly_summary_reconciles_when_sale_moves_to_another_period(self):
        old_date = self.month_start_before(timezone.localdate(), months=2).replace(day=15)
        new_date = self.month_start_before(timezone.localdate(), months=1).replace(day=15)
        product = self.make_product('Café venta trasladada')
        sale, _item = self.make_sale_item(product, old_date, quantity=2, unit_price=20000)
        self.client.get(reverse('dashboard_home'))
        self.assertEqual(
            MonthlySummary.objects.get(year=old_date.year, month=old_date.month).sales_total,
            40000,
        )

        sale.sale_date = new_date
        sale.save()
        self.client.get(reverse('dashboard_home'))

        self.assertFalse(
            MonthlySummary.objects.filter(year=old_date.year, month=old_date.month).exists(),
        )
        new_summary = MonthlySummary.objects.get(year=new_date.year, month=new_date.month)
        self.assertEqual(new_summary.sales_total, 40000)
