from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from agriculture.models import CropCycle, Farm, Harvest, Lot
from agriculture.services import register_harvest_inventory
from inventory.cutover import (
    LegacyInventoryCutoverConflictError,
    LegacyInventoryCutoverService,
)
from inventory.models import InventoryMovement
from inventory.services import InventoryService
from products.models import Product
from sales.models import Sale, SaleItem
from django.contrib.auth import get_user_model


class LegacyInventoryCutoverTests(TestCase):
    def setUp(self):
        self.traditional = Product.objects.create(
            name='Café tradicional',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=Decimal('500'),
            is_sellable=True,
            is_stock_tracked=False,
            sale_price=Decimal('20000'),
            production_cost=Decimal('10000'),
        )
        sale = Sale.objects.create(sale_date=date(2026, 9, 17), payment_method='Efectivo')
        for _ in range(13):
            SaleItem.objects.create(sale=sale, product=self.traditional, quantity=1, unit_price=20000)

    def test_cutover_creates_the_approved_opening_balances_and_preserves_sales(self):
        LegacyInventoryCutoverService.apply()

        self.traditional.refresh_from_db()
        parchment = Product.objects.get(name='Café pergamino')
        balances = InventoryMovement.objects.order_by('operation_key')

        self.assertTrue(self.traditional.is_stock_tracked)
        self.assertEqual(
            (parchment.item_type, parchment.coffee_stage, parchment.base_unit,
             parchment.is_stock_tracked, parchment.is_sellable, parchment.production_cost),
            (Product.ItemType.COFFEE, Product.CoffeeStage.PARCHMENT, Product.BaseUnit.G, True, False, None),
        )
        self.assertEqual(balances.count(), 2)
        self.assertEqual(
            [(row.product.name, row.movement_type, row.quantity, row.unit_cost) for row in balances],
            [
                ('Café pergamino', InventoryMovement.MovementType.OPENING_BALANCE_IN, Decimal('13000.000'), None),
                ('Café tradicional', InventoryMovement.MovementType.OPENING_BALANCE_IN, Decimal('2000.000'), None),
            ],
        )
        self.assertEqual(InventoryService.get_stock(self.traditional), Decimal('2000.000'))
        self.assertEqual(InventoryService.get_stock(parchment), Decimal('13000.000'))
        self.assertEqual(SaleItem.objects.count(), 13)
        self.assertFalse(InventoryMovement.objects.filter(movement_type=InventoryMovement.MovementType.SALE_OUT).exists())

    def test_cutover_is_idempotent(self):
        first = LegacyInventoryCutoverService.apply()
        second = LegacyInventoryCutoverService.apply()

        self.assertEqual(InventoryMovement.objects.count(), 2)
        self.assertEqual([created for _row, created in first], [True, True])
        self.assertEqual([created for _row, created in second], [False, False])

    def test_existing_operation_key_with_different_data_is_an_explicit_conflict(self):
        self.traditional.is_stock_tracked = True
        self.traditional.save(update_fields=['is_stock_tracked', 'updated_at'])
        InventoryMovement.objects.create(
            product=self.traditional,
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            quantity=Decimal('1.000'),
            occurred_at=LegacyInventoryCutoverService.occurred_at(),
            operation_key='legacy-cutoff:2026-09-18:cafe-tradicional',
        )

        with self.assertRaises(LegacyInventoryCutoverConflictError):
            LegacyInventoryCutoverService.apply()

    def test_command_dry_run_writes_nothing_then_applies_the_cutover(self):
        output = StringIO()
        call_command('apply_legacy_inventory_cutover', '--dry-run', stdout=output)
        self.assertFalse(self.traditional.is_stock_tracked)
        self.assertFalse(Product.objects.filter(name='Café pergamino').exists())
        self.assertEqual(InventoryMovement.objects.count(), 0)
        self.assertIn('sin cambios', output.getvalue())

        call_command('apply_legacy_inventory_cutover', stdout=StringIO())
        self.assertEqual(InventoryMovement.objects.count(), 2)

    def test_cutover_does_not_break_harvest_receipts(self):
        LegacyInventoryCutoverService.apply()
        user = get_user_model().objects.create_user(username='cutover-owner')
        farm = Farm.objects.create(owner=user, name='Finca corte')
        lot = Lot.objects.create(farm=farm, code='C-1', name='Lote corte', area_ha=1)
        cycle = CropCycle.objects.create(
            lot=lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2026, 1, 1),
        )
        harvest = Harvest.objects.create(crop_cycle=cycle, harvested_on=date(2026, 9, 19))
        cherry = Product.objects.create(
            name='Café cereza', item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.CHERRY, base_unit=Product.BaseUnit.G,
            is_stock_tracked=True, is_sellable=False, production_cost=None,
        )

        movement = register_harvest_inventory(harvest, cherry, Decimal('3'))

        self.assertEqual(movement.movement_type, InventoryMovement.MovementType.HARVEST_IN)
        self.assertEqual(movement.quantity, Decimal('3000.000'))
        self.assertEqual(InventoryMovement.objects.filter(harvest=harvest).count(), 1)
