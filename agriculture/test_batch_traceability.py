from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from agriculture.models import CropCycle, Farm, Harvest, Lot, ProductionBatch
from agriculture.services import BatchTransformationError, register_batch_transformation, register_harvest_inventory
from agriculture.traceability import trace_sale_item
from inventory.models import InventoryMovement
from inventory.services import InventoryService
from products.models import Product
from sales.models import Sale, SaleItem
from sales.services import SalesService

Stage = Product.CoffeeStage
Type = InventoryMovement.MovementType


def at(day):
    return datetime(2025, 10, day, 8, tzinfo=datetime_timezone.utc)


class BatchAndTraceabilityBase(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='batch-user', password='test-password')
        self.farm_a = Farm.objects.create(owner=user, name='Finca A')
        self.farm_b = Farm.objects.create(owner=user, name='Finca B')
        self.cycle_a = self.make_cycle(self.farm_a, 'A-01')
        self.cycle_b = self.make_cycle(self.farm_b, 'B-01')
        self.cherry = self.make_product('Cereza', Stage.CHERRY)
        self.parchment = self.make_product('Pergamino', Stage.PARCHMENT, sellable=True)
        self.green = self.make_product('Verde', Stage.GREEN, sellable=True)

    def make_cycle(self, farm, code):
        lot = Lot.objects.create(farm=farm, code=code, name=f'Lote {code}', area_ha=Decimal('1.0000'))
        return CropCycle.objects.create(lot=lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1))

    def make_product(self, name, stage, *, sellable=False, item_type=Product.ItemType.COFFEE, unit=Product.BaseUnit.G):
        return Product.objects.create(
            name=name,
            item_type=item_type,
            coffee_stage=stage if item_type == Product.ItemType.COFFEE else None,
            base_unit=unit,
            is_stock_tracked=True,
            is_sellable=sellable,
            sale_unit_quantity=Decimal('500') if sellable else None,
            sale_price=Decimal('20000') if sellable else None,
        )

    def harvest(self, cycle, kilos, day):
        harvest = Harvest.objects.create(crop_cycle=cycle, harvested_on=date(2025, 10, day))
        register_harvest_inventory(harvest, self.cherry, Decimal(kilos))
        return harvest

    def batch(self, code, process=ProductionBatch.ProcessType.BENEFIT):
        return ProductionBatch.objects.create(
            code=code, process_type=process, started_at=at(11), finished_at=at(12),
        )

    def sell(self, product, quantity, key):
        sale, _ = SalesService.create_integrated_sale(
            {'sale_date': date(2026, 10, 1), 'payment_method': 'Efectivo'},
            [{'product': product, 'quantity': quantity, 'unit_price': 20000}],
            operation_key=key,
        )
        return sale.items.get()


class BatchTransformationTests(BatchAndTraceabilityBase):
    def setUp(self):
        super().setUp()
        self.harvest_a = self.harvest(self.cycle_a, '300', 1)
        self.harvest_b = self.harvest(self.cycle_b, '100', 2)

    def test_batch_consumes_cherry_and_creates_one_parchment_layer(self):
        batch = self.batch('PB-001')

        outputs, incoming = register_batch_transformation(
            batch, [{'product': self.cherry, 'quantity': 400000}], self.parchment, 80000,
        )

        self.assertEqual(len(outputs), 2)
        self.assertEqual({row.production_batch for row in outputs}, {batch})
        self.assertEqual(incoming.movement_type, Type.TRANSFORMATION_IN)
        self.assertEqual(incoming.production_batch, batch)
        self.assertEqual(incoming.occurred_at, at(12))
        self.assertIsNone(incoming.unit_cost)
        self.assertEqual(InventoryService.get_stock(self.cherry), Decimal('0.000'))
        self.assertEqual(InventoryService.get_stock(self.parchment), Decimal('80000.000'))

    def test_output_cost_is_the_consumed_cost_over_output_grams(self):
        costed = Product.objects.create(
            name='Cereza comprada', item_type=Product.ItemType.COFFEE, coffee_stage=Stage.CHERRY,
            base_unit=Product.BaseUnit.G, is_stock_tracked=True,
        )
        InventoryService.record_incoming(
            costed, Decimal('1000'), movement_type=Type.OPENING_BALANCE_IN, unit_cost=Decimal('2'),
        )

        _, incoming = register_batch_transformation(
            self.batch('PB-002'), [{'product': costed, 'quantity': 1000}], self.parchment, 400,
        )

        self.assertEqual(incoming.unit_cost, Decimal('5.00000000'))

    def test_explicit_layer_preserves_the_origin_of_the_batch(self):
        layer_b = self.harvest_b.inventory_movement

        outputs, _ = register_batch_transformation(
            self.batch('PB-003'),
            [{'product': self.cherry, 'quantity': 50000, 'source_layers': [layer_b]}],
            self.parchment, 10000,
        )

        self.assertEqual([row.source_movement_id for row in outputs], [layer_b.pk])

    def test_invalid_batches_write_nothing(self):
        before = InventoryMovement.objects.count()
        ok_input = [{'product': self.cherry, 'quantity': 1000}]
        cases = {
            'salida mayor que entrada': (ok_input, self.parchment, 2000),
            'sin entradas': ([], self.parchment, 10),
            'salida no es café': (ok_input, self.make_product('Abono', None, item_type=Product.ItemType.OTHER), 10),
            'cantidad cero': ([{'product': self.cherry, 'quantity': 0}], self.parchment, 10),
            'stock insuficiente': ([{'product': self.cherry, 'quantity': 999999999}], self.parchment, 10),
            'salida invalida': (ok_input, self.parchment, 'abc'),
        }

        for name, (inputs, output, quantity) in cases.items():
            with self.subTest(case=name), self.assertRaises(BatchTransformationError):
                register_batch_transformation(self.batch(f'X-{name}'[:40]), inputs, output, quantity)

        self.assertEqual(InventoryMovement.objects.count(), before)

    def test_a_batch_can_only_be_posted_once(self):
        batch = self.batch('PB-004')
        register_batch_transformation(batch, [{'product': self.cherry, 'quantity': 1000}], self.parchment, 200)

        with self.assertRaises(BatchTransformationError):
            register_batch_transformation(batch, [{'product': self.cherry, 'quantity': 1000}], self.parchment, 200)
        self.assertEqual(InventoryMovement.objects.filter(production_batch=batch).count(), 2)


class SaleTraceabilityTests(BatchAndTraceabilityBase):
    def test_sale_traces_back_to_each_farm_with_proportional_shares(self):
        harvest_a = self.harvest(self.cycle_a, '300', 1)
        harvest_b = self.harvest(self.cycle_b, '100', 2)
        register_batch_transformation(
            self.batch('PB-010'), [{'product': self.cherry, 'quantity': 400000}], self.parchment, 80000,
        )

        shares = trace_sale_item(self.sell(self.parchment, 2, 'trace-1'))

        by_harvest = {share.harvest: share for share in shares}
        self.assertEqual(sum(share.share for share in shares), Decimal('1'))
        self.assertEqual(by_harvest[harvest_a].share, Decimal('0.75'))
        self.assertEqual(by_harvest[harvest_b].share, Decimal('0.25'))
        self.assertEqual(by_harvest[harvest_a].farm, self.farm_a)
        self.assertEqual(by_harvest[harvest_b].lot.code, 'B-01')
        self.assertEqual(by_harvest[harvest_b].crop_cycle, self.cycle_b)
        self.assertEqual(by_harvest[harvest_a].batch_codes, ('PB-010',))

    def test_trace_crosses_several_transformation_stages(self):
        harvest = self.harvest(self.cycle_a, '100', 1)
        register_batch_transformation(
            self.batch('PB-020'), [{'product': self.cherry, 'quantity': 100000}], self.parchment, 20000,
        )
        register_batch_transformation(
            self.batch('PB-021', ProductionBatch.ProcessType.MILLING),
            [{'product': self.parchment, 'quantity': 20000}], self.green, 16000,
        )

        [share] = trace_sale_item(self.sell(self.green, 2, 'trace-2'))

        self.assertEqual(share.harvest, harvest)
        self.assertEqual(share.share, Decimal('1'))
        self.assertEqual(share.batch_codes, ('PB-021', 'PB-020'))

    def test_layers_without_agricultural_origin_are_reported_as_unknown(self):
        InventoryService.record_incoming(
            self.parchment, Decimal('5000'), movement_type=Type.OPENING_BALANCE_IN,
        )

        [share] = trace_sale_item(self.sell(self.parchment, 2, 'trace-3'))

        self.assertFalse(share.is_known)
        self.assertEqual(share.share, Decimal('1'))
        self.assertIn('Saldo inicial', share.reason)

    def test_sale_without_inventory_movements_is_unknown(self):
        sale = Sale.objects.create(sale_date=date(2026, 1, 1), payment_method='Efectivo')
        item = SaleItem.objects.create(sale=sale, product=self.parchment, quantity=1, unit_price=20000)

        [share] = trace_sale_item(item)

        self.assertFalse(share.is_known)
        self.assertEqual(share.share, Decimal('1'))
