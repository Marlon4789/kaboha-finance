from django.test import TestCase
from django.urls import reverse
from .models import Product


class ProductTests(TestCase):
    def test_product_profit_and_margin(self):
        product = Product.objects.create(
            name='Blend Test',
            description='Prueba de margen',
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
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Café Test')
