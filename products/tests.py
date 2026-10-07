from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from agriculture.models import ActivityInput, AgriculturalActivity, CropCycle, Farm, Lot
from inventory.models import InventoryMovement
from inventory.services import InventoryService
from sales.models import Sale, SaleItem
from .models import Product


class ProductTests(TestCase):
    def test_product_profit_and_margin(self):
        product = Product.objects.create(
            name='Blend Test',
            description='Prueba de margen',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=250,
            weight_grams=250,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        self.assertEqual(product.profit_per_unit, 21000)
        self.assertEqual(product.margin_percentage, 60.0)

    def test_product_list_page(self):
        Product.objects.create(
            name='Café Test',
            description='Café',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            is_sellable=True,
            is_stock_tracked=True,
            sale_unit_quantity=500,
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Café Test')

    def test_decimal_catalog_price_and_grams_keep_precision_in_filters(self):
        from dashboard.templatetags.finance_filters import co_currency, co_grams

        self.assertEqual(co_currency(Decimal('35000.50')), '$35.000,50 COP')
        self.assertEqual(co_currency(Decimal('35000.00')), '$35.000 COP')
        self.assertEqual(co_grams(Decimal('250.500')), '250,5 g')


class ProductCatalogTests(TestCase):
    def build_product(self, **overrides):
        values = {
            'name': 'Producto catálogo',
            'description': '',
            'item_type': Product.ItemType.OTHER,
            'coffee_stage': None,
            'base_unit': Product.BaseUnit.UNIT,
            'sale_unit_quantity': None,
            'is_sellable': False,
            'is_stock_tracked': False,
            'sale_price': None,
            'production_cost': 0,
        }
        values.update(overrides)
        return Product(**values)

    def test_all_item_types_are_valid_choices(self):
        for item_type in Product.ItemType.values:
            with self.subTest(item_type=item_type):
                product = self.build_product(
                    item_type=item_type,
                    coffee_stage=Product.CoffeeStage.GROUND if item_type == Product.ItemType.COFFEE else None,
                )
                product.full_clean()

    def test_all_coffee_stages_are_valid_and_required_for_coffee(self):
        for stage in Product.CoffeeStage.values:
            with self.subTest(stage=stage):
                product = self.build_product(item_type=Product.ItemType.COFFEE, coffee_stage=stage)
                product.full_clean()

        missing_stage = self.build_product(item_type=Product.ItemType.COFFEE)
        with self.assertRaises(ValidationError):
            missing_stage.full_clean()

    def test_noncoffee_products_cannot_have_coffee_stage(self):
        product = self.build_product(item_type=Product.ItemType.TOOL, coffee_stage=Product.CoffeeStage.GROUND)

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_all_base_units_are_valid(self):
        for unit in Product.BaseUnit.values:
            with self.subTest(unit=unit):
                product = self.build_product(base_unit=unit, is_stock_tracked=True)
                product.full_clean()

    def test_sellable_product_requires_price_unit_and_positive_commercial_quantity(self):
        valid = self.build_product(
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=250,
            is_sellable=True,
            is_stock_tracked=True,
            sale_price='35000.00',
        )
        valid.full_clean()
        valid.save()
        valid.refresh_from_db()
        self.assertEqual(valid.sale_price, Decimal('35000.00'))
        self.assertEqual(valid.sale_unit_quantity, Decimal('250.000'))

        for changes in (
            {'sale_price': None},
            {'sale_unit_quantity': None},
            {'sale_unit_quantity': Decimal('0')},
            {'base_unit': None},
        ):
            with self.subTest(changes=changes):
                invalid_values = {
                    'item_type': Product.ItemType.COFFEE,
                    'coffee_stage': Product.CoffeeStage.GROUND,
                    'base_unit': Product.BaseUnit.G,
                    'sale_unit_quantity': 250,
                    'is_sellable': True,
                    'is_stock_tracked': True,
                    'sale_price': 35000,
                }
                invalid_values.update(changes)
                invalid = self.build_product(**invalid_values)
                with self.assertRaises(ValidationError):
                    invalid.full_clean()

    def test_non_sellable_product_may_have_no_sale_price_or_presentation(self):
        product = self.build_product(
            item_type=Product.ItemType.AGRICULTURAL_INPUT,
            base_unit=Product.BaseUnit.G,
            is_stock_tracked=True,
        )
        product.full_clean()
        self.assertIsNone(product.sale_price)
        self.assertIsNone(product.sale_unit_quantity)
        product.save()
        self.assertIsNotNone(product.pk)

    def test_tracked_product_requires_base_unit(self):
        product = self.build_product(base_unit=None, is_stock_tracked=True)

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_sale_price_must_be_nonnegative(self):
        product = self.build_product(sale_price=Decimal('-0.01'))

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_product_form_exposes_catalog_fields_and_not_legacy_weight(self):
        from .forms import ProductForm

        self.assertEqual(
            set(ProductForm.Meta.fields),
            {
                'name', 'description', 'item_type', 'coffee_stage', 'base_unit',
                'sale_unit_quantity', 'is_sellable', 'is_stock_tracked',
                'sale_price', 'production_cost', 'active',
            },
        )


class ProductFinancialDisplayTests(TestCase):
    def make_product(self, *, sale_price, production_cost):
        return Product.objects.create(
            name='Producto para margen',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=Decimal('250'),
            is_sellable=True,
            is_stock_tracked=True,
            sale_price=sale_price,
            production_cost=production_cost,
        )

    def test_unknown_cost_makes_profit_and_margin_unknown(self):
        product = self.make_product(sale_price=Decimal('35000'), production_cost=None)

        self.assertIsNone(product.profit_per_unit)
        self.assertIsNone(product.margin_percentage)

    def test_missing_price_makes_profit_and_margin_not_calculable(self):
        product = Product(sale_price=None, production_cost=14000)

        self.assertIsNone(product.profit_per_unit)
        self.assertIsNone(product.margin_percentage)

    def test_known_zero_cost_is_calculated_without_becoming_unknown(self):
        product = self.make_product(sale_price=Decimal('35000'), production_cost=0)

        self.assertEqual(product.profit_per_unit, Decimal('35000'))
        self.assertEqual(product.margin_percentage, 100.0)

    def test_zero_sale_price_does_not_divide_by_zero(self):
        product = self.make_product(sale_price=Decimal('0'), production_cost=0)

        self.assertEqual(product.profit_per_unit, Decimal('0'))
        self.assertIsNone(product.margin_percentage)

    def test_product_list_displays_unknown_profit_and_margin_as_dashes(self):
        self.make_product(sale_price=Decimal('35000'), production_cost=None)

        response = self.client.get(reverse('product_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count('>—</td>'.encode()), 3)


class ProductSellabilityTests(TestCase):
    def valid_sellable_data(self, *, stock_tracked):
        return {
            'name': 'Café vendible',
            'description': '',
            'item_type': Product.ItemType.COFFEE,
            'coffee_stage': Product.CoffeeStage.GROUND,
            'base_unit': Product.BaseUnit.G,
            'sale_unit_quantity': '250',
            'is_sellable': 'on',
            'is_stock_tracked': 'on' if stock_tracked else '',
            'sale_price': '35000',
            'production_cost': '',
            'active': 'on',
        }

    def test_sellable_product_with_stock_tracking_is_valid(self):
        from .forms import ProductForm

        form = ProductForm(self.valid_sellable_data(stock_tracked=True))

        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertTrue(product.is_sellable)
        self.assertTrue(product.is_stock_tracked)

    def test_sellable_product_without_stock_tracking_is_rejected(self):
        from .forms import ProductForm

        form = ProductForm(self.valid_sellable_data(stock_tracked=False))

        self.assertFalse(form.is_valid())
        self.assertIn('is_stock_tracked', form.errors)

        product = Product(
            name='Café inválido',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=Decimal('250'),
            is_sellable=True,
            is_stock_tracked=False,
            sale_price=Decimal('35000'),
        )
        with self.assertRaises(ValidationError):
            product.full_clean()
        self.assertFalse(Product.objects.filter(name='Café inválido').exists())

    def test_non_sellable_untracked_product_remains_valid(self):
        from .forms import ProductForm

        data = self.valid_sellable_data(stock_tracked=False)
        data.update({
            'name': 'Producto sin venta ni stock',
            'item_type': Product.ItemType.OTHER,
            'coffee_stage': '',
            'base_unit': '',
            'sale_unit_quantity': '',
            'is_sellable': '',
            'sale_price': '',
        })
        form = ProductForm(data)

        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertFalse(product.is_sellable)
        self.assertFalse(product.is_stock_tracked)


class ProductDeletionTests(TestCase):
    def make_sellable_product(self):
        return Product.objects.create(
            name='Café con historial',
            item_type=Product.ItemType.COFFEE,
            coffee_stage=Product.CoffeeStage.GROUND,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=Decimal('250'),
            is_sellable=True,
            is_stock_tracked=True,
            sale_price=Decimal('35000'),
            production_cost=14000,
        )

    def assert_protected_delete_is_controlled(self, product):
        response = self.client.post(
            reverse('product_delete', args=[product.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se puede eliminar este producto')
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_product_without_protected_references_can_be_deleted(self):
        product = Product.objects.create(
            name='Producto sin historial',
            item_type=Product.ItemType.OTHER,
            base_unit=Product.BaseUnit.UNIT,
        )

        response = self.client.post(reverse('product_delete', args=[product.pk]))

        self.assertRedirects(response, reverse('product_list'))
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_product_with_sale_item_cannot_be_deleted(self):
        product = self.make_sellable_product()
        sale = Sale.objects.create(payment_method='Efectivo')
        item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=1,
            unit_price=32000,
        )

        self.assert_protected_delete_is_controlled(product)
        self.assertTrue(SaleItem.objects.filter(pk=item.pk, product=product).exists())

    def test_product_with_inventory_movement_cannot_be_deleted(self):
        product = self.make_sellable_product()
        movement = InventoryService.record_incoming(
            product,
            500,
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
        )

        self.assert_protected_delete_is_controlled(product)
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk, product=product).exists())

    def test_product_with_agricultural_input_cannot_be_deleted(self):
        product = Product.objects.create(
            name='Insumo agrícola con historial',
            item_type=Product.ItemType.AGRICULTURAL_INPUT,
            base_unit=Product.BaseUnit.UNIT,
            is_stock_tracked=True,
        )
        user = get_user_model().objects.create_user(username='product-delete-user')
        farm = Farm.objects.create(owner=user, name='Finca de prueba')
        lot = Lot.objects.create(
            farm=farm,
            code='PRODUCT-DELETE-LOT',
            name='Lote de prueba',
            area_ha=Decimal('1.0000'),
        )
        cycle = CropCycle.objects.create(
            lot=lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date=date(2025, 1, 1),
        )
        activity = AgriculturalActivity.objects.create(
            crop_cycle=cycle,
            activity_type=AgriculturalActivity.ActivityType.OTHER,
        )
        activity_input = ActivityInput.objects.create(
            activity=activity,
            product=product,
            quantity=Decimal('1.000'),
        )

        self.assert_protected_delete_is_controlled(product)
        self.assertTrue(
            ActivityInput.objects.filter(pk=activity_input.pk, product=product).exists(),
        )

    def test_catalog_price_changes_and_protected_delete_preserve_sale_price_history(self):
        product = self.make_sellable_product()
        sale = Sale.objects.create(payment_method='Efectivo')
        item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=1,
            unit_price=32000,
        )

        product.sale_price = Decimal('40000')
        product.save(update_fields=['sale_price'])
        item.refresh_from_db()
        self.assertEqual(item.unit_price, 32000)

        self.assert_protected_delete_is_controlled(product)
        item.refresh_from_db()
        self.assertEqual(item.unit_price, 32000)


class ProductBaseUnitHistoryTests(TestCase):
    def build_product(self, *, is_sellable=False, is_stock_tracked=True):
        return Product.objects.create(
            name='Producto unidad base',
            item_type=Product.ItemType.COFFEE if is_sellable else Product.ItemType.OTHER,
            coffee_stage=Product.CoffeeStage.GROUND if is_sellable else None,
            base_unit=Product.BaseUnit.G,
            sale_unit_quantity=Decimal('250') if is_sellable else None,
            is_sellable=is_sellable,
            is_stock_tracked=is_stock_tracked,
            sale_price=Decimal('10000') if is_sellable else None,
            production_cost=0,
        )

    def assert_base_unit_change_rejected(self, product):
        original_unit = product.base_unit
        product.base_unit = Product.BaseUnit.ML
        with self.assertRaises(ValidationError):
            product.save(update_fields=['base_unit'])
        product.refresh_from_db()
        self.assertEqual(product.base_unit, original_unit)

    def create_activity_input(self, product):
        user = get_user_model().objects.create_user(username='product-history-user')
        farm = Farm.objects.create(owner=user, name='Finca unidad base')
        lot = Lot.objects.create(
            farm=farm,
            code='UNIT-HISTORY-LOT',
            name='Lote unidad base',
            area_ha=Decimal('1.0000'),
        )
        cycle = CropCycle.objects.create(
            lot=lot,
            cycle_type=CropCycle.CycleType.NEW,
            start_date=date(2025, 1, 1),
        )
        activity = AgriculturalActivity.objects.create(
            crop_cycle=cycle,
            activity_type=AgriculturalActivity.ActivityType.OTHER,
        )
        return ActivityInput.objects.create(
            activity=activity,
            product=product,
            quantity=Decimal('1.000'),
        )

    def test_base_unit_can_change_without_sales_or_inventory_history(self):
        product = self.build_product()

        product.base_unit = Product.BaseUnit.ML
        product.save(update_fields=['base_unit'])
        product.refresh_from_db()

        self.assertEqual(product.base_unit, Product.BaseUnit.ML)

    def test_base_unit_cannot_change_after_sales(self):
        from sales.models import Sale, SaleItem

        product = self.build_product(is_sellable=True)
        sale = Sale.objects.create(payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=10000)

        self.assert_base_unit_change_rejected(product)

    def test_base_unit_cannot_change_after_inventory_movement(self):
        from inventory.models import InventoryMovement

        product = self.build_product()
        InventoryMovement.objects.create(
            product=product,
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            quantity=Decimal('1000'),
            occurred_at=timezone.now(),
        )

        self.assert_base_unit_change_rejected(product)

    def test_base_unit_cannot_change_after_agricultural_input(self):
        product = self.build_product()
        activity_input = self.create_activity_input(product)

        self.assert_base_unit_change_rejected(product)
        self.assertTrue(ActivityInput.objects.filter(pk=activity_input.pk).exists())

    def test_base_unit_cannot_change_after_both_sales_and_inventory_movement(self):
        from inventory.models import InventoryMovement
        from sales.models import Sale, SaleItem

        product = self.build_product(is_sellable=True)
        sale = Sale.objects.create(payment_method='Efectivo')
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=10000)
        InventoryMovement.objects.create(
            product=product,
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            quantity=Decimal('1000'),
            occurred_at=timezone.now(),
        )

        self.assert_base_unit_change_rejected(product)

    def test_saving_without_changing_base_unit_is_allowed_with_history(self):
        product = self.build_product()
        movement = InventoryService.record_incoming(
            product,
            Decimal('1000'),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=Decimal('2.50000000'),
        )

        product.name = 'Producto unidad base actualizado'
        product.save(update_fields=['name'])

        self.assertEqual(InventoryService.get_stock(product), Decimal('1000.000'))
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk, product=product).exists())

    def test_base_unit_history_rule_is_applied_by_product_form(self):
        from .forms import ProductForm

        product = self.build_product()
        self.create_activity_input(product)
        form = ProductForm({
            'name': product.name,
            'description': '',
            'item_type': Product.ItemType.OTHER,
            'coffee_stage': '',
            'base_unit': Product.BaseUnit.ML,
            'sale_unit_quantity': '',
            'is_sellable': '',
            'is_stock_tracked': 'on',
            'sale_price': '',
            'production_cost': '0',
            'active': 'on',
        }, instance=product)

        self.assertFalse(form.is_valid())
        self.assertIn('base_unit', form.errors)


class ProductStockTrackingHistoryTests(TestCase):
    def build_product(self, *, is_stock_tracked=True):
        return Product.objects.create(
            name='Producto seguimiento',
            item_type=Product.ItemType.OTHER,
            base_unit=Product.BaseUnit.UNIT,
            is_stock_tracked=is_stock_tracked,
            is_sellable=False,
        )

    def assert_stock_tracking_change_rejected(self, product, new_value):
        original_value = product.is_stock_tracked
        product.is_stock_tracked = new_value
        with self.assertRaises(ValidationError):
            product.save(update_fields=['is_stock_tracked'])
        product.refresh_from_db()
        self.assertEqual(product.is_stock_tracked, original_value)

    def test_stock_tracking_can_change_in_both_directions_without_movements(self):
        product = self.build_product()

        product.is_stock_tracked = False
        product.save(update_fields=['is_stock_tracked'])
        product.refresh_from_db()
        self.assertFalse(product.is_stock_tracked)

        product.is_stock_tracked = True
        product.save(update_fields=['is_stock_tracked'])
        product.refresh_from_db()
        self.assertTrue(product.is_stock_tracked)

    def test_stock_tracking_cannot_be_disabled_after_inventory_movement(self):
        product = self.build_product()
        movement = InventoryService.record_incoming(
            product,
            Decimal('1000'),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=Decimal('3.00000000'),
        )

        self.assert_stock_tracking_change_rejected(product, False)
        self.assertEqual(InventoryService.get_stock(product), Decimal('1000.000'))
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk).exists())

    def test_stock_tracking_cannot_be_enabled_after_inventory_movement(self):
        product = self.build_product(is_stock_tracked=False)
        movement = InventoryMovement.objects.create(
            product=product,
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            quantity=Decimal('1000'),
            occurred_at=timezone.now(),
        )

        self.assert_stock_tracking_change_rejected(product, True)
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk).exists())

    def test_stock_tracking_history_rule_is_applied_by_product_form(self):
        from .forms import ProductForm

        product = self.build_product()
        InventoryService.record_incoming(
            product,
            Decimal('1000'),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
        )
        form = ProductForm({
            'name': product.name,
            'description': '',
            'item_type': Product.ItemType.OTHER,
            'coffee_stage': '',
            'base_unit': Product.BaseUnit.UNIT,
            'sale_unit_quantity': '',
            'is_sellable': '',
            'is_stock_tracked': '',
            'sale_price': '',
            'production_cost': '0',
            'active': 'on',
        }, instance=product)

        self.assertFalse(form.is_valid())
        self.assertIn('is_stock_tracked', form.errors)

    def test_stock_and_layer_cost_survive_allowed_product_changes(self):
        product = self.build_product()
        movement = InventoryService.record_incoming(
            product,
            Decimal('1000'),
            movement_type=InventoryMovement.MovementType.OPENING_BALANCE_IN,
            unit_cost=Decimal('3.00000000'),
        )

        product.name = 'Producto actualizado'
        product.active = False
        product.production_cost = 25000
        product.sale_unit_quantity = Decimal('500')
        product.save(update_fields=[
            'name', 'active', 'production_cost', 'sale_unit_quantity', 'updated_at',
        ])

        self.assertEqual(InventoryService.get_stock(product), Decimal('1000.000'))
        movement.refresh_from_db()
        self.assertEqual(movement.unit_cost, Decimal('3.00000000'))
