from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from agriculture.models import ActivityInput, AgriculturalActivity, CropCycle, Farm, Lot
from agriculture.services import ActivityInputError, record_activity_input
from inventory.models import InventoryMovement
from inventory.services import InventoryService
from products.models import Product


class ActivityInputConsumptionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='input-user', password='test-password')
        farm = Farm.objects.create(owner=self.user, name='Finca insumos')
        lot = Lot.objects.create(farm=farm, code='I-01', name='Lote insumos', area_ha=Decimal('1.0000'))
        cycle = CropCycle.objects.create(
            lot=lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1),
        )
        self.activity = AgriculturalActivity.objects.create(
            crop_cycle=cycle,
            activity_type=AgriculturalActivity.ActivityType.FERTILIZATION,
            performed_on=date(2025, 3, 10),
        )
        self.fertilizer = self.make_product('Fertilizante')
        self.old = self.receipt(self.fertilizer, 100, '2', day=1)
        self.new = self.receipt(self.fertilizer, 100, '3', day=2)

    def make_product(self, name, *, item_type=Product.ItemType.AGRICULTURAL_INPUT, tracked=True):
        return Product.objects.create(
            name=name, item_type=item_type, base_unit=Product.BaseUnit.G, is_stock_tracked=tracked,
        )

    def receipt(self, product, quantity, cost, *, day):
        return InventoryService.record_incoming(
            product,
            Decimal(quantity),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=Decimal(cost),
            occurred_at=datetime(2025, 1, day, tzinfo=datetime_timezone.utc),
        )

    def assert_nothing_recorded(self):
        self.assertEqual(ActivityInput.objects.count(), 0)
        self.assertFalse(
            InventoryMovement.objects.filter(
                movement_type=InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT,
            ).exists(),
        )

    def test_records_input_and_one_consumption_row_per_fifo_layer(self):
        activity_input, movements = record_activity_input(
            self.activity, self.fertilizer, '120', created_by=self.user,
        )

        self.assertEqual(activity_input.quantity, Decimal('120'))
        self.assertEqual(
            [(m.source_movement_id, m.quantity, m.unit_cost) for m in movements],
            [
                (self.old.pk, Decimal('100.000'), Decimal('2.00000000')),
                (self.new.pk, Decimal('20.000'), Decimal('3.00000000')),
            ],
        )
        for movement in movements:
            self.assertEqual(movement.activity_input, activity_input)
            self.assertEqual(movement.movement_type, InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT)
            self.assertEqual(movement.created_by, self.user)
            self.assertEqual(movement.occurred_at.date(), date(2025, 3, 10))
        self.assertEqual(InventoryService.get_stock(self.fertilizer), Decimal('80.000'))

    def test_explicit_layers_are_forwarded_to_inventory(self):
        _, movements = record_activity_input(self.activity, self.fertilizer, '10', source_layers=[self.new])

        self.assertEqual([m.source_movement_id for m in movements], [self.new.pk])

    def test_insufficient_stock_rolls_back_the_input(self):
        with self.assertRaises(ActivityInputError):
            record_activity_input(self.activity, self.fertilizer, '500')

        self.assert_nothing_recorded()
        self.assertEqual(InventoryService.get_stock(self.fertilizer), Decimal('200.000'))

    def test_rejects_ineligible_products(self):
        coffee = self.make_product('Café', item_type=Product.ItemType.COFFEE)
        untracked = self.make_product('Abono propio', tracked=False)

        for product in (coffee, untracked):
            with self.subTest(product=product.name), self.assertRaises(ActivityInputError):
                record_activity_input(self.activity, product, '1')
        self.assert_nothing_recorded()

    def test_rejects_invalid_quantities(self):
        for quantity in ('0', '-5', 'abc', 'NaN', '1.2345'):
            with self.subTest(quantity=quantity), self.assertRaises(ActivityInputError):
                record_activity_input(self.activity, self.fertilizer, quantity)
        self.assert_nothing_recorded()

    def test_rejects_missing_activity_or_product(self):
        with self.assertRaises(ActivityInputError):
            record_activity_input(999999, self.fertilizer, '1')
        with self.assertRaises(ActivityInputError):
            record_activity_input(self.activity, 999999, '1')
        self.assert_nothing_recorded()

    def test_consumed_input_cannot_change_structural_fields_but_notes_can(self):
        activity_input, _ = record_activity_input(self.activity, self.fertilizer, '10')

        activity_input.quantity = Decimal('20')
        with self.assertRaises(ValidationError):
            activity_input.save()

        activity_input.refresh_from_db()
        activity_input.notes = 'Aplicado en la mañana'
        activity_input.save()
        self.assertEqual(ActivityInput.objects.get(pk=activity_input.pk).notes, 'Aplicado en la mañana')

    def test_consumed_input_cannot_be_deleted(self):
        activity_input, _ = record_activity_input(self.activity, self.fertilizer, '10')

        with self.assertRaises(ProtectedError):
            activity_input.delete()

    def test_admin_cannot_add_or_change_inputs_directly(self):
        activity_input, _ = record_activity_input(self.activity, self.fertilizer, '10')
        admin_user = get_user_model().objects.create_superuser('boss', 'boss@example.com', 'test-password')
        self.client.force_login(admin_user)

        self.assertEqual(self.client.get(reverse('admin:agriculture_activityinput_add')).status_code, 403)
        change_url = reverse('admin:agriculture_activityinput_change', args=[activity_input.pk])
        self.assertEqual(self.client.post(change_url, {'quantity': '99'}).status_code, 403)
