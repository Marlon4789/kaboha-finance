"""Explicit, repeatable cutover from the legacy aggregate inventory."""

from datetime import datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from inventory.models import InventoryMovement
from inventory.services import InventoryService
from products.models import Product


class LegacyInventoryCutoverError(ValueError):
    """Raised when the approved legacy-inventory cutover cannot be applied."""


class LegacyInventoryCutoverConflictError(LegacyInventoryCutoverError):
    """Raised when an existing idempotency key does not represent this cutover."""


class LegacyInventoryCutoverService:
    CUTOVER_DATE = datetime(2026, 9, 18).date()
    TRADITIONAL_NAME = 'Café tradicional'
    PARCHMENT_NAME = 'Café pergamino'
    NOTE = (
        'Saldo físico verificado en el corte del inventario legado del 2026-09-18; '
        'no representa una reconstrucción de la trazabilidad histórica.'
    )
    BALANCES = (
        (TRADITIONAL_NAME, Product.CoffeeStage.GROUND, Decimal('2000.000'),
         'legacy-cutoff:2026-09-18:cafe-tradicional'),
        (PARCHMENT_NAME, Product.CoffeeStage.PARCHMENT, Decimal('13000.000'),
         'legacy-cutoff:2026-09-18:cafe-pergamino'),
    )

    @classmethod
    def occurred_at(cls):
        return timezone.make_aware(
            datetime.combine(cls.CUTOVER_DATE, time.min), timezone.get_current_timezone(),
        )

    @classmethod
    def _validate_product(cls, product, *, stage, sellable):
        expected = {
            'item_type': Product.ItemType.COFFEE,
            'coffee_stage': stage,
            'base_unit': Product.BaseUnit.G,
            'is_stock_tracked': True,
            'is_sellable': sellable,
        }
        mismatches = [field for field, value in expected.items() if getattr(product, field) != value]
        if mismatches:
            names = ', '.join(mismatches)
            raise LegacyInventoryCutoverError(
                f'El producto {product.name!r} no cumple el corte aprobado: {names}.',
            )
        try:
            product.full_clean()
        except ValidationError as exc:
            raise LegacyInventoryCutoverError(' '.join(exc.messages)) from exc

    @classmethod
    def _traditional_product(cls, *, lock):
        queryset = Product.objects.select_for_update() if lock else Product.objects
        try:
            product = queryset.get(name=cls.TRADITIONAL_NAME)
        except Product.DoesNotExist as exc:
            raise LegacyInventoryCutoverError(
                f'No existe el producto requerido {cls.TRADITIONAL_NAME!r}.',
            ) from exc
        except Product.MultipleObjectsReturned as exc:
            raise LegacyInventoryCutoverError(
                f'Hay más de un producto llamado {cls.TRADITIONAL_NAME!r}; resuélvelo antes del corte.',
            ) from exc

        product.is_stock_tracked = True
        cls._validate_product(product, stage=Product.CoffeeStage.GROUND, sellable=True)
        return product

    @classmethod
    def _parchment_product(cls, *, lock, create):
        queryset = Product.objects.select_for_update() if lock else Product.objects
        matches = queryset.filter(name=cls.PARCHMENT_NAME)
        if matches.count() > 1:
            raise LegacyInventoryCutoverError(
                f'Hay más de un producto llamado {cls.PARCHMENT_NAME!r}; resuélvelo antes del corte.',
            )
        product = matches.first()
        if product is None:
            product = Product(
                name=cls.PARCHMENT_NAME,
                item_type=Product.ItemType.COFFEE,
                coffee_stage=Product.CoffeeStage.PARCHMENT,
                base_unit=Product.BaseUnit.G,
                is_stock_tracked=True,
                is_sellable=False,
                production_cost=None,
            )
            cls._validate_product(product, stage=Product.CoffeeStage.PARCHMENT, sellable=False)
            if create:
                product.save(force_insert=True)
            return product

        cls._validate_product(product, stage=Product.CoffeeStage.PARCHMENT, sellable=False)
        return product

    @classmethod
    def _matches_balance(cls, movement, *, product, quantity, operation_key):
        return (
            movement.product_id == product.pk
            and movement.movement_type == InventoryMovement.MovementType.OPENING_BALANCE_IN
            and movement.quantity == quantity
            and movement.occurred_at == cls.occurred_at()
            and movement.unit_cost is None
            and movement.operation_key == operation_key
            and movement.notes == cls.NOTE
            and movement.source_movement_id is None
        )

    @classmethod
    def _record_balance(cls, product, quantity, operation_key):
        existing = InventoryMovement.objects.filter(operation_key=operation_key).first()
        if existing:
            if cls._matches_balance(existing, product=product, quantity=quantity, operation_key=operation_key):
                return existing, False
            raise LegacyInventoryCutoverConflictError(
                f'La clave {operation_key!r} ya existe con datos distintos.',
            )

        try:
            # A savepoint keeps the outer cutover transaction usable only for a
            # concurrent unique-key collision; all other database errors propagate.
            with transaction.atomic():
                movement = InventoryService.record_incoming(
                    product,
                    quantity,
                    movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
                    occurred_at=cls.occurred_at(),
                    unit_cost=None,
                    notes=cls.NOTE,
                    operation_key=operation_key,
                )
                return movement, True
        except IntegrityError:
            existing = InventoryMovement.objects.filter(operation_key=operation_key).first()
            if existing and cls._matches_balance(
                existing, product=product, quantity=quantity, operation_key=operation_key,
            ):
                return existing, False
            if existing:
                raise LegacyInventoryCutoverConflictError(
                    f'La clave {operation_key!r} ya existe con datos distintos.',
                )
            raise

    @classmethod
    def preview(cls):
        """Validate the cutover without creating products or movements."""
        traditional = cls._traditional_product(lock=False)
        parchment = cls._parchment_product(lock=False, create=False)
        products = {traditional.name: traditional, parchment.name: parchment}
        results = []
        for name, _stage, quantity, operation_key in cls.BALANCES:
            existing = InventoryMovement.objects.filter(operation_key=operation_key).first()
            if existing:
                if not cls._matches_balance(
                    existing, product=products[name], quantity=quantity, operation_key=operation_key,
                ):
                    raise LegacyInventoryCutoverConflictError(
                        f'La clave {operation_key!r} ya existe con datos distintos.',
                    )
                results.append((existing, False))
            else:
                results.append((name, True))
        return results

    @classmethod
    @transaction.atomic
    def apply(cls):
        # Locking the existing traditional product serializes the cutover, including
        # creation of the otherwise non-unique parchment catalog row.
        traditional = cls._traditional_product(lock=True)
        if not traditional.is_stock_tracked:
            # Kept for clarity; _traditional_product sets it before validation.
            traditional.is_stock_tracked = True
        traditional.save(update_fields=['is_stock_tracked', 'updated_at'])
        parchment = cls._parchment_product(lock=True, create=True)
        products = {traditional.name: traditional, parchment.name: parchment}

        results = []
        for name, _stage, quantity, operation_key in cls.BALANCES:
            results.append(cls._record_balance(products[name], quantity, operation_key))
        return results
