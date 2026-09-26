from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import CropCycle, Farm, Lot


class AgriculturalCoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='farm-owner', password='test-password')

    def create_farm(self, name='Finca Central', **kwargs):
        return Farm.objects.create(owner=self.user, name=name, **kwargs)

    def create_lot(self, farm=None, **kwargs):
        farm = farm or self.create_farm()
        return Lot.objects.create(
            farm=farm,
            code=kwargs.pop('code', 'L-01'),
            name=kwargs.pop('name', 'Lote Norte'),
            area_ha=kwargs.pop('area_ha', Decimal('2.5000')),
            **kwargs,
        )

    def test_farm_creation_and_owner_relation(self):
        farm = self.create_farm(total_area_ha=Decimal('5.2500'))

        self.assertEqual(farm.owner, self.user)
        self.assertEqual(self.user.farms.get(), farm)
        self.assertEqual(farm.total_area_ha, Decimal('5.2500'))
        self.assertTrue(farm.active)

    def test_farm_area_must_be_positive_when_provided(self):
        farm = Farm(owner=self.user, name='Finca inválida', total_area_ha=Decimal('0'))

        with self.assertRaises(ValidationError):
            farm.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Farm.objects.create(owner=self.user, name='Finca inválida', total_area_ha=Decimal('0'))

    def test_lot_belongs_to_farm_and_area_is_positive(self):
        farm = self.create_farm()
        lot = self.create_lot(farm=farm)

        self.assertEqual(lot.farm, farm)
        self.assertEqual(farm.lots.get(), lot)

        invalid_lot = Lot(farm=farm, code='L-02', name='Área cero', area_ha=Decimal('0'))
        with self.assertRaises(ValidationError):
            invalid_lot.full_clean()

    def test_lot_code_is_unique_within_farm(self):
        farm = self.create_farm()
        self.create_lot(farm=farm, code='L-01')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_lot(farm=farm, code='L-01', name='Duplicado')

    def test_same_lot_code_is_allowed_in_another_farm(self):
        first = self.create_farm(name='Finca Uno')
        second = self.create_farm(name='Finca Dos')

        self.create_lot(farm=first, code='L-01')
        other_lot = self.create_lot(farm=second, code='L-01', name='Otro lote')

        self.assertEqual(other_lot.code, 'L-01')
        self.assertEqual(Lot.objects.filter(code='L-01').count(), 2)

    def test_crop_cycle_creation_and_lot_relation(self):
        lot = self.create_lot()
        cycle = CropCycle.objects.create(
            lot=lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date='2024-01-15',
            planted_tree_count=1200,
        )

        self.assertEqual(cycle.lot, lot)
        self.assertEqual(lot.crop_cycles.get(), cycle)
        self.assertEqual(cycle.planted_tree_count, 1200)

    def test_crop_cycle_end_date_cannot_precede_start_date(self):
        cycle = CropCycle(
            lot=self.create_lot(),
            cycle_type=CropCycle.CycleType.RENEWAL,
            start_date='2024-02-01',
            end_date='2024-01-31',
        )

        with self.assertRaises(ValidationError):
            cycle.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                cycle.save()

    def test_only_one_open_cycle_is_allowed_per_lot(self):
        lot = self.create_lot()
        CropCycle.objects.create(lot=lot, cycle_type=CropCycle.CycleType.NEW, start_date='2020-01-01')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CropCycle.objects.create(lot=lot, cycle_type=CropCycle.CycleType.SOCA, start_date='2024-01-01')

    def test_multiple_closed_historical_cycles_are_allowed(self):
        lot = self.create_lot()
        first = CropCycle.objects.create(
            lot=lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date='2010-01-01',
            end_date='2018-12-31',
        )
        second = CropCycle.objects.create(
            lot=lot,
            cycle_type=CropCycle.CycleType.RENEWAL,
            start_date='2019-01-01',
            end_date='2023-12-31',
        )

        self.assertEqual(lot.crop_cycles.count(), 2)
        self.assertIsNotNone(first.end_date)
        self.assertIsNotNone(second.end_date)
