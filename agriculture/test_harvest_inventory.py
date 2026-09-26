from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agriculture.forms import HarvestInventoryForm
from agriculture.models import CropCycle, Farm, Harvest, Lot
from agriculture.services import (
    HarvestAlreadyRegisteredError,
    HarvestRegistrationError,
    register_harvest_inventory,
)
from inventory.models import InventoryMovement
from inventory.services import InventoryService
from products.models import Product


class HarvestInventoryIntegrationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='harvest-user', password='test-password')
        self.farm = Farm.objects.create(owner=user, name='Finca cosecha')
        self.lot = Lot.objects.create(
            farm=self.farm, code='H-01', name='Lote cosecha', area_ha=Decimal('1.0000'),
        )
        self.cycle = CropCycle.objects.create(
            lot=self.lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date=date(2025, 1, 1),
        )
        self.harvest = Harvest.objects.create(
            crop_cycle=self.cycle, harvested_on=date(2025, 10, 10), notes='Corte principal',
        )
        self.cherry = self.make_product('Café cereza')

    def make_product(
        self,
        name,
        *,
        item_type=Product.ItemType.COFFEE,
        coffee_stage=Product.CoffeeStage.CHERRY,
        base_unit=Product.BaseUnit.G,
        stock_tracked=True,
    ):
        return Product.objects.create(
            name=name,
            item_type=item_type,
            coffee_stage=coffee_stage,
            base_unit=base_unit,
            is_stock_tracked=stock_tracked,
            production_cost=0,
        )

    def register(self, harvest=None, product=None, quantity=Decimal('850')):
        return register_harvest_inventory(
            harvest or self.harvest,
            product or self.cherry,
            quantity,
        )

    def test_valid_harvest_creates_one_cherry_receipt_in_grams(self):
        movement = self.register()

        self.assertEqual(movement.movement_type, InventoryMovement.MovementType.HARVEST_IN)
        self.assertEqual(movement.harvest, self.harvest)
        self.assertEqual(movement.product, self.cherry)
        self.assertEqual(movement.quantity, Decimal('850000.000'))
        self.assertEqual(movement.product.base_unit, Product.BaseUnit.G)
        self.assertIsNone(movement.unit_cost)
        self.assertEqual(movement.occurred_at.date(), self.harvest.harvested_on)
        self.assertEqual(movement.harvest.crop_cycle.lot.farm, self.farm)
        self.assertEqual(InventoryService.get_stock(self.cherry), Decimal('850000.000'))

    def test_quantity_must_be_positive(self):
        for quantity in (Decimal('0'), Decimal('-1')):
            with self.subTest(quantity=quantity), self.assertRaises(HarvestRegistrationError):
                self.register(quantity=quantity)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_invalid_gram_precision_is_reported_as_harvest_validation_error(self):
        with self.assertRaises(HarvestRegistrationError):
            self.register(quantity=Decimal('0.0000001'))
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_harvest_rejects_noncoffee_or_noncherry_products(self):
        other_type = self.make_product(
            'Fertilizante', item_type=Product.ItemType.AGRICULTURAL_INPUT, coffee_stage=None,
        )
        other_stage = self.make_product('Café pergamino', coffee_stage=Product.CoffeeStage.PARCHMENT)

        for product in (other_type, other_stage):
            with self.subTest(product=product.name), self.assertRaises(HarvestRegistrationError):
                self.register(product=product)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_harvest_requires_gram_unit_and_stock_tracking(self):
        wrong_unit = self.make_product('Cereza ml', base_unit=Product.BaseUnit.ML)
        not_tracked = self.make_product('Cereza no inventariable', stock_tracked=False)

        for product in (wrong_unit, not_tracked):
            with self.subTest(product=product.name), self.assertRaises(HarvestRegistrationError):
                self.register(product=product)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_duplicate_registration_is_rejected_without_creating_another_movement(self):
        first = self.register()

        with self.assertRaises(HarvestAlreadyRegisteredError):
            self.register()

        self.assertEqual(InventoryMovement.objects.filter(harvest=self.harvest).count(), 1)
        self.assertEqual(first.pk, self.harvest.inventory_movement.pk)

    def test_form_only_offers_stock_tracked_cherry_products(self):
        other_stage = self.make_product('Café tostado', coffee_stage=Product.CoffeeStage.ROASTED)
        form = HarvestInventoryForm()

        self.assertEqual(list(form.fields['product'].queryset), [self.cherry])
        self.assertNotIn(other_stage, form.fields['product'].queryset)

    def test_create_and_confirmation_views_keep_quantity_out_of_harvest(self):
        response = self.client.post(reverse('harvest_create'), {
            'crop_cycle': self.cycle.pk,
            'harvested_on': '2025-10-11',
            'notes': 'Segundo corte',
        })

        harvest = Harvest.objects.get(harvested_on='2025-10-11')
        self.assertRedirects(response, reverse('harvest_inventory_register', args=[harvest.pk]))
        self.assertFalse(InventoryMovement.objects.filter(harvest=harvest).exists())
        self.assertNotIn('quantity', {field.name for field in Harvest._meta.fields})

        response = self.client.post(reverse('harvest_inventory_register', args=[harvest.pk]), {
            'product': self.cherry.pk,
            'quantity_kg': '1.250',
        })
        self.assertRedirects(response, reverse('harvest_list'))
        self.assertEqual(harvest.inventory_movement.quantity, Decimal('1250.000'))

    def test_register_view_handles_duplicate_confirmation(self):
        url = reverse('harvest_inventory_register', args=[self.harvest.pk])
        payload = {'product': self.cherry.pk, 'quantity_kg': '2.000'}

        self.client.post(url, payload)
        response = self.client.post(url, payload)

        self.assertRedirects(response, reverse('harvest_list'))
        self.assertEqual(InventoryMovement.objects.filter(harvest=self.harvest).count(), 1)

    def test_harvest_cannot_be_deleted_after_inventory_registration(self):
        self.register()

        with self.assertRaises(ProtectedError):
            self.harvest.delete()

    def test_failure_after_movement_write_rolls_back_inventory_confirmation(self):
        original_record_incoming = InventoryService.record_incoming

        def write_then_fail(*args, **kwargs):
            original_record_incoming(*args, **kwargs)
            raise RuntimeError('Fallo simulado durante la confirmación')

        with patch('agriculture.services.InventoryService.record_incoming', side_effect=write_then_fail):
            with self.assertRaises(RuntimeError):
                self.register()

        self.assertTrue(Harvest.objects.filter(pk=self.harvest.pk).exists())
        self.assertFalse(InventoryMovement.objects.filter(harvest=self.harvest).exists())
