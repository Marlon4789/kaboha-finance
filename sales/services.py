"""Atomic application service for sales that consume operational inventory."""

from datetime import date, datetime, time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from inventory.models import InventoryMovement
from inventory.services import InsufficientStockError, InventoryOperationError, InventoryService
from products.models import Product
from sales.models import Sale, SaleItem


class SalesOperationError(ValueError):
    """Raised when a sale cannot be posted to operational inventory."""


class SaleIdempotencyConflictError(SalesOperationError):
    """Raised when an operation key identifies a different sale."""


class SaleBeforeCutoverError(SalesOperationError):
    """Raised when an operational sale predates the approved ledger cutover."""


class SalesService:
    CUTOVER_DATE = date(2026, 9, 18)

    @classmethod
    def _validate_sale_data(cls, sale_data, operation_key):
        if not operation_key or not str(operation_key).strip():
            raise SalesOperationError('Las ventas operativas requieren una clave de operación.')
        if len(str(operation_key)) > Sale._meta.get_field('operation_key').max_length:
            raise SalesOperationError('La clave de operación excede la longitud permitida.')
        sale_date = sale_data.get('sale_date')
        if not isinstance(sale_date, date):
            raise SalesOperationError('La fecha de venta no es válida.')
        if sale_date < cls.CUTOVER_DATE:
            raise SaleBeforeCutoverError(
                'No se pueden registrar ventas operativas anteriores al corte del 2026-09-18.',
            )
        payment_method = sale_data.get('payment_method')
        if payment_method not in dict(Sale.PAYMENT_METHODS):
            raise SalesOperationError('El medio de pago no es válido.')

    @staticmethod
    def _line_value(line, field):
        return line.get(field) if isinstance(line, dict) else getattr(line, field, None)

    @classmethod
    def _normalize_lines(cls, lines):
        normalized = []
        for position, line in enumerate(lines, start=1):
            product = cls._line_value(line, 'product')
            quantity = cls._line_value(line, 'quantity')
            unit_price = cls._line_value(line, 'unit_price')
            product_id = getattr(product, 'pk', product)
            if product_id is None:
                raise SalesOperationError(f'La línea {position} requiere un producto guardado.')
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                raise SalesOperationError(f'La cantidad de la línea {position} debe ser un entero positivo.')
            try:
                unit_price = SaleItem._meta.get_field('unit_price').clean(unit_price, None)
            except ValidationError as exc:
                raise SalesOperationError(f'El precio unitario de la línea {position} no es válido.') from exc
            normalized.append({
                'position': position,
                'product_id': product_id,
                'quantity': quantity,
                'unit_price': unit_price,
            })
        if not normalized:
            raise SalesOperationError('Una venta operativa debe tener al menos un ítem.')
        return normalized

    @classmethod
    def _validate_products(cls, lines, *, lock):
        product_ids = sorted({line['product_id'] for line in lines})
        queryset = Product.objects.select_for_update() if lock else Product.objects
        products = {product.pk: product for product in queryset.filter(pk__in=product_ids).order_by('pk')}
        if len(products) != len(product_ids):
            raise SalesOperationError('Uno de los productos de la venta ya no existe.')
        for line in lines:
            product = products[line['product_id']]
            if not product.is_sellable:
                raise SalesOperationError(f'El producto {product.name} no está habilitado para venta.')
            if not product.is_stock_tracked:
                raise SalesOperationError(f'El producto {product.name} no controla inventario.')
            if product.base_unit not in Product.BaseUnit.values:
                raise SalesOperationError(f'El producto {product.name} no tiene una unidad base válida.')
            if product.sale_unit_quantity is None or product.sale_unit_quantity <= 0:
                raise SalesOperationError(f'El producto {product.name} no tiene contenido comercial válido.')
        return products

    @staticmethod
    def _canonical_header(sale_date, customer_name, payment_method, notes):
        return (sale_date, customer_name or '', payment_method, notes or '')

    @classmethod
    def _matches_existing(cls, sale, sale_data, lines):
        if cls._canonical_header(
            sale.sale_date, sale.customer_name, sale.payment_method, sale.notes,
        ) != cls._canonical_header(
            sale_data['sale_date'], sale_data.get('customer_name'),
            sale_data['payment_method'], sale_data.get('notes'),
        ):
            return False
        existing_lines = sorted(
            sale.items.values_list('product_id', 'quantity', 'unit_price'),
        )
        requested_lines = sorted(
            (line['product_id'], line['quantity'], line['unit_price']) for line in lines
        )
        return existing_lines == requested_lines

    @classmethod
    def _existing_or_conflict(cls, operation_key, sale_data, lines):
        sale = Sale.objects.filter(operation_key=operation_key).first()
        if sale is None:
            return None
        if cls._matches_existing(sale, sale_data, lines):
            return sale
        raise SaleIdempotencyConflictError(
            f'La clave de operación {operation_key!r} ya representa una venta diferente.',
        )

    @staticmethod
    def _occurred_at(sale_date):
        return timezone.make_aware(
            datetime.combine(sale_date, time.min), timezone.get_current_timezone(),
        )

    @classmethod
    @transaction.atomic
    def create_integrated_sale(cls, sale_data, lines, *, operation_key, actor=None):
        """Create one sale and its FIFO SALE_OUT rows, or roll back all writes."""
        operation_key = str(operation_key).strip()
        cls._validate_sale_data(sale_data, operation_key)
        normalized_lines = cls._normalize_lines(lines)

        existing = cls._existing_or_conflict(operation_key, sale_data, normalized_lines)
        if existing is not None:
            return existing, False

        # All locks are acquired in the same product-primary-key order before any
        # sale row is written, avoiding multi-product lock inversion.
        products = cls._validate_products(normalized_lines, lock=True)

        try:
            # The savepoint isolates only the expected unique-key race. Any other
            # IntegrityError is re-raised unchanged.
            with transaction.atomic():
                sale = Sale.objects.create(
                    sale_date=sale_data['sale_date'],
                    customer_name=sale_data.get('customer_name') or None,
                    payment_method=sale_data['payment_method'],
                    notes=sale_data.get('notes') or '',
                    operation_key=operation_key,
                )
        except IntegrityError:
            existing = cls._existing_or_conflict(operation_key, sale_data, normalized_lines)
            if existing is not None:
                return existing, False
            raise

        occurred_at = cls._occurred_at(sale.sale_date)
        created_items = []
        for line in normalized_lines:
            item = SaleItem(
                sale=sale,
                product=products[line['product_id']],
                quantity=line['quantity'],
                unit_price=line['unit_price'],
            )
            # SaleItem.save fixes the snapshot from the current product catalog;
            # callers cannot supply an alternate snapshot through this service.
            item.save(force_insert=True)
            created_items.append(item)

        for item in sorted(created_items, key=lambda row: (row.product_id, row.pk)):
            quantity_base = item.quantity * item.unit_quantity_base_snapshot
            try:
                InventoryService.consume(
                    item.product,
                    quantity_base,
                    movement_type=InventoryMovement.MovementType.SALE_OUT,
                    occurred_at=occurred_at,
                    created_by=actor,
                    context={'sale_item': item},
                )
            except InsufficientStockError:
                raise
            except InventoryOperationError as exc:
                raise SalesOperationError(str(exc)) from exc
        return sale, True
