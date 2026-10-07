from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from agriculture.costing import activity_cost
from agriculture.models import AgriculturalActivity, CropCycle, Farm, Lot
from agriculture.services import record_activity_input
from expenses.models import Expense, ExpenseCategory
from inventory.models import InventoryMovement
from inventory.purchases import PurchaseReceiptError, receive_purchase
from inventory.services import InventoryService
from products.models import Product


class PurchaseReceiptTests(TestCase):
    def setUp(self):
        self.category = ExpenseCategory.objects.create(name='Insumos')
        self.expense = Expense.objects.create(
            date=date(2025, 2, 5), category=self.category, description='Compra', amount=1000,
        )
        self.fertilizer = self.make_product('Fertilizante')
        self.fungicide = self.make_product('Fungicida')

    def make_product(self, name, *, tracked=True):
        return Product.objects.create(
            name=name, item_type=Product.ItemType.AGRICULTURAL_INPUT,
            base_unit=Product.BaseUnit.G, is_stock_tracked=tracked,
        )

    def purchases(self):
        return InventoryMovement.objects.filter(movement_type=InventoryMovement.MovementType.PURCHASE_IN)

    def test_full_expense_becomes_one_costed_layer_linked_to_the_expense(self):
        movement = receive_purchase(self.expense, self.fertilizer, 500)

        self.assertEqual(movement.expense, self.expense)
        self.assertEqual(movement.unit_cost, Decimal('2.00000000'))
        self.assertEqual(movement.occurred_at.date(), date(2025, 2, 5))
        self.assertEqual(InventoryService.get_stock(self.fertilizer), Decimal('500.000'))
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.amount, 1000)

    def test_one_expense_can_fund_several_products_without_exceeding_its_amount(self):
        receive_purchase(self.expense, self.fertilizer, 100, cost=600)
        second = receive_purchase(self.expense, self.fungicide, 40)

        self.assertEqual(second.unit_cost, Decimal('10.00000000'))
        with self.assertRaises(PurchaseReceiptError):
            receive_purchase(self.expense, self.fertilizer, 1, cost=1)
        self.assertEqual(self.purchases().count(), 2)

    def test_cost_above_pending_amount_is_rejected(self):
        receive_purchase(self.expense, self.fertilizer, 100, cost=600)

        with self.assertRaises(PurchaseReceiptError):
            receive_purchase(self.expense, self.fungicide, 10, cost=500)
        self.assertEqual(self.purchases().count(), 1)

    def test_rounding_remainder_does_not_allow_a_second_receipt(self):
        expense = Expense.objects.create(category=self.category, amount=100)

        movement = receive_purchase(expense, self.fertilizer, 3)

        self.assertEqual(movement.unit_cost, Decimal('33.33333333'))
        with self.assertRaises(PurchaseReceiptError):
            receive_purchase(expense, self.fungicide, 1)

    def test_invalid_input_creates_nothing(self):
        untracked = self.make_product('Abono propio', tracked=False)
        cases = [
            (self.fertilizer, 0, None),
            (self.fertilizer, -1, None),
            (self.fertilizer, 'abc', None),
            (self.fertilizer, 10, 0),
            (self.fertilizer, 10, 'NaN'),
            (untracked, 10, None),
            (999999, 10, None),
        ]

        for product, quantity, cost in cases:
            with self.subTest(product=product, quantity=quantity, cost=cost), self.assertRaises(PurchaseReceiptError):
                receive_purchase(self.expense, product, quantity, cost=cost)
        with self.assertRaises(PurchaseReceiptError):
            receive_purchase(999999, self.fertilizer, 10)
        self.assertEqual(self.purchases().count(), 0)

    def test_purchase_cost_flows_into_activity_cost(self):
        user = get_user_model().objects.create_user(username='buyer', password='test-password')
        farm = Farm.objects.create(owner=user, name='Finca compra')
        lot = Lot.objects.create(farm=farm, code='B-01', name='Lote', area_ha=Decimal('1.0000'))
        cycle = CropCycle.objects.create(lot=lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1))
        activity = AgriculturalActivity.objects.create(
            crop_cycle=cycle, activity_type=AgriculturalActivity.ActivityType.FERTILIZATION,
            performed_on=date(2025, 3, 1),
        )
        receive_purchase(self.expense, self.fertilizer, 500)

        record_activity_input(activity, self.fertilizer, 120)

        summary = activity_cost(activity)
        self.assertEqual(summary.inputs, Decimal('240.00'))
        self.assertTrue(summary.is_complete)
