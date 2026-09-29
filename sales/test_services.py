from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from inventory.models import InventoryMovement
from inventory.services import InsufficientStockError, InventoryService
from products.models import Product
from sales.models import Sale, SaleItem
from sales.services import SaleBeforeCutoverError, SaleIdempotencyConflictError, SalesService


class SalesServiceTests(TestCase):
    def make_product(self, name, *, quantity=Decimal('500')):
        return Product.objects.create(
            name=name,
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=quantity,
            is_sellable=True,
            is_stock_tracked=True,
            sale_price=20000,
            production_cost=10000,
        )

    def receipt(self, product, quantity, *, cost=None):
        return InventoryService.record_incoming(
            product, quantity,
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=cost,
        )

    def sale_data(self, **overrides):
        values = {
            'sale_date': date(2026, 9, 18),
            'customer_name': 'Cliente',
            'payment_method': 'Efectivo',
            'notes': 'Venta de prueba',
        }
        values.update(overrides)
        return values

    def create(self, sale_data, lines, operation_key=None):
        return SalesService.create_integrated_sale(
            sale_data, lines, operation_key=operation_key or str(uuid4()),
        )

    def test_simple_sale_uses_snapshot_and_reduces_stock(self):
        product = self.make_product('Café simple')
        self.receipt(product, Decimal('2000'))

        sale, created = self.create(self.sale_data(), [
            {'product': product, 'quantity': 1, 'unit_price': 20000},
        ])

        item = sale.items.get()
        [movement] = item.inventory_movements.all()
        self.assertTrue(created)
        self.assertEqual(item.unit_quantity_base_snapshot, Decimal('500.000'))
        self.assertEqual(movement.movement_type, InventoryMovement.MovementType.SALE_OUT)
        self.assertEqual(movement.quantity, Decimal('500.000'))
        self.assertEqual(InventoryService.get_stock(product), Decimal('1500.000'))

    def test_multiple_units_and_fifo_layers_keep_source_costs(self):
        product = self.make_product('Café FIFO')
        first = self.receipt(product, Decimal('1000'), cost=Decimal('3'))
        second = self.receipt(product, Decimal('1000'), cost=Decimal('4'))

        sale, _created = self.create(self.sale_data(), [
            {'product': product, 'quantity': 3, 'unit_price': 20000},
        ])

        movements = list(sale.items.get().inventory_movements.order_by('source_movement_id'))
        self.assertEqual(
            [(row.quantity, row.source_movement_id, row.unit_cost) for row in movements],
            [
                (Decimal('1000.000'), first.pk, Decimal('3.00000000')),
                (Decimal('500.000'), second.pk, Decimal('4.00000000')),
            ],
        )
        self.assertEqual(sum(row.quantity * row.unit_cost for row in movements), Decimal('5000.00000000'))
        self.assertEqual(InventoryService.get_stock(product), Decimal('500.000'))

    def test_any_insufficient_line_rolls_back_sale_items_and_all_consumption(self):
        product_a = self.make_product('Café A')
        product_b = self.make_product('Café B')
        self.receipt(product_a, Decimal('1000'))
        self.receipt(product_b, Decimal('500'))

        with self.assertRaises(InsufficientStockError):
            self.create(self.sale_data(), [
                {'product': product_a, 'quantity': 1, 'unit_price': 20000},
                {'product': product_b, 'quantity': 2, 'unit_price': 20000},
            ])

        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(InventoryMovement.objects.filter(movement_type='SALE_OUT').count(), 0)
        self.assertEqual(InventoryService.get_stock(product_a), Decimal('1000.000'))
        self.assertEqual(InventoryService.get_stock(product_b), Decimal('500.000'))

    def test_same_product_in_two_lines_consumes_each_line_and_links_it(self):
        product = self.make_product('Café dos líneas')
        self.receipt(product, Decimal('2000'))

        sale, _created = self.create(self.sale_data(), [
            {'product': product, 'quantity': 1, 'unit_price': 20000},
            {'product': product, 'quantity': 2, 'unit_price': 18000},
        ])

        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(
            sorted(item.inventory_movements.get().quantity for item in sale.items.all()),
            [Decimal('500.000'), Decimal('1000.000')],
        )
        self.assertEqual(InventoryService.get_stock(product), Decimal('500.000'))

    def test_idempotency_recognizes_same_sale_without_second_consumption(self):
        product = self.make_product('Café idempotente')
        self.receipt(product, Decimal('2000'))
        key = str(uuid4())
        data = self.sale_data()
        lines = [{'product': product, 'quantity': 1, 'unit_price': 20000}]

        first, first_created = self.create(data, lines, key)
        second, second_created = self.create(data, lines, key)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(InventoryMovement.objects.filter(movement_type='SALE_OUT').count(), 1)
        self.assertEqual(InventoryService.get_stock(product), Decimal('1500.000'))

    def test_idempotency_key_with_different_line_is_a_conflict(self):
        product = self.make_product('Café conflicto')
        self.receipt(product, Decimal('2000'))
        key = str(uuid4())
        self.create(self.sale_data(), [{'product': product, 'quantity': 1, 'unit_price': 20000}], key)

        with self.assertRaises(SaleIdempotencyConflictError):
            self.create(self.sale_data(), [{'product': product, 'quantity': 2, 'unit_price': 20000}], key)

        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(InventoryService.get_stock(product), Decimal('1500.000'))

    def test_sales_before_cutover_are_rejected_without_writes(self):
        product = self.make_product('Café fecha')
        self.receipt(product, Decimal('2000'))

        with self.assertRaises(SaleBeforeCutoverError):
            self.create(
                self.sale_data(sale_date=date(2026, 9, 17)),
                [{'product': product, 'quantity': 1, 'unit_price': 20000}],
            )

        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(InventoryService.get_stock(product), Decimal('2000.000'))

    def test_posted_sale_and_item_cannot_be_structurally_changed_or_deleted(self):
        product = self.make_product('Café inmutable')
        other_product = self.make_product('Café alterno')
        self.receipt(product, Decimal('2000'))
        sale, _created = self.create(self.sale_data(), [
            {'product': product, 'quantity': 1, 'unit_price': 20000},
        ])
        item = sale.items.get()

        item.quantity = 2
        with self.assertRaises(ValidationError):
            item.save()
        item.product = other_product
        with self.assertRaises(ValidationError):
            item.save()
        item.refresh_from_db()
        with self.assertRaises(ProtectedError):
            item.delete()
        sale.sale_date = date(2026, 9, 19)
        with self.assertRaises(ValidationError):
            sale.save()
        with self.assertRaises(ValidationError):
            sale.delete()

    def test_historical_sales_remain_unposted(self):
        product = self.make_product('Café histórico')
        for _ in range(13):
            sale = Sale.objects.create(sale_date=date(2026, 9, 17), payment_method='Efectivo')
            SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=20000)

        self.assertEqual(SaleItem.objects.count(), 13)
        self.assertFalse(Sale.objects.filter(operation_key__isnull=False).exists())
        self.assertFalse(InventoryMovement.objects.filter(movement_type='SALE_OUT').exists())


class SalesWebIntegrationTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Café web', item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND, base_unit=Product.BaseUnit.G,
            sale_unit_quantity=500, is_sellable=True, is_stock_tracked=True,
            sale_price=20000, production_cost=10000,
        )
        InventoryService.record_incoming(
            self.product, 2000, movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
        )

    def test_web_create_generates_key_and_posts_integrated_sale(self):
        response = self.client.get(reverse('sale_create'))
        key = response.context['form']['operation_key'].value()
        self.assertTrue(key)

        response = self.client.post(reverse('sale_create'), {
            'sale_date': '2026-09-18',
            'customer_name': 'Cliente web',
            'payment_method': 'Efectivo',
            'notes': '',
            'operation_key': key,
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': str(self.product.pk),
            'items-0-quantity': '1',
            'items-0-unit_price': '20000',
        })

        self.assertRedirects(response, reverse('sale_list'))
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(InventoryMovement.objects.filter(movement_type='SALE_OUT').count(), 1)
        self.assertEqual(InventoryService.get_stock(self.product), Decimal('1500.000'))
