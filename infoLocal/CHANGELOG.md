# CHANGELOG

## Sin publicar

- Inventario: `InventoryService.consume` acepta capas explícitas (`source_layers`); nuevo `inventory/purchases.py` para recibir compras con costo real ligadas a un `Expense`.
- Agricultura: `record_activity_input` (insumo + consumo atómico), `register_batch_transformation` (lote de producción con costo derivado), `costing.py` (costos de actividad, ciclo y lote) y `traceability.py` (venta → finca).
- Seguridad: las vistas de cosecha exigen login y se limitan a las fincas del usuario.

## 0.1.0

- Proyecto inicial creado.
- Apps: dashboard, products, sales, expenses.
- Configuración básica de Django y PostgreSQL.
- Documentación inicial.
