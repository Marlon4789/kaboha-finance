# Kaboha Finance

Kaboha Finance es una aplicación web diseñada para administrar finanzas, ventas y rentabilidad de un negocio de café de especialidad.

## Instalación

1. Crear el entorno virtual:

```bash
python -m venv venv
```

2. Activar el entorno:

```bash
source venv/bin/activate
```

3. Instalar dependencias:

```bash
pip install -r requirements.txt
```
```

4. Configurar la base de datos en `.env`.

5. Ejecutar migraciones:

```bash
python manage.py makemigrations
python manage.py migrate
```

6. Crear superusuario:

```bash
python manage.py createsuperuser
```

7. Ejecutar servidor:

```bash
python manage.py runserver
```

## Características

- Dashboard financiero con ventas, gastos, utilidad, margen y kilos vendidos.
- Gestión de productos con cálculo automático de ganancia y margen.
- Registro de ventas con items, gramos y total.
- Control de gastos por categorías.
- Gráficos responsivos con Chart.js.

## Documentación

- `infoLocal/README.md`
- `infoLocal/TODO.md`
- `infoLocal/CHANGELOG.md`
- `infoLocal/BUSINESS_RULES.md`
