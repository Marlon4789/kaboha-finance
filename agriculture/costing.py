"""Read-only cost derivations for agricultural activities, cycles and lots.

Nothing here is stored. Labor comes from ActivityLabor (hours x rate) and input cost
from the AGRICULTURAL_CONSUMPTION_OUT movements of each ActivityInput, whose unit_cost
is the real cost of the consumed layer. Expense is deliberately not read: it is the cash
outflow of the same money, so adding it would double count. An unknown cost is reported
as incomplete, never as zero.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from agriculture.models import ActivityInput, ActivityLabor
from inventory.models import InventoryMovement

CENT = Decimal('0.01')


@dataclass(frozen=True)
class CostSummary:
    labor: Decimal
    inputs: Decimal
    # False when any consumed layer has no cost or an input has no recorded consumption.
    is_complete: bool
    issues: tuple = field(default_factory=tuple)

    @property
    def total(self):
        return self.labor + self.inputs


def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _summarize(**activity_filter):
    labor = sum(
        (hours * rate for hours, rate in ActivityLabor.objects.filter(**activity_filter).values_list(
            'hours', 'hourly_rate',
        )),
        Decimal('0'),
    )

    inputs_total = Decimal('0')
    issues = []
    consumed_by_input = {}
    movements = InventoryMovement.objects.filter(
        movement_type=InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT,
        activity_input__in=ActivityInput.objects.filter(**activity_filter),
    ).values_list('activity_input_id', 'quantity', 'unit_cost')
    for input_id, quantity, unit_cost in movements:
        consumed_by_input[input_id] = consumed_by_input.get(input_id, Decimal('0')) + quantity
        if unit_cost is None:
            issues.append(f'El insumo {input_id} consumió una capa sin costo.')
        else:
            inputs_total += quantity * unit_cost

    for input_id, declared in ActivityInput.objects.filter(**activity_filter).values_list('pk', 'quantity'):
        if consumed_by_input.get(input_id, Decimal('0')) != declared:
            issues.append(f'El insumo {input_id} no tiene su consumo de inventario completo.')

    return CostSummary(
        labor=_money(labor),
        inputs=_money(inputs_total),
        is_complete=not issues,
        issues=tuple(sorted(set(issues))),
    )


def activity_cost(activity):
    return _summarize(activity=activity)


def crop_cycle_cost(crop_cycle):
    return _summarize(activity__crop_cycle=crop_cycle)


def lot_cost(lot):
    return _summarize(activity__crop_cycle__lot=lot)
