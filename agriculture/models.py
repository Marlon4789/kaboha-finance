from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
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
