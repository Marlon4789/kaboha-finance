from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

from django.test import TestCase

from inventory.models import InventoryMovement
from inventory.services import InsufficientStockError, InventoryOperationError, InventoryService
from products.models import Product


class ExplicitLayerConsumptionTests(TestCase):
    def setUp(self):
        self.product = self.make_product('Producto A')
        self.old = self.receipt(self.product, 100, '2', day=1)
        self.new = self.receipt(self.product, 100, '5', day=2)

    def make_product(self, name):
        return Product.objects.create(
            name=name,
            item_type=Product.ItemType.OTHER,
            base_unit=Product.BaseUnit.G,
            is_stock_tracked=True,
        )

    def receipt(self, product, quantity, cost, *, day):
        return InventoryService.record_incoming(
            product,
            Decimal(quantity),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=Decimal(cost),
            occurred_at=datetime(2025, 1, day, tzinfo=datetime_timezone.utc),
        )

    def consume(self, quantity, layers):
        return InventoryService.consume(
            self.product,
            Decimal(quantity),
            movement_type=InventoryMovement.MovementType.TRANSFORMATION_OUT,
            source_layers=layers,
        )

    def test_explicit_layer_is_used_instead_of_the_oldest_one(self):
        [row] = self.consume(30, [self.new])

        self.assertEqual(row.source_movement_id, self.new.pk)
        self.assertEqual(row.unit_cost, Decimal('5.00000000'))
        self.assertEqual(InventoryService.get_stock(self.product), Decimal('170.000'))

    def test_layers_are_consumed_in_the_given_order_and_accept_pks(self):
        rows = self.consume(130, [self.new.pk, self.old.pk])

        self.assertEqual(
            [(row.source_movement_id, row.quantity) for row in rows],
            [(self.new.pk, Decimal('100.000')), (self.old.pk, Decimal('30.000'))],
        )

    def test_without_source_layers_behavior_remains_fifo(self):
        [row] = self.consume(30, None)

        self.assertEqual(row.source_movement_id, self.old.pk)

    def test_invalid_layers_are_rejected_without_writing_movements(self):
        other = self.make_product('Producto B')
        foreign = self.receipt(other, 50, '1', day=1)
        exhausted = self.receipt(self.product, 10, '1', day=3)
        InventoryService.consume(
            self.product, Decimal('10'),
            movement_type=InventoryMovement.MovementType.SALE_OUT,
            source_layers=[exhausted],
        )
        before = InventoryMovement.objects.count()

        for layers in ([], [self.old, self.old], [foreign], [exhausted], [999999]):
            with self.subTest(layers=layers), self.assertRaises(InventoryOperationError):
                self.consume(5, layers)

        self.assertEqual(InventoryMovement.objects.count(), before)

    def test_insufficient_quantity_in_selected_layers_reports_selected_availability(self):
        before = InventoryMovement.objects.count()

        with self.assertRaises(InsufficientStockError) as caught:
            self.consume(150, [self.new])

        self.assertEqual(caught.exception.available_quantity, Decimal('100.000'))
        self.assertEqual(InventoryMovement.objects.count(), before)
