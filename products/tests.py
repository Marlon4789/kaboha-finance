from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
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
