from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlySummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.IntegerField()),
                ('month', models.IntegerField()),
                ('sales_total', models.FloatField(default=0)),
                ('expenses_total', models.FloatField(default=0)),
                ('profit_total', models.FloatField(default=0)),
                ('bags_sold', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-year', '-month'],
                'unique_together': {('year', 'month')},
            },
        ),
    ]
