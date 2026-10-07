from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from agriculture.costing import activity_cost, crop_cycle_cost, lot_cost
from agriculture.models import ActivityInput, ActivityLabor, AgriculturalActivity, CropCycle, Farm, Lot
from agriculture.services import record_activity_input
from expenses.models import Expense, ExpenseCategory
from inventory.models import InventoryMovement
from inventory.services import InventoryService
from products.models import Product


class CostingTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='cost-user', password='test-password')
        farm = Farm.objects.create(owner=user, name='Finca costos')
        self.lot = Lot.objects.create(farm=farm, code='C-01', name='Lote costos', area_ha=Decimal('1.0000'))
        self.other_lot = Lot.objects.create(farm=farm, code='C-02', name='Otro lote', area_ha=Decimal('1.0000'))
        self.cycle = CropCycle.objects.create(
            lot=self.lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1),
        )
        self.other_cycle = CropCycle.objects.create(
            lot=self.other_lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1),
        )
        self.fertilizer = Product.objects.create(
            name='Fertilizante', item_type=Product.ItemType.AGRICULTURAL_INPUT,
            base_unit=Product.BaseUnit.G, is_stock_tracked=True,
        )

    def make_activity(self, cycle=None):
        return AgriculturalActivity.objects.create(
            crop_cycle=cycle or self.cycle,
            activity_type=AgriculturalActivity.ActivityType.FERTILIZATION,
            performed_on=date(2025, 3, 10),
        )

    def receipt(self, quantity, cost, *, day=1):
        return InventoryService.record_incoming(
            self.fertilizer,
            Decimal(quantity),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=None if cost is None else Decimal(cost),
            occurred_at=datetime(2025, 1, day, tzinfo=datetime_timezone.utc),
        )

    def add_labor(self, activity, hours, rate):
        return ActivityLabor.objects.create(
            activity=activity, worker_name='Jornalero', hours=Decimal(hours), hourly_rate=Decimal(rate),
        )

    def test_activity_without_records_costs_zero_and_is_complete(self):
        summary = activity_cost(self.make_activity())

        self.assertEqual((summary.labor, summary.inputs, summary.total), (Decimal('0.00'),) * 3)
        self.assertTrue(summary.is_complete)

    def test_labor_cost_is_hours_times_rate(self):
        activity = self.make_activity()
        self.add_labor(activity, '8', '5000.50')
        self.add_labor(activity, '2.5', '6000')

        summary = activity_cost(activity)

        self.assertEqual(summary.labor, Decimal('55004.00'))
        self.assertEqual(summary.total, Decimal('55004.00'))
        self.assertTrue(summary.is_complete)

    def test_input_cost_comes_from_consumed_layer_costs(self):
        self.receipt(100, '2', day=1)
        self.receipt(100, '3', day=2)
        activity = self.make_activity()
        record_activity_input(activity, self.fertilizer, '120')

        summary = activity_cost(activity)

        self.assertEqual(summary.inputs, Decimal('260.00'))
        self.assertTrue(summary.is_complete)

    def test_costless_layer_is_reported_as_incomplete_not_as_zero_cost(self):
        self.receipt(100, None)
        activity = self.make_activity()
        record_activity_input(activity, self.fertilizer, '40')

        summary = activity_cost(activity)

        self.assertEqual(summary.inputs, Decimal('0.00'))
        self.assertFalse(summary.is_complete)
        self.assertTrue(summary.issues)

    def test_input_without_recorded_consumption_is_incomplete(self):
        activity = self.make_activity()
        ActivityInput.objects.create(activity=activity, product=self.fertilizer, quantity=Decimal('10'))

        summary = activity_cost(activity)

        self.assertFalse(summary.is_complete)

    def test_cycle_and_lot_aggregate_their_activities_only(self):
        self.receipt(1000, '2')
        first, second, elsewhere = self.make_activity(), self.make_activity(), self.make_activity(self.other_cycle)
        self.add_labor(first, '1', '1000')
        self.add_labor(second, '2', '1000')
        self.add_labor(elsewhere, '10', '1000')
        record_activity_input(first, self.fertilizer, '50')
        record_activity_input(elsewhere, self.fertilizer, '500')

        cycle = crop_cycle_cost(self.cycle)

        self.assertEqual((cycle.labor, cycle.inputs, cycle.total), (Decimal('3000.00'), Decimal('100.00'), Decimal('3100.00')))
        self.assertEqual(lot_cost(self.lot), cycle)
        self.assertEqual(lot_cost(self.other_lot).total, Decimal('11000.00'))

    def test_expenses_are_not_added_to_agricultural_costs(self):
        activity = self.make_activity()
        self.add_labor(activity, '1', '1000')
        Expense.objects.create(
            category=ExpenseCategory.objects.create(name='Jornales'), description='Pago', amount=1000,
        )

        self.assertEqual(activity_cost(activity).total, Decimal('1000.00'))
