from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from inventory.models import InventoryEntry
from products.models import Product
from sales.models import Sale, SaleItem


class InventoryTests(TestCase):
    def test_inventory_list_page_status_code(self):
        response = self.client.get(reverse('inventory_list'))
        self.assertEqual(response.status_code, 200)

    def test_inventory_entry_and_sales_affect_stock(self):
        InventoryEntry.objects.create(date=timezone.localdate(), bags_added=10, kilos_added=50)
        product = Product.objects.create(
            name='Café Test',
            description='Café para prueba',
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
        self.assertEqual(response.context['stock_kilos'], 49.0)
        self.assertEqual(response.context['sold_bags_total'], 2)
