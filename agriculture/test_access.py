from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agriculture.models import CropCycle, Farm, Harvest, Lot


class HarvestAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='test-password')
        self.intruder = User.objects.create_user(username='intruder', password='test-password')
        farm = Farm.objects.create(owner=self.owner, name='Finca privada')
        lot = Lot.objects.create(farm=farm, code='P-01', name='Lote privado', area_ha=Decimal('1.0000'))
        self.cycle = CropCycle.objects.create(
            lot=lot, cycle_type=CropCycle.CycleType.NEW, start_date=date(2025, 1, 1),
        )
        self.harvest = Harvest.objects.create(crop_cycle=self.cycle, harvested_on=date(2025, 10, 10))

    def urls(self):
        return [
            reverse('harvest_list'),
            reverse('harvest_create'),
            reverse('harvest_inventory_register', args=[self.harvest.pk]),
        ]

    def test_anonymous_users_are_redirected_to_login(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"{reverse('admin:login')}?next={url}", fetch_redirect_response=False,
                )

    def test_owner_can_see_own_harvests(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse('harvest_list'))

        self.assertEqual(list(response.context['harvests']), [self.harvest])

    def test_other_users_do_not_see_or_register_foreign_harvests(self):
        self.client.force_login(self.intruder)

        self.assertEqual(list(self.client.get(reverse('harvest_list')).context['harvests']), [])
        register_url = reverse('harvest_inventory_register', args=[self.harvest.pk])
        self.assertEqual(self.client.get(register_url).status_code, 404)
        self.assertEqual(self.client.post(register_url, {'quantity_kg': '1'}).status_code, 404)

    def test_other_users_cannot_create_harvests_on_foreign_cycles(self):
        self.client.force_login(self.intruder)

        response = self.client.post(reverse('harvest_create'), {
            'crop_cycle': self.cycle.pk,
            'harvested_on': '2025-11-01',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('crop_cycle', response.context['form'].errors)
        self.assertEqual(Harvest.objects.count(), 1)
