from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Expense
from .forms import ExpenseForm


def expense_list(request):
    expenses = Expense.objects.order_by('-date')
    return render(request, 'expenses/list.html', {'expenses': expenses})


def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(reverse('expense_list'))
    else:
        form = ExpenseForm()
    return render(request, 'expenses/form.html', {'form': form, 'title': 'Nuevo gasto'})


def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            return redirect(reverse('expense_list'))
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'expenses/form.html', {'form': form, 'title': 'Editar gasto'})


def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        return redirect(reverse('expense_list'))
    return render(request, 'confirm_delete.html', {
        'object_name': f'Gasto {expense}',
        'cancel_url': reverse('expense_list'),
    })
