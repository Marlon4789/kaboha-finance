from datetime import date
from django.db.models import Sum, F, FloatField, Avg, Q
import json
from django.shortcuts import render
from django.utils import timezone
from sales.models import SaleItem
from expenses.models import Expense, ExpenseCategory
from products.models import Product
from inventory.services import InventoryService
from .models import MonthlySummary
from django.http import HttpResponse
import csv
from django.shortcuts import get_object_or_404
from io import BytesIO


def format_cop(value):
    return f"${value:,.0f} COP".replace(',', '.')


def get_month_range(year, month):
    return date(year, month, 1)


def summarize_period(sales_qs, expense_qs):
    sales_data = sales_qs.aggregate(
        total=Sum(F('unit_price') * F('quantity'), output_field=FloatField()),
        bags_sold=Sum('quantity'),
    )
    expenses_total = expense_qs.aggregate(total=Sum('amount'))['total'] or 0
    sales_total = sales_data['total'] or 0
    return {
        'sales_total': sales_total,
        'expenses_total': expenses_total,
        'profit_total': sales_total - expenses_total,
        'bags_sold': sales_data['bags_sold'] or 0,
    }


def sync_monthly_summary(year, month):
    sales_qs = SaleItem.objects.filter(sale__sale_date__year=year, sale__sale_date__month=month)
    expense_qs = Expense.objects.filter(date__year=year, date__month=month)
    if not sales_qs.exists() and not expense_qs.exists():
        MonthlySummary.objects.filter(year=year, month=month).delete()
        return

    values = summarize_period(sales_qs, expense_qs)
    MonthlySummary.objects.update_or_create(
        year=year,
        month=month,
        defaults=values,
    )


def reconcile_monthly_summaries(today):
    periods = {
        (sale_date.year, sale_date.month)
        for sale_date in SaleItem.objects.filter(
            sale__sale_date__lte=today,
        ).values_list('sale__sale_date', flat=True).distinct()
    }
    periods.update(
        (expense_date.year, expense_date.month)
        for expense_date in Expense.objects.filter(
            date__lte=today,
        ).values_list('date', flat=True).distinct()
    )
    periods.update(
        MonthlySummary.objects.filter(
            Q(year__lt=today.year) | Q(year=today.year, month__lte=today.month),
        ).values_list('year', 'month')
    )

    for year, month in sorted(periods):
        sync_monthly_summary(year, month)


def home(request):
    today = timezone.localdate()
    # Spanish month names for display
    month_names_es = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    available_periods = set(
        (sale_date.year, sale_date.month)
        for sale_date in SaleItem.objects.values_list('sale__sale_date', flat=True)
        if sale_date and (sale_date.year, sale_date.month) <= (today.year, today.month)
    )
    available_periods.update(
        (expense_date.year, expense_date.month)
        for expense_date in Expense.objects.values_list('date', flat=True)
        if expense_date and (expense_date.year, expense_date.month) <= (today.year, today.month)
    )
    available_periods.add((today.year, today.month))
    available_periods = sorted(available_periods, reverse=True)

    selected_period = request.GET.get('month', '')
    try:
        selected_year, selected_month = (int(value) for value in selected_period.split('-'))
        if (selected_year, selected_month) not in available_periods:
            raise ValueError
    except (TypeError, ValueError):
        selected_year, selected_month = today.year, today.month

    first_day_month = date(selected_year, selected_month, 1)
    current_month_display = f"{month_names_es[selected_month - 1].capitalize()} {selected_year}"
    annual_start = date(today.year, 1, 1)

    sales_items = SaleItem.objects.filter(
        sale__sale_date__range=(annual_start, today),
    )
    expenses_year = Expense.objects.filter(date__range=(annual_start, today))

    monthly_sales = SaleItem.objects.filter(sale__sale_date__year=selected_year, sale__sale_date__month=selected_month)
    monthly_expenses = Expense.objects.filter(date__year=selected_year, date__month=selected_month)

    monthly_summary = summarize_period(monthly_sales, monthly_expenses)
    year_summary = summarize_period(sales_items, expenses_year)

    sales_total_month = monthly_summary['sales_total']
    expenses_total_month = monthly_summary['expenses_total']
    profit_month = monthly_summary['profit_total']
    sales_total_year = year_summary['sales_total']
    expenses_total_year = year_summary['expenses_total']
    profit_year = year_summary['profit_total']
    margin_month = (profit_month / sales_total_month * 100) if sales_total_month else 0
    margin_year = (profit_year / sales_total_year * 100) if sales_total_year else 0

    kilograms_sold_month = monthly_sales.filter(product__base_unit=Product.BaseUnit.G).aggregate(total_grams=Sum(F('unit_quantity_base_snapshot') * F('quantity'), output_field=FloatField()))['total_grams'] or 0
    kilograms_sold_year = sales_items.filter(product__base_unit=Product.BaseUnit.G).aggregate(total_grams=Sum(F('unit_quantity_base_snapshot') * F('quantity'), output_field=FloatField()))['total_grams'] or 0

    sales_count_month = monthly_sales.values('sale').distinct().count()
    average_ticket = (sales_total_month / sales_count_month) if sales_count_month else 0

    best_selling_product = Product.objects.filter(
        saleitem__sale__sale_date__year=selected_year,
        saleitem__sale__sale_date__month=selected_month,
    ).annotate(total_quantity=Sum('saleitem__quantity')).order_by('-total_quantity').first()
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
        # Use Spanish abbreviated month names for chart labels
        labels.append(month_names_es[month - 1].capitalize())
        period_sales = sales_items.filter(sale__sale_date__year=year, sale__sale_date__month=month)
        period_expenses = expenses_year.filter(date__year=year, date__month=month)
        sales_history.append(period_sales.aggregate(total=Sum(F('unit_price') * F('quantity'), output_field=FloatField()))['total'] or 0)
        expenses_history.append(period_expenses.aggregate(total=Sum('amount'))['total'] or 0)
        kg_history.append((period_sales.filter(product__base_unit=Product.BaseUnit.G).aggregate(total_grams=Sum(F('unit_quantity_base_snapshot') * F('quantity'), output_field=FloatField()))['total_grams'] or 0) / 1000)

    categories = ExpenseCategory.objects.all()
    expense_distribution = []
    for category in categories:
        total = monthly_expenses.filter(category=category).aggregate(total=Sum('amount'))['total'] or 0
        expense_distribution.append({'name': category.name, 'total': total})

    stock_bags = 0
    stock_kilos = 0
    for product in Product.objects.filter(
        item_type=Product.ItemType.COFFEE,
        coffee_stage=Product.CoffeeStage.GROUND,
        base_unit=Product.BaseUnit.G,
        is_stock_tracked=True,
    ):
        stock_grams = InventoryService.get_stock(product)
        stock_kilos += stock_grams / 1000
        if product.is_sellable and product.sale_unit_quantity:
            stock_bags += stock_grams / product.sale_unit_quantity

    all_time_sales_total = SaleItem.objects.aggregate(total=Sum(F('unit_price') * F('quantity'), output_field=FloatField()))['total'] or 0
    fallback_bag_price = Product.objects.filter(active=True).aggregate(avg_price=Avg('sale_price'))['avg_price'] or 0
    sold_bags_total = SaleItem.objects.aggregate(total=Sum('quantity'))['total'] or 0
    average_value_per_bag = float(
        (all_time_sales_total / sold_bags_total) if sold_bags_total else fallback_bag_price,
    )
    sales_objective = float(stock_bags) * average_value_per_bag

    reconcile_monthly_summaries(today)

    monthly_records = MonthlySummary.objects.filter(
        Q(year__lt=today.year) | Q(year=today.year, month__lte=today.month),
    ).order_by('-year', '-month')

    context = {
        'current_month_display': current_month_display,
        'selected_month': f'{selected_year:04d}-{selected_month:02d}',
        'available_months': [
            {
                'value': f'{year:04d}-{month:02d}',
                'label': f'{month_names_es[month - 1].capitalize()} {year}',
            }
            for year, month in available_periods
        ],
        'current_year': today.year,
        'sales_total_month': format_cop(sales_total_month),
        'sales_objective': format_cop(sales_objective),
        'sales_objective_note': 'Valor del stock operativo multiplicado por el precio promedio por bolsa.',
        'sales_objective_stock': stock_bags,
        'sales_total_year': format_cop(sales_total_year),
        'expenses_total_year': format_cop(expenses_total_year),
        'profit_year': format_cop(profit_year),
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
        'stock_kilos': stock_kilos,
        'sold_bags_total': sold_bags_total,
        'monthly_records': monthly_records,
        'chart_labels': json.dumps(labels, ensure_ascii=False),
        'chart_sales_data': json.dumps(sales_history),
        'chart_expenses_data': json.dumps(expenses_history),
        'chart_kg_data': json.dumps(kg_history),
        'chart_expense_labels': json.dumps([item['name'] for item in expense_distribution], ensure_ascii=False),
        'chart_expense_values': json.dumps([item['total'] for item in expense_distribution]),
    }
    return render(request, 'dashboard/home.html', context)


def export_month_csv(request, year, month):
    # Export sale items for the given month as CSV
    qs = SaleItem.objects.filter(sale__sale_date__year=year, sale__sale_date__month=month).select_related('product', 'sale')
    filename = f"ventas_{year}_{month:02d}.csv"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    # header
    writer.writerow(['ID Venta', 'Fecha Venta', 'Producto', 'Cantidad', 'Precio Unitario', 'Total'])
    total = 0
    for item in qs:
        line_total = item.unit_price * item.quantity
        total += line_total
        writer.writerow([item.sale.id, item.sale.sale_date, item.product.name, item.quantity, item.unit_price, line_total])
    writer.writerow([])
    writer.writerow(['', '', 'Totales', '', '', total])
    return response


def export_month_xlsx(request, year, month):
    # Lazy import to avoid hard dependency at import time
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, numbers
    except ImportError:
        return HttpResponse('openpyxl is required for XLSX export', status=500)

    qs = SaleItem.objects.filter(sale__sale_date__year=year, sale__sale_date__month=month).select_related('product', 'sale')
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Ventas_{year}_{month:02d}"

    headers = ['ID Venta', 'Fecha Venta', 'Producto', 'Cantidad', 'Precio Unitario', 'Total']
    header_font = Font(bold=True)
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    total = 0
    for row_idx, item in enumerate(qs, start=2):
        line_total = (item.unit_price or 0) * (item.quantity or 0)
        total += line_total
        ws.cell(row=row_idx, column=1, value=item.sale.id)
        ws.cell(row=row_idx, column=2, value=item.sale.sale_date.isoformat())
        ws.cell(row=row_idx, column=3, value=item.product.name)
        ws.cell(row=row_idx, column=4, value=item.quantity)
        ws.cell(row=row_idx, column=5, value=item.unit_price)
        ws.cell(row=row_idx, column=6, value=line_total)

    # Totals row
    total_row = qs.count() + 2
    ws.cell(row=total_row, column=5, value='Totales')
    tot_cell = ws.cell(row=total_row, column=6, value=total)
    tot_cell.font = Font(bold=True)

    # Format columns
    for col in ['E', 'F']:
        for cell in ws[col]:
            try:
                cell.number_format = numbers.FORMAT_CURRENCY_USD_SIMPLE
            except Exception:
                pass

    # Adjust column widths
    dims = {1: 10, 2: 15, 3: 30, 4: 10, 5: 15, 6: 15}
    for col, width in dims.items():
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"ventas_{year}_{month:02d}.xlsx"
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(output.getvalue())
    return response
