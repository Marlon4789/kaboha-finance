from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Farm(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='farms',
        verbose_name=_('propietario'),
    )
    name = models.CharField(_('nombre'), max_length=160)
    code = models.CharField(_('código'), max_length=40, blank=True)
    department = models.CharField(_('departamento'), max_length=100, blank=True)
    municipality = models.CharField(_('municipio'), max_length=100, blank=True)
    address = models.CharField(_('dirección'), max_length=250, blank=True)
    total_area_ha = models.DecimalField(
        _('área total (ha)'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    notes = models.TextField(_('observaciones'), blank=True)
    active = models.BooleanField(_('activa'), default=True)
    created_at = models.DateTimeField(_('creada'), auto_now_add=True)
    updated_at = models.DateTimeField(_('actualizada'), auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('finca')
        verbose_name_plural = _('fincas')
        constraints = [
            models.CheckConstraint(
                condition=Q(total_area_ha__isnull=True) | Q(total_area_ha__gt=0),
                name='agri_farm_area_positive_if_set',
            ),
        ]

    def __str__(self):
        return self.name


class Lot(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Activo')
        FALLOW = 'FALLOW', _('En descanso')
        RETIRED = 'RETIRED', _('Retirado')

    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name='lots',
        verbose_name=_('finca'),
    )
    code = models.CharField(_('código'), max_length=40)
    name = models.CharField(_('nombre'), max_length=120)
    area_ha = models.DecimalField(
        _('área (ha)'),
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    current_tree_count = models.PositiveIntegerField(
        _('árboles actuales'),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    status = models.CharField(
        _('estado'),
        max_length=8,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    notes = models.TextField(_('observaciones'), blank=True)
    created_at = models.DateTimeField(_('creado'), auto_now_add=True)
    updated_at = models.DateTimeField(_('actualizado'), auto_now=True)

    class Meta:
        ordering = ['farm__name', 'code']
        verbose_name = _('lote')
        verbose_name_plural = _('lotes')
        constraints = [
            models.UniqueConstraint(fields=['farm', 'code'], name='agri_lot_farm_code_unique'),
            models.CheckConstraint(condition=Q(area_ha__gt=0), name='agri_lot_area_positive'),
            models.CheckConstraint(
                condition=Q(current_tree_count__isnull=True) | Q(current_tree_count__gt=0),
                name='agri_lot_tree_count_positive_if_set',
            ),
        ]

    def __str__(self):
        return f'{self.farm.name} - {self.code}: {self.name}'


class CropCycle(models.Model):
    class CycleType(models.TextChoices):
        NEW = 'NEW', _('Establecimiento nuevo')
        RENEWAL = 'RENEWAL', _('Renovación')
        SOCA = 'SOCA', _('Soca')
        REPLANTING = 'REPLANTING', _('Resiembra')
        OTHER = 'OTHER', _('Otro')

    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name='crop_cycles',
        verbose_name=_('lote'),
    )
    cycle_type = models.CharField(
        _('tipo de ciclo'),
        max_length=10,
        choices=CycleType.choices,
    )
    start_date = models.DateField(_('fecha de inicio'))
    end_date = models.DateField(_('fecha de finalización'), null=True, blank=True)
    planted_tree_count = models.PositiveIntegerField(
        _('árboles establecidos'),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    notes = models.TextField(_('observaciones'), blank=True)
    created_at = models.DateTimeField(_('creado'), auto_now_add=True)

    class Meta:
        ordering = ['-start_date', 'lot__code']
        verbose_name = _('ciclo de cultivo')
        verbose_name_plural = _('ciclos de cultivo')
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')),
                name='agri_cycle_end_on_or_after_start',
            ),
            models.CheckConstraint(
                condition=Q(planted_tree_count__isnull=True) | Q(planted_tree_count__gt=0),
                name='agri_cycle_tree_count_positive_if_set',
            ),
            models.UniqueConstraint(
                fields=['lot'],
                condition=Q(end_date__isnull=True),
                name='agri_cycle_one_open_per_lot',
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': _('La fecha final no puede ser anterior a la fecha de inicio.')})

    def __str__(self):
        return f'{self.lot.code} - {self.get_cycle_type_display()} ({self.start_date})'


class AgriculturalActivity(models.Model):
    class ActivityType(models.TextChoices):
        FERTILIZATION = 'FERTILIZATION', _('Fertilización')
        WEEDING = 'WEEDING', _('Control de malezas')
        PRUNING = 'PRUNING', _('Poda')
        SPRAYING = 'SPRAYING', _('Aplicación')
        PEST_CONTROL = 'PEST_CONTROL', _('Control de plagas')
        DISEASE_CONTROL = 'DISEASE_CONTROL', _('Control de enfermedades')
        IRRIGATION = 'IRRIGATION', _('Riego')
        SOIL_MANAGEMENT = 'SOIL_MANAGEMENT', _('Manejo del suelo')
        PLANTING = 'PLANTING', _('Siembra')
        OTHER = 'OTHER', _('Otra actividad')

    crop_cycle = models.ForeignKey(
        CropCycle,
        on_delete=models.PROTECT,
        related_name='activities',
        verbose_name=_('ciclo de cultivo'),
    )
    activity_type = models.CharField(
        _('tipo de actividad'),
        max_length=20,
        choices=ActivityType.choices,
    )
    performed_on = models.DateField(_('fecha realizada'), default=timezone.localdate)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='responsible_agricultural_activities',
        verbose_name=_('responsable'),
        null=True,
        blank=True,
    )
    notes = models.TextField(_('observaciones'), blank=True)
    created_at = models.DateTimeField(_('creada'), auto_now_add=True)

    class Meta:
        ordering = ['-performed_on', '-created_at']
        verbose_name = _('actividad agrícola')
        verbose_name_plural = _('actividades agrícolas')

    def __str__(self):
        return f'{self.get_activity_type_display()} - {self.performed_on}'


class ActivityInput(models.Model):
    activity = models.ForeignKey(
        AgriculturalActivity,
        on_delete=models.PROTECT,
        related_name='inputs',
        verbose_name=_('actividad'),
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='agricultural_activity_inputs',
        verbose_name=_('producto'),
    )
    quantity = models.DecimalField(
        _('cantidad'),
        max_digits=18,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    notes = models.TextField(_('observaciones'), blank=True)
    created_at = models.DateTimeField(_('registrado'), auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        verbose_name = _('insumo de actividad')
        verbose_name_plural = _('insumos de actividad')
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='agri_activity_input_quantity_positive'),
        ]

    def __str__(self):
        return f'{self.product.name}: {self.quantity}'


class ActivityLabor(models.Model):
    activity = models.ForeignKey(
        AgriculturalActivity,
        on_delete=models.PROTECT,
        related_name='labor_records',
        verbose_name=_('actividad'),
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='agricultural_labor_records',
        verbose_name=_('trabajador con usuario'),
        null=True,
        blank=True,
    )
    worker_name = models.CharField(_('nombre del trabajador'), max_length=160, blank=True)
    hours = models.DecimalField(
        _('horas'),
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    hourly_rate = models.DecimalField(
        _('tarifa por hora (COP)'),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(_('observaciones'), blank=True)

    class Meta:
        ordering = ['pk']
        verbose_name = _('mano de obra de actividad')
        verbose_name_plural = _('mano de obra de actividades')
        constraints = [
            models.CheckConstraint(condition=Q(hours__gt=0), name='agri_labor_hours_positive'),
            models.CheckConstraint(condition=Q(hourly_rate__gte=0), name='agri_labor_hourly_rate_nonnegative'),
            models.CheckConstraint(
                condition=Q(performed_by__isnull=False) | ~Q(worker_name=''),
                name='agri_labor_has_worker_identifier',
            ),
        ]

    def clean(self):
        super().clean()
        self.worker_name = (self.worker_name or '').strip()
        if not self.performed_by_id and not self.worker_name:
            raise ValidationError({
                'worker_name': _('Indica un usuario trabajador o el nombre de la persona.'),
            })

    @property
    def analytical_cost(self):
        return self.hours * self.hourly_rate

    def __str__(self):
        worker = self.worker_name or str(self.performed_by)
        return f'{worker} - {self.hours} h'

class Harvest(models.Model):
    crop_cycle = models.ForeignKey(
        CropCycle,
        on_delete=models.PROTECT,
        related_name='harvests',
        verbose_name=_('ciclo de cultivo'),
    )
    harvested_on = models.DateField(_('fecha de cosecha'))
    notes = models.TextField(_('observaciones'), blank=True)
    created_at = models.DateTimeField(_('creada'), auto_now_add=True)

    class Meta:
        ordering = ['-harvested_on', '-created_at']
        verbose_name = _('cosecha')
        verbose_name_plural = _('cosechas')

    def __str__(self):
        return f'{self.crop_cycle} - {self.harvested_on}'


class ProductionBatch(models.Model):
    class ProcessType(models.TextChoices):
        BENEFIT = 'BENEFIT', _('Beneficio')
        DRYING = 'DRYING', _('Secado')
        MILLING = 'MILLING', _('Trilla')
        ROASTING = 'ROASTING', _('Tostión')
        GRINDING = 'GRINDING', _('Molienda')
        OTHER = 'OTHER', _('Otro')

    code = models.CharField(_('código'), max_length=40, unique=True)
    process_type = models.CharField(_('tipo de proceso'), max_length=10, choices=ProcessType.choices)
    started_at = models.DateTimeField(_('fecha y hora de inicio'))
    finished_at = models.DateTimeField(_('fecha y hora de finalización'), null=True, blank=True)
    notes = models.TextField(_('observaciones'), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='created_production_batches',
        verbose_name=_('creado por'),
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_('creado'), auto_now_add=True)

    class Meta:
        ordering = ['-started_at', 'code']
        verbose_name = _('lote de producción')
        verbose_name_plural = _('lotes de producción')
        constraints = [
            models.CheckConstraint(
                condition=Q(finished_at__isnull=True) | Q(finished_at__gte=F('started_at')),
                name='agri_batch_finish_on_or_after_start',
            ),
        ]

    def clean(self):
        super().clean()
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValidationError({
                'finished_at': _('La fecha final no puede ser anterior a la fecha de inicio.'),
            })

    def __str__(self):
        return f'{self.code} - {self.get_process_type_display()}'


class QualityAssessment(models.Model):
    production_batch = models.ForeignKey(
        ProductionBatch,
        on_delete=models.PROTECT,
        related_name='quality_assessments',
        verbose_name=_('lote de producción'),
    )
    assessed_on = models.DateField(_('fecha de evaluación'))
    # The unit, scale, interpretation and ranges for factor have not been defined yet.
    factor = models.DecimalField(_('factor'), max_digits=12, decimal_places=4, null=True, blank=True)
    moisture_pct = models.DecimalField(
        _('humedad (%)'), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    defects_pct = models.DecimalField(
        _('defectos (%)'), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    broca_pct = models.DecimalField(
        _('broca (%)'), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    # Score is stored as reported; no score scale or automatic calculation is defined.
    score = models.DecimalField(_('calificación'), max_digits=12, decimal_places=4, null=True, blank=True)
    notes = models.TextField(_('observaciones'), blank=True)

    class Meta:
        ordering = ['-assessed_on', '-pk']
        verbose_name = _('evaluación de calidad')
        verbose_name_plural = _('evaluaciones de calidad')
        constraints = [
            models.CheckConstraint(
                condition=Q(moisture_pct__isnull=True) | Q(moisture_pct__gte=0, moisture_pct__lte=100),
                name='agri_quality_moisture_pct_range',
            ),
            models.CheckConstraint(
                condition=Q(defects_pct__isnull=True) | Q(defects_pct__gte=0, defects_pct__lte=100),
                name='agri_quality_defects_pct_range',
            ),
            models.CheckConstraint(
                condition=Q(broca_pct__isnull=True) | Q(broca_pct__gte=0, broca_pct__lte=100),
                name='agri_quality_broca_pct_range',
            ),
        ]

    def __str__(self):
        return f'{self.production_batch.code} - {self.assessed_on}'
