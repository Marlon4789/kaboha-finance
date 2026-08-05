from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from .models import Sale, SaleItem


class SalesTests(TestCase):
    def test_sale_calculation_and_metrics(self):
        product = Product.objects.create(
            name='Café Prueba',
            description='Especial',
            weight_grams=500,
            sale_price=35000,
            production_cost=14000,
            active=True,
        )
        sale = Sale.objects.create(sale_date=timezone.localdate(), customer_name='Cliente Prueba', payment_method='Efectivo')
        sale_item = SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=35000)

        self.assertEqual(sale.subtotal(), 70000)
        self.assertEqual(sale.total(), 70000)
        self.assertEqual(sale.quantity_units(), 2)
        self.assertEqual(sale.grams_sold(), 1000)
        self.assertEqual(sale.kilos_sold(), 1)
        self.assertEqual(str(sale), f'Venta {sale.id} - Cliente Prueba ({sale.sale_date})')

    def test_sale_list_page(self):
        Sale.objects.create(sale_date=timezone.localdate(), customer_name='Cliente Test', payment_method='Efectivo')
        response = self.client.get(reverse('sale_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cliente Test')
