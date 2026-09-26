from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agriculture.models import (
    ActivityInput,
    AgriculturalActivity,
    CropCycle,
    Farm,
    Harvest,
    Lot,
    ProductionBatch,
)
from expenses.models import Expense, ExpenseCategory
from inventory.models import InventoryEntry, InventoryMovement
from products.models import Product
from sales.models import Sale, SaleItem
from .forms import InventoryEntryForm


class InventoryTests(TestCase):
    def test_inventory_form_is_in_spanish_and_includes_pergamino(self):
        form = InventoryEntryForm()

        self.assertIn('kilos_pergamino', form.fields)
        self.assertEqual(form.fields['kilos_pergamino'].label, 'Kilos de café pergamino')
        response = self.client.get(reverse('inventory_create'))
        self.assertContains(response, 'Kilos de café pergamino')
        self.assertContains(response, 'Cantidad de café pergamino.')

    def test_inventory_list_page_status_code(self):
        response = self.client.get(reverse('inventory_list'))
        self.assertEqual(response.status_code, 200)

    def test_inventory_entry_and_sales_affect_stock(self):
        InventoryEntry.objects.create(date=timezone.localdate(), bags_added=10, kilos_added=50, kilos_pergamino=12)
        product = Product.objects.create(
            name='Café Test',
            description='Café para prueba',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=20000,
            production_cost=10000,
            active=True,
        )
        sale = Sale.objects.create(sale_date=timezone.localdate(), payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=20000)

        response = self.client.get(reverse('inventory_list'))
        self.assertContains(response, 'Bolsas disponibles')
        self.assertContains(response, '8')
        self.assertContains(response, 'Bolsas vendidas')
        self.assertContains(response, '2')
        self.assertContains(response, 'Kilos pergamino')
        self.assertEqual(response.context['stock_kilos'], 49.0)
        self.assertEqual(response.context['sold_bags_total'], 2)
        self.assertEqual(response.context['total_kilos_pergamino'], 12.0)


class InventoryMovementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='farm-owner', password='test-password')
        self.product = self.create_product('Insumo', item_type=Product.ItemType.AGRICULTURAL_INPUT)
        self.coffee = self.create_product(
            'Café molido', item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND, is_sellable=True,
            sale_unit_quantity=Decimal('250'), sale_price=Decimal('10000'),
        )
        self.category = ExpenseCategory.objects.create(name='Compra de insumos')
        self.expense = Expense.objects.create(category=self.category, description='Abono', amount=300000)
        self.farm = Farm.objects.create(owner=self.user, name='Finca test')
        self.lot = Lot.objects.create(farm=self.farm, code='L-1', name='Lote 1', area_ha=Decimal('1'))
        self.cycle = CropCycle.objects.create(
            lot=self.lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1),
        )
        self.activity = AgriculturalActivity.objects.create(
            crop_cycle=self.cycle, activity_type=AgriculturalActivity.ActivityType.FERTILIZATION,
        )
        self.activity_input = ActivityInput.objects.create(
            activity=self.activity, product=self.product, quantity=Decimal('1000'),
        )
        self.harvest = Harvest.objects.create(crop_cycle=self.cycle, harvested_on=date(2025, 10, 1))
        self.batch = ProductionBatch.objects.create(
            code='PB-TEST', process_type=ProductionBatch.ProcessType.BENEFIT,
            started_at=timezone.now(),
        )
        self.sale = Sale.objects.create(sale_date=date(2025, 10, 2), payment_method='Efectivo')
        self.sale_item = SaleItem.objects.create(
            sale=self.sale, product=self.coffee, quantity=1, unit_price=10000,
        )
        self.source = self.create_movement(
            InventoryMovement.MovementType.OPENING_BALANCE_IN, product=self.product,
        )

    def create_product(
        self, name, *, item_type, coffee_stage=None, is_sellable=False,
        sale_unit_quantity=None, sale_price=None,
    ):
        return Product.objects.create(
            name=name,
            item_type=item_type,
            coffee_stage=coffee_stage,
            base_unit=Product.BaseUnit.G,
            is_sellable=is_sellable,
            is_stock_tracked=True,
            sale_unit_quantity=sale_unit_quantity,
            sale_price=sale_price,
            production_cost=0,
        )

    def create_movement(self, movement_type, *, product=None, **kwargs):
        if movement_type in InventoryMovement.OUTBOUND_TYPES:
            kwargs.setdefault('source_movement', self.source if hasattr(self, 'source') else None)
        if movement_type in InventoryMovement.ADJUSTMENT_TYPES:
            kwargs.setdefault('reason', 'Ajuste validado')
        return InventoryMovement.objects.create(
            product=product or self.product,
            movement_type=movement_type,
            quantity=Decimal('1.000'),
            occurred_at=timezone.now(),
            **kwargs,
        )

    def test_all_movement_types_create_with_the_expected_source_shape(self):
        created = []
        for movement_type in InventoryMovement.INBOUND_TYPES:
            created.append(self.create_movement(movement_type))
        for movement_type in InventoryMovement.OUTBOUND_TYPES:
            created.append(self.create_movement(movement_type))

        self.assertEqual(len(created), 9)
        for movement in created:
            if movement.movement_type in InventoryMovement.INBOUND_TYPES:
                self.assertIsNone(movement.source_movement_id)
            else:
                self.assertIsNotNone(movement.source_movement_id)

    def test_quantity_must_be_positive_in_the_database(self):
        for quantity in (Decimal('0'), Decimal('-1')):
            with self.subTest(quantity=quantity):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    InventoryMovement.objects.create(
                        product=self.product,
                        movement_type=InventoryMovement.MovementType.PURCHASE_IN,
                        quantity=quantity,
                        occurred_at=timezone.now(),
                    )

    def test_unit_cost_accepts_positive_zero_and_null_and_rejects_negative(self):
        for unit_cost in (Decimal('3.12345678'), Decimal('0'), None):
            with self.subTest(unit_cost=unit_cost):
                movement = self.create_movement(
                    InventoryMovement.MovementType.PURCHASE_IN, unit_cost=unit_cost,
                )
                self.assertEqual(movement.unit_cost, unit_cost)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.objects.create(
                product=self.product,
                movement_type=InventoryMovement.MovementType.PURCHASE_IN,
                quantity=Decimal('1'),
                occurred_at=timezone.now(),
                unit_cost=Decimal('-0.01'),
            )

    def test_source_rules_and_adjustment_reason_are_enforced(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.objects.create(
                product=self.product,
                movement_type=InventoryMovement.MovementType.SALE_OUT,
                quantity=Decimal('1'),
                occurred_at=timezone.now(),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.objects.create(
                product=self.product,
                movement_type=InventoryMovement.MovementType.PURCHASE_IN,
                quantity=Decimal('1'),
                occurred_at=timezone.now(),
                source_movement=self.source,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.objects.create(
                product=self.product,
                movement_type=InventoryMovement.MovementType.ADJUSTMENT_IN,
                quantity=Decimal('1'),
                occurred_at=timezone.now(),
            )
        row = self.create_movement(InventoryMovement.MovementType.SALE_OUT)
        row.source_movement = row
        with self.assertRaises(IntegrityError), transaction.atomic():
            row.save(update_fields=['source_movement'])

    def test_clean_rejects_source_from_a_different_product(self):
        other_product = self.create_product('Otro insumo', item_type=Product.ItemType.AGRICULTURAL_INPUT)
        movement = InventoryMovement(
            product=other_product,
            movement_type=InventoryMovement.MovementType.SALE_OUT,
            quantity=Decimal('1'),
            occurred_at=timezone.now(),
            source_movement=self.source,
        )
        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_all_domain_relations_protect_their_history(self):
        self.create_movement(InventoryMovement.MovementType.PURCHASE_IN, expense=self.expense)
        self.create_movement(
            InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT,
            activity_input=self.activity_input,
        )
        self.create_movement(InventoryMovement.MovementType.HARVEST_IN, harvest=self.harvest)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.objects.create(
                product=self.product,
                movement_type=InventoryMovement.MovementType.HARVEST_IN,
                quantity=Decimal('1'),
                occurred_at=timezone.now(),
                harvest=self.harvest,
            )
        self.create_movement(
            InventoryMovement.MovementType.TRANSFORMATION_IN, production_batch=self.batch,
        )
        self.create_movement(
            InventoryMovement.MovementType.SALE_OUT,
            product=self.coffee,
            sale_item=self.sale_item,
            source_movement=self.create_movement(
                InventoryMovement.MovementType.OPENING_BALANCE_IN, product=self.coffee,
            ),
        )

        protected_product = self.create_product(
            'Producto protegido', item_type=Product.ItemType.AGRICULTURAL_INPUT,
        )
        self.create_movement(
            InventoryMovement.MovementType.PURCHASE_IN, product=protected_product,
        )
        protected_objects = (
            protected_product, self.expense, self.activity_input, self.harvest,
            self.batch, self.sale_item, self.source,
        )
        for obj in protected_objects:
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(ProtectedError), transaction.atomic():
                    obj.delete()

    def test_created_by_is_set_null_when_user_is_deleted(self):
        User = get_user_model()
        creator = User.objects.create_user(username='movement-author', password='test-password')
        movement = self.create_movement(
            InventoryMovement.MovementType.PURCHASE_IN, created_by=creator,
        )

        creator.delete()
        movement.refresh_from_db()
        self.assertIsNone(movement.created_by_id)
