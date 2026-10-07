"""Read-only traceability from a sale item back to its agricultural origin.

Nothing is stored. The chain is derived from InventoryMovement:
SALE_OUT.source_movement -> layer -> (TRANSFORMATION_IN -> batch -> its TRANSFORMATION_OUT
rows -> earlier layers ...) -> HARVEST_IN.harvest -> crop cycle -> lot -> farm.
A layer with another origin (opening balance, purchase, adjustment) or a sale without
inventory movements is reported as unknown, never silently dropped.
"""

from dataclasses import dataclass
from decimal import Decimal

from inventory.models import InventoryMovement

MAX_STAGES = 20


@dataclass(frozen=True)
class OriginShare:
    # Fraction (0..1) of the traced quantity that comes from this origin.
    share: Decimal
    # Batch codes crossed from the sold layer back to the origin, sale side first.
    batch_codes: tuple
    harvest: object = None
    reason: str = ''

    @property
    def is_known(self):
        return self.harvest is not None

    @property
    def crop_cycle(self):
        return self.harvest.crop_cycle if self.harvest else None

    @property
    def lot(self):
        return self.crop_cycle.lot if self.harvest else None

    @property
    def farm(self):
        return self.lot.farm if self.harvest else None


def _expand_layer(layer, weight, batch_codes, depth):
    Type = InventoryMovement.MovementType
    if layer.movement_type == Type.HARVEST_IN and layer.harvest_id:
        return [OriginShare(weight, batch_codes, harvest=layer.harvest)]
    if layer.movement_type == Type.TRANSFORMATION_IN and layer.production_batch_id and depth < MAX_STAGES:
        batch = layer.production_batch
        inputs = list(
            InventoryMovement.objects.filter(production_batch=batch, movement_type=Type.TRANSFORMATION_OUT)
            .select_related('source_movement', 'source_movement__harvest__crop_cycle__lot__farm',
                            'source_movement__production_batch'),
        )
        total = sum((row.quantity for row in inputs), Decimal('0'))
        if inputs and total > 0:
            shares = []
            for row in inputs:
                shares.extend(_expand_layer(
                    row.source_movement, weight * row.quantity / total, batch_codes + (batch.code,), depth + 1,
                ))
            return shares
        return [OriginShare(weight, batch_codes + (batch.code,), reason='El lote de producción no registra sus entradas.')]
    label = layer.get_movement_type_display()
    return [OriginShare(weight, batch_codes, reason=f'Entrada sin origen agrícola: {label}.')]


def trace_sale_item(sale_item):
    """Return the OriginShare list for a SaleItem; shares always add up to 1."""
    sold = list(
        InventoryMovement.objects.filter(
            sale_item=sale_item, movement_type=InventoryMovement.MovementType.SALE_OUT,
        ).select_related(
            'source_movement', 'source_movement__harvest__crop_cycle__lot__farm',
            'source_movement__production_batch',
        ),
    )
    total = sum((row.quantity for row in sold), Decimal('0'))
    if not sold or total <= 0:
        return [OriginShare(
            Decimal('1'), (), reason='La venta no tiene movimientos de inventario (anterior al corte).',
        )]
    shares = []
    for row in sold:
        shares.extend(_expand_layer(row.source_movement, row.quantity / total, (), 0))
    return shares
