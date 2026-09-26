from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from products.models import Product

from .models import (
    AgriculturalActivity, ActivityInput, ActivityLabor, CropCycle, Farm, Harvest, Lot,
    ProductionBatch, QualityAssessment,
)


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


class AgriculturalActivityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='activity-user', password='test-password')
        self.farm = Farm.objects.create(owner=self.user, name='Finca Actividades')
        self.lot = Lot.objects.create(farm=self.farm, code='ACT-01', name='Lote Actividades', area_ha=Decimal('1.2500'))
        self.cycle = CropCycle.objects.create(
            lot=self.lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date='2024-01-01',
        )
        self.product = Product.objects.create(
            name='Fertilizante prueba',
            description='',
            weight_grams=1000,
            sale_price=10000,
            production_cost=5000,
        )

    def test_activity_creation_cycle_type_date_and_optional_responsible(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.FERTILIZATION,
            performed_on='2024-03-10',
        )

        self.assertEqual(activity.crop_cycle, self.cycle)
        self.assertEqual(self.cycle.activities.get(), activity)
        self.assertEqual(activity.get_activity_type_display(), 'Fertilización')
        self.assertEqual(str(activity.performed_on), '2024-03-10')
        self.assertIsNone(activity.responsible)

    def test_activity_responsible_user_is_optional_and_supported(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.PRUNING,
            responsible=self.user,
        )

        self.assertEqual(activity.responsible, self.user)
        self.assertEqual(self.user.responsible_agricultural_activities.get(), activity)

    def test_invalid_activity_type_is_rejected_by_model_validation(self):
        activity = AgriculturalActivity(
            crop_cycle=self.cycle,
            activity_type='NOT_A_VALID_TYPE',
            performed_on='2024-03-10',
        )

        with self.assertRaises(ValidationError):
            activity.full_clean()

    def test_activity_input_creation_and_relations(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.FERTILIZATION,
        )
        activity_input = ActivityInput.objects.create(
            activity=activity,
            product=self.product,
            quantity=Decimal('20.500'),
            notes='Aplicación registrada',
        )

        self.assertEqual(activity_input.activity, activity)
        self.assertEqual(activity_input.product, self.product)
        self.assertEqual(activity.inputs.get(), activity_input)
        self.assertEqual(self.product.agricultural_activity_inputs.get(), activity_input)
        self.assertEqual(activity_input.quantity, Decimal('20.500'))

    def test_activity_input_quantity_must_be_positive(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.WEEDING,
        )
        invalid_input = ActivityInput(activity=activity, product=self.product, quantity=Decimal('0'))

        with self.assertRaises(ValidationError):
            invalid_input.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ActivityInput.objects.create(activity=activity, product=self.product, quantity=Decimal('0'))

    def test_activity_labor_can_identify_worker_by_user(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.PRUNING,
        )
        labor = ActivityLabor.objects.create(
            activity=activity,
            performed_by=self.user,
            hours=Decimal('3.00'),
            hourly_rate=Decimal('8000.00'),
        )

        self.assertEqual(labor.performed_by, self.user)
        self.assertEqual(activity.labor_records.get(), labor)
        self.assertEqual(labor.analytical_cost, Decimal('24000.0000'))

    def test_activity_labor_can_identify_worker_by_name(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.WEEDING,
        )
        labor = ActivityLabor.objects.create(
            activity=activity,
            worker_name='María Gómez',
            hours=Decimal('2.50'),
            hourly_rate=Decimal('7000.00'),
        )

        self.assertEqual(labor.worker_name, 'María Gómez')
        self.assertEqual(labor.analytical_cost, Decimal('17500.0000'))

    def test_activity_labor_rejects_missing_worker_identifier(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.IRRIGATION,
        )
        labor = ActivityLabor(
            activity=activity,
            hours=Decimal('1.00'),
            hourly_rate=Decimal('0.00'),
        )

        with self.assertRaises(ValidationError):
            labor.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ActivityLabor.objects.create(
                    activity=activity,
                    hours=Decimal('1.00'),
                    hourly_rate=Decimal('0.00'),
                )

    def test_activity_labor_rejects_nonpositive_hours_and_negative_rate(self):
        activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle,
            activity_type=AgriculturalActivity.ActivityType.OTHER,
        )
        invalid_hours = ActivityLabor(
            activity=activity,
            worker_name='Trabajador',
            hours=Decimal('0'),
            hourly_rate=Decimal('0'),
        )
        with self.assertRaises(ValidationError):
            invalid_hours.full_clean()

        invalid_rate = ActivityLabor(
            activity=activity,
            worker_name='Trabajador',
            hours=Decimal('1'),
            hourly_rate=Decimal('-1'),
        )
        with self.assertRaises(ValidationError):
            invalid_rate.full_clean()

class HarvestProductionQualityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='phase4-user', password='test-password')
        self.farm = Farm.objects.create(owner=self.user, name='Finca Fase 4')
        self.lot = Lot.objects.create(farm=self.farm, code='P4-01', name='Lote Fase 4', area_ha=Decimal('1.0000'))
        self.cycle = CropCycle.objects.create(
            lot=self.lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date='2024-01-01',
        )

    def create_batch(self, code='PB-000001', **kwargs):
        from django.utils import timezone
        from datetime import datetime

        defaults = {
            'process_type': ProductionBatch.ProcessType.BENEFIT,
            'started_at': timezone.make_aware(datetime(2024, 10, 1, 8, 0)),
            'created_by': self.user,
        }
        defaults.update(kwargs)
        return ProductionBatch.objects.create(code=code, **defaults)

    def test_harvest_creation_date_and_crop_cycle_relation(self):
        harvest = Harvest.objects.create(crop_cycle=self.cycle, harvested_on='2024-10-10', notes='Corte principal')

        self.assertEqual(harvest.crop_cycle, self.cycle)
        self.assertEqual(self.cycle.harvests.get(), harvest)
        self.assertEqual(str(harvest.harvested_on), '2024-10-10')
        self.assertTrue(hasattr(harvest, 'created_at'))
        self.assertNotIn('quantity', {field.name for field in Harvest._meta.fields})

    def test_multiple_harvests_can_belong_to_one_crop_cycle(self):
        first = Harvest.objects.create(crop_cycle=self.cycle, harvested_on='2024-10-10')
        second = Harvest.objects.create(crop_cycle=self.cycle, harvested_on='2024-10-20')

        self.assertEqual(self.cycle.harvests.count(), 2)
        self.assertNotEqual(first.pk, second.pk)

    def test_crop_cycle_deletion_is_protected_by_harvest(self):
        Harvest.objects.create(crop_cycle=self.cycle, harvested_on='2024-10-10')

        with self.assertRaises(ProtectedError):
            self.cycle.delete()

    def test_production_batch_creation_and_optional_fields(self):
        batch = self.create_batch(finished_at=None)

        self.assertEqual(batch.code, 'PB-000001')
        self.assertEqual(batch.process_type, ProductionBatch.ProcessType.BENEFIT)
        self.assertEqual(batch.created_by, self.user)
        self.assertIsNone(batch.finished_at)

    def test_production_batch_code_is_unique(self):
        self.create_batch()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_batch(code='PB-000001')

    def test_all_production_batch_process_types_are_valid_choices(self):
        for index, process_type in enumerate(ProductionBatch.ProcessType.values, start=1):
            with self.subTest(process_type=process_type):
                batch = self.create_batch(code=f'PB-{index:06d}', process_type=process_type)
                self.assertEqual(batch.process_type, process_type)

        invalid_batch = ProductionBatch(
            code='PB-INVALID',
            process_type='NOT_A_PROCESS',
            started_at=self.create_batch(code='PB-TEMP').started_at,
        )
        with self.assertRaises(ValidationError):
            invalid_batch.full_clean()

    def test_production_batch_finish_date_must_not_precede_start(self):
        from datetime import datetime
        from django.utils import timezone

        invalid_batch = ProductionBatch(
            code='PB-INVALID-DATE',
            process_type=ProductionBatch.ProcessType.DRYING,
            started_at=timezone.make_aware(datetime(2024, 10, 2, 8, 0)),
            finished_at=timezone.make_aware(datetime(2024, 10, 2, 7, 59)),
        )
        with self.assertRaises(ValidationError):
            invalid_batch.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                invalid_batch.save()

    def test_different_production_batches_are_independent(self):
        first = self.create_batch(code='PB-000001')
        second = self.create_batch(code='PB-000002', process_type=ProductionBatch.ProcessType.DRYING)

        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.code, second.code)

    def test_quality_assessment_relates_to_batch_and_accepts_optional_values(self):
        batch = self.create_batch()
        assessment = QualityAssessment.objects.create(production_batch=batch, assessed_on='2024-10-12')

        self.assertEqual(assessment.production_batch, batch)
        self.assertEqual(batch.quality_assessments.get(), assessment)
        self.assertIsNone(assessment.factor)
        self.assertIsNone(assessment.score)

    def test_quality_percentages_accept_zero_and_one_hundred(self):
        batch = self.create_batch()
        assessment = QualityAssessment.objects.create(
            production_batch=batch,
            assessed_on='2024-10-12',
            moisture_pct=Decimal('0'),
            defects_pct=Decimal('100'),
            broca_pct=Decimal('25.50'),
        )

        self.assertEqual(assessment.moisture_pct, Decimal('0.00'))
        self.assertEqual(assessment.defects_pct, Decimal('100.00'))
        self.assertEqual(assessment.broca_pct, Decimal('25.50'))

    def test_quality_percentages_outside_range_are_invalid(self):
        batch = self.create_batch()
        for field_name in ('moisture_pct', 'defects_pct', 'broca_pct'):
            for value in (Decimal('-0.01'), Decimal('100.01')):
                with self.subTest(field=field_name, value=value):
                    assessment = QualityAssessment(
                        production_batch=batch,
                        assessed_on='2024-10-12',
                        **{field_name: value},
                    )
                    with self.assertRaises(ValidationError):
                        assessment.full_clean()
                    with self.assertRaises(IntegrityError):
                        with transaction.atomic():
                            assessment.save()

    def test_multiple_quality_assessments_can_belong_to_one_batch(self):
        batch = self.create_batch()
        first = QualityAssessment.objects.create(production_batch=batch, assessed_on='2024-10-12')
        second = QualityAssessment.objects.create(production_batch=batch, assessed_on='2024-10-13')

        self.assertEqual(batch.quality_assessments.count(), 2)
        self.assertNotEqual(first.pk, second.pk)

    def test_batch_deletion_is_protected_by_quality_assessment(self):
        batch = self.create_batch()
        QualityAssessment.objects.create(production_batch=batch, assessed_on='2024-10-12')

        with self.assertRaises(ProtectedError):
            batch.delete()
