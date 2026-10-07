# TODO

## Pendiente (Cafena v1)

- UI mínima para fincas, lotes, ciclos, actividades (con insumos y mano de obra), lotes de producción, calidad, sanidad y tareas.
- Pantalla de trazabilidad y de costos por ciclo/lote (los servicios ya existen).
- Costo de la cereza cosechada (`HARVEST_IN.unit_cost` sigue en `NULL`): definir la política de asignación.
- Costos de proceso (mano de obra e insumos del beneficio) en lotes de producción; requiere decidir el modelo y una migración.
- Significado y escala de `QualityAssessment.factor`.
- Fuente de árboles para métricas por árbol (`Lot.current_tree_count` vs `CropCycle.planted_tree_count`).
- Utilidad por lote: ingresos de venta menos costo vendido (`SALE_OUT.unit_cost`).
- Login propio para usuarios que no son staff (hoy se usa el login del admin).
- Prueba de concurrencia en PostgreSQL para el consumo de inventario.
- Decisión de renombrado de `kaboha_finance`.
