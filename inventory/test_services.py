from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from inventory.models import InventoryMovement
from inventory.services import (
    InsufficientStockError,
    InventoryOperationError,
    InventoryService,
)
from products.models import Product


class InventoryServiceTests(TestCase):
    def make_product(self, *, name='Producto', unit=Product.BaseUnit.G, stock_tracked=True):
        return Product.objects.create(
            name=name,
            item_type=Product.ItemType.OTHER,
            base_unit=unit,
            is_stock_tracked=stock_tracked,
            production_cost=0,
        )

    def receipt(self, product, quantity, cost=None, *, occurred_at=None):
        return InventoryService.record_incoming(
            product,
            Decimal(str(quantity)),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=None if cost is None else Decimal(str(cost)),
            occurred_at=occurred_at or timezone.now(),
        )

    def test_incoming_accepts_null_zero_and_positive_cost(self):
        product = self.make_product()
        values = (None, Decimal('0'), Decimal('3.12500000'))

        rows = [self.receipt(product, 10, value) for value in values]

        self.assertEqual([row.unit_cost for row in rows], list(values))
        self.assertEqual(InventoryMovement.objects.count(), 3)
        self.assertEqual(InventoryService.get_stock(product), Decimal('30.000'))

    def test_incoming_rejects_non_stock_tracked_product(self):
        product = self.make_product(stock_tracked=False)

        with self.assertRaises(InventoryOperationError):
            self.receipt(product, 1)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_incoming_rejects_zero_negative_quantity_and_negative_cost(self):
        product = self.make_product()
        for quantity in (0, -1):
            with self.subTest(quantity=quantity), self.assertRaises(InventoryOperationError):
                self.receipt(product, quantity)
        with self.assertRaises(InventoryOperationError):
            self.receipt(product, 1, -0.01)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_context_references_must_match_the_movement_type(self):
        product = self.make_product()

        with self.assertRaises(InventoryOperationError):
            InventoryService.record_incoming(
                product,
                1,
                movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
                context={'expense': object()},
            )
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_stock_is_derived_from_incoming_and_outgoing_movements(self):
        product = self.make_product()
        self.receipt(product, 100, 3)

        created = InventoryService.consume(
            product,
            30,
            movement_type=InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT,
        )

        self.assertEqual(len(created), 1)
        self.assertEqual(InventoryService.get_stock(product), Decimal('70.000'))
        self.assertEqual(created[0].unit_cost, Decimal('3.00000000'))

    def test_available_layer_reports_partial_and_excludes_exhausted_layers(self):
        product = self.make_product()
        layer = self.receipt(product, 100, 3)

        InventoryService.consume(
            product, 40,
            movement_type=InventoryMovement.MovementType.SALE_OUT,
        )
        partial_layers = list(InventoryService.get_available_layers(product))

        self.assertEqual(len(partial_layers), 1)
        self.assertEqual(partial_layers[0].pk, layer.pk)
        self.assertEqual(partial_layers[0].available_quantity, Decimal('60.000'))
        self.assertEqual(layer.quantity, Decimal('100.000'))

        InventoryService.consume(
            product, 60,
            movement_type=InventoryMovement.MovementType.SALE_OUT,
        )
        self.assertEqual(list(InventoryService.get_available_layers(product)), [])
        self.assertEqual(InventoryService.get_stock(product), Decimal('0.000'))

    def test_fifo_uses_occurred_at_then_id_and_propagates_each_cost(self):
        product = self.make_product()
        later = datetime(2025, 1, 2, tzinfo=datetime_timezone.utc)
        earlier = datetime(2025, 1, 1, tzinfo=datetime_timezone.utc)
        late_layer = self.receipt(product, 100, '3.5', occurred_at=later)
        early_layer = self.receipt(product, 100, '3', occurred_at=earlier)

        outputs = InventoryService.consume(
            product,
            150,
            movement_type=InventoryMovement.MovementType.SALE_OUT,
        )

        self.assertEqual(
            [(row.quantity, row.source_movement_id, row.unit_cost) for row in outputs],
            [
                (Decimal('100.000'), early_layer.pk, Decimal('3.00000000')),
                (Decimal('50.000'), late_layer.pk, Decimal('3.50000000')),
            ],
        )

    def test_fifo_uses_id_as_tie_breaker_for_equal_occurred_at(self):
        product = self.make_product()
        same_time = datetime(2025, 1, 1, tzinfo=datetime_timezone.utc)
        first = self.receipt(product, 5, 1, occurred_at=same_time)
        second = self.receipt(product, 5, 2, occurred_at=same_time)

        [output] = InventoryService.consume(
            product, 5,
            movement_type=InventoryMovement.MovementType.SALE_OUT,
        )

        self.assertEqual(output.source_movement_id, first.pk)
        self.assertEqual(output.source_movement_id, min(first.pk, second.pk))

    def test_fifo_can_split_across_three_layers(self):
        product = self.make_product()
        layers = [self.receipt(product, quantity, cost) for quantity, cost in ((10, 1), (20, 2), (30, 3))]

        outputs = InventoryService.consume(
            product, 25,
            movement_type=InventoryMovement.MovementType.TRANSFORMATION_OUT,
        )

        self.assertEqual(
            [(row.quantity, row.source_movement_id) for row in outputs],
            [(Decimal('10.000'), layers[0].pk), (Decimal('15.000'), layers[1].pk)],
        )
        self.assertEqual(InventoryService.get_stock(product), Decimal('35.000'))

    def test_insufficient_stock_creates_no_partial_movements(self):
        product = self.make_product(name='Poco stock')
        self.receipt(product, 10, 3)
        before = InventoryMovement.objects.count()

        with self.assertRaises(InsufficientStockError) as caught:
            InventoryService.consume(
                product, 15,
                movement_type=InventoryMovement.MovementType.SALE_OUT,
            )

        self.assertEqual(caught.exception.product.pk, product.pk)
        self.assertEqual(caught.exception.requested_quantity, Decimal('15.000'))
        self.assertEqual(caught.exception.available_quantity, Decimal('10.000'))
        self.assertIn('Poco stock', str(caught.exception))
        self.assertEqual(InventoryMovement.objects.count(), before)
        self.assertEqual(InventoryService.get_stock(product), Decimal('10.000'))

    def test_costless_layer_remains_costless_when_consumed(self):
        product = self.make_product()
        layer = self.receipt(product, 5, None)

        [output] = InventoryService.consume(
            product, 2,
            movement_type=InventoryMovement.MovementType.SALE_OUT,
        )

        self.assertEqual(output.source_movement_id, layer.pk)
        self.assertIsNone(output.unit_cost)

    def test_unit_base_is_used_as_stored_without_silent_conversion(self):
        for unit in Product.BaseUnit.values:
            with self.subTest(unit=unit):
                product = self.make_product(name=f'Producto {unit}', unit=unit)
                self.receipt(product, Decimal('12.345'))
                self.assertEqual(InventoryService.get_stock(product), Decimal('12.345'))

    def test_adjustments_require_reason_and_negative_adjustment_uses_fifo(self):
        product = self.make_product()
        with self.assertRaises(InventoryOperationError):
            InventoryService.record_adjustment(
                product, 1,
                movement_type=InventoryMovement.MovementType.ADJUSTMENT_IN,
                reason='  ',
            )

        positive = InventoryService.record_adjustment(
            product, 10,
            movement_type=InventoryMovement.MovementType.ADJUSTMENT_IN,
            reason='Conteo físico sobrante',
            unit_cost=0,
        )
        [negative] = InventoryService.record_adjustment(
            product, 4,
            movement_type=InventoryMovement.MovementType.ADJUSTMENT_OUT,
            reason='Merma verificada',
        )

        self.assertEqual(positive.movement_type, InventoryMovement.MovementType.ADJUSTMENT_IN)
        self.assertEqual(negative.movement_type, InventoryMovement.MovementType.ADJUSTMENT_OUT)
        self.assertEqual(negative.source_movement_id, positive.pk)
        self.assertEqual(negative.unit_cost, Decimal('0E-8'))
        self.assertEqual(InventoryService.get_stock(product), Decimal('6.000'))

    def test_negative_adjustment_respects_insufficient_stock(self):
        product = self.make_product()
        with self.assertRaises(InsufficientStockError):
            InventoryService.record_adjustment(
                product, 1,
                movement_type=InventoryMovement.MovementType.ADJUSTMENT_OUT,
                reason='Corrección',
            )
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_insufficient_stock_across_layers_creates_no_partial_movements(self):
        product = self.make_product()
        self.receipt(product, 4, 1)
        self.receipt(product, 4, 2)
        before = InventoryMovement.objects.count()

        with self.assertRaises(InsufficientStockError):
            InventoryService.consume(
                product, 10,
                movement_type=InventoryMovement.MovementType.SALE_OUT,
            )

        self.assertEqual(InventoryMovement.objects.count(), before)
        self.assertEqual(InventoryService.get_stock(product), Decimal('8.000'))

    def test_failed_second_fifo_write_rolls_back_the_first(self):
        product = self.make_product()
        self.receipt(product, 5, 1)
        self.receipt(product, 5, 2)
        before = InventoryMovement.objects.count()
        real_create = InventoryService._create_movement
        calls = 0

        def fail_on_second_write(**values):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('Fallo simulado después de la primera salida')
            return real_create(**values)

        with patch.object(InventoryService, '_create_movement', side_effect=fail_on_second_write):
            with self.assertRaises(RuntimeError):
                InventoryService.consume(
                    product, 8,
                    movement_type=InventoryMovement.MovementType.SALE_OUT,
                )

        self.assertEqual(calls, 2)
        self.assertEqual(InventoryMovement.objects.count(), before)
        self.assertEqual(InventoryService.get_stock(product), Decimal('10.000'))
