from datetime import date
from django.db.models import Sum, F, FloatField
import json
from django.shortcuts import render
from django.utils import timezone
from sales.models import SaleItem
from expenses.models import Expense, ExpenseCategory
from products.models import Product
from inventory.models import InventoryEntry


def format_cop(value):
    return f"${value:,.0f} COP".replace(',', '.')


def get_month_range(year, month):
    return date(year, month, 1)


def home(request):
    today = timezone.localdate()
    first_day_month = today.replace(day=1)
    annual_start = today.replace(month=1, day=1)

    sales_items = SaleItem.objects.filter(sale__sale_date__gte=annual_start)
    expenses_year = Expense.objects.filter(date__gte=annual_start)

    monthly_sales = sales_items.filter(sale__sale_date__gte=first_day_month)
    monthly_expenses = expenses_year.filter(date__gte=first_day_month)

    sales_total_month = monthly_sales.aggregate(total=Sum(F('unit_price') * F('quantity'), output_field=FloatField()))['total'] or 0
    expenses_total_month = monthly_expenses.aggregate(total=Sum('amount'))['total'] or 0
    sales_total_year = sales_items.aggregate(total=Sum(F('unit_price') * F('quantity'), output_field=FloatField()))['total'] or 0
    expenses_total_year = expenses_year.aggregate(total=Sum('amount'))['total'] or 0

    profit_month = sales_total_month - expenses_total_month
    profit_year = sales_total_year - expenses_total_year
    margin_month = (profit_month / sales_total_month * 100) if sales_total_month else 0
    margin_year = (profit_year / sales_total_year * 100) if sales_total_year else 0

    kilograms_sold_month = monthly_sales.aggregate(total_grams=Sum(F('product__weight_grams') * F('quantity'), output_field=FloatField()))['total_grams'] or 0
    kilograms_sold_year = sales_items.aggregate(total_grams=Sum(F('product__weight_grams') * F('quantity'), output_field=FloatField()))['total_grams'] or 0

    sales_count_month = monthly_sales.values('sale').distinct().count()
    average_ticket = (sales_total_month / sales_count_month) if sales_count_month else 0

    best_selling_product = Product.objects.annotate(total_quantity=Sum('saleitem__quantity')).order_by('-total_quantity').first()
    most_profitable_product = Product.objects.annotate(total_profit=Sum((F('saleitem__unit_price') - F('production_cost')) * F('saleitem__quantity'), output_field=FloatField())).order_by('-total_profit').first()

    sales_history = []
    expenses_history = []
    kg_history = []
    labels = []
    current_year = today.year
    current_month = today.month
    for idx in range(11, -1, -1):
        month = current_month - idx
        year = current_year
        if month <= 0:
            month += 12
            year -= 1
        labels.append(date(year, month, 1).strftime('%b'))
        period_sales = sales_items.filter(sale__sale_date__year=year, sale__sale_date__month=month)
        period_expenses = expenses_year.filter(date__year=year, date__month=month)
        sales_history.append(period_sales.aggregate(total=Sum(F('unit_price') * F('quantity'), output_field=FloatField()))['total'] or 0)
        expenses_history.append(period_expenses.aggregate(total=Sum('amount'))['total'] or 0)
        kg_history.append((period_sales.aggregate(total_grams=Sum(F('product__weight_grams') * F('quantity'), output_field=FloatField()))['total_grams'] or 0) / 1000)

    categories = ExpenseCategory.objects.all()
    expense_distribution = []
    for category in categories:
        total = expenses_year.filter(category=category).aggregate(total=Sum('amount'))['total'] or 0
        expense_distribution.append({'name': category.name, 'total': total})

    inventory_totals = InventoryEntry.objects.aggregate(
        total_bags=Sum('bags_added'),
        total_kilos=Sum('kilos_added'),
    )
    inventory_month = InventoryEntry.objects.filter(date__gte=first_day_month).aggregate(
        month_bags=Sum('bags_added'),
        month_kilos=Sum('kilos_added'),
    )
    sold_totals = SaleItem.objects.aggregate(
        sold_bags=Sum('quantity'),
        sold_kilos=Sum(F('quantity') * F('product__weight_grams') / 1000.0, output_field=FloatField()),
    )
    sold_monthly = SaleItem.objects.filter(sale__sale_date__gte=first_day_month).aggregate(
        sold_bags=Sum('quantity'),
        sold_kilos=Sum(F('quantity') * F('product__weight_grams') / 1000.0, output_field=FloatField()),
    )

    total_bags = inventory_totals['total_bags'] or 0
    total_kilos = inventory_totals['total_kilos'] or 0
    sold_bags_total = sold_totals['sold_bags'] or 0
    sold_kilos_total = sold_totals['sold_kilos'] or 0
    stock_bags = total_bags - sold_bags_total
    stock_kilos = total_kilos - sold_kilos_total

    context = {
        'sales_total_month': format_cop(sales_total_month),
        'expenses_total_month': format_cop(expenses_total_month),
        'profit_month': format_cop(profit_month),
        'profit_month_value': profit_month,
        'margin_month': f'{margin_month:.1f} %',
        'margin_month_value': margin_month,
        'kilograms_sold_month': f'{kilograms_sold_month / 1000:.2f} kg',
        'sales_count_month': sales_count_month,
        'average_ticket': format_cop(average_ticket),
        'best_selling_product': best_selling_product.name if best_selling_product else 'N/A',
        'stock_bags': stock_bags,
        'stock_kilos': stock_kilos or 0,
        'sold_bags_total': sold_bags_total,
        'sold_kilos_total': sold_kilos_total or 0,
        'chart_labels': json.dumps(labels, ensure_ascii=False),
        'chart_sales_data': json.dumps(sales_history),
        'chart_expenses_data': json.dumps(expenses_history),
        'chart_kg_data': json.dumps(kg_history),
        'chart_expense_labels': json.dumps([item['name'] for item in expense_distribution], ensure_ascii=False),
        'chart_expense_values': json.dumps([item['total'] for item in expense_distribution]),
    }
    return render(request, 'dashboard/home.html', context)
