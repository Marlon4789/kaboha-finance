from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from .models import Sale, SaleItem


class SalesTests(TestCase):
    def test_sale_calculation_and_metrics(self):
        product = Product.objects.create(
            name='Café Prueba',
            description='Especial',
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
        sale = Sale.objects.create(sale_date=timezone.localdate(), customer_name='Cliente Prueba', payment_method='Efectivo')
        sale_item = SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=35000)

        self.assertEqual(sale.subtotal(), 70000)
        self.assertEqual(sale.total(), 70000)
        self.assertEqual(sale.quantity_units(), 2)
        self.assertEqual(sale_item.unit_quantity_base_snapshot, Decimal('500.000'))
        self.assertEqual(sale.grams_sold(), 1000)
        self.assertEqual(sale.kilos_sold(), 1)
        self.assertEqual(str(sale), f'Venta {sale.id} - Cliente Prueba ({sale.sale_date})')

    def test_sale_list_page(self):
        Sale.objects.create(sale_date=timezone.localdate(), customer_name='Cliente Test', payment_method='Efectivo')
        response = self.client.get(reverse('sale_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cliente Test')

    def test_sale_item_grams_use_snapshot_after_product_weight_changes(self):
        product = Product.objects.create(
            name='Café Snapshot',
            description='Café molido',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=250,
            is_sellable=True,
            is_stock_tracked=True,
            weight_grams=250,
            sale_price=Decimal('18000.00'),
            production_cost=9000,
            active=True,
        )
        sale = Sale.objects.create(payment_method='Efectivo')
        item = SaleItem.objects.create(sale=sale, product=product, quantity=3, unit_price=18000)

        self.assertEqual(item.unit_quantity_base_snapshot, Decimal('250.000'))
        self.assertEqual(item.grams_sold(), Decimal('750.000'))

        product.weight_grams = 900
        product.save(update_fields=['weight_grams'])
        item.refresh_from_db()
        self.assertEqual(item.grams_sold(), Decimal('750.000'))
        self.assertEqual(sale.grams_sold(), Decimal('750.000'))

    def test_sale_item_snapshots_commercial_quantity_at_creation(self):
        product = Product.objects.create(
            name='Café Presentación',
            description='Café molido',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=250,
            is_sellable=True,
            is_stock_tracked=True,
            sale_price=18000,
            production_cost=9000,
        )
        sale = Sale.objects.create(payment_method='Efectivo')
        item = SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=18000)

        product.sale_unit_quantity = 500
        product.save(update_fields=['sale_unit_quantity'])
        item.refresh_from_db()
        self.assertEqual(item.unit_quantity_base_snapshot, Decimal('250.000'))
        self.assertEqual(item.grams_sold(), Decimal('500.000'))

    def test_base_unit_cannot_be_changed_after_sales_have_been_snapshotted(self):
        product = Product.objects.create(
            name='Café Unidad Inmutable',
            description='Café molido',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=250,
            is_sellable=True,
            is_stock_tracked=True,
            sale_price=18000,
            production_cost=9000,
        )
        sale = Sale.objects.create(payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=18000)

        product.base_unit = Product.BaseUnit.ML
        with self.assertRaises(ValidationError):
            product.full_clean()
        with self.assertRaises(ValidationError):
            product.save(update_fields=['base_unit'])
