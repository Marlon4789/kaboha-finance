# Instrucciones de desarrollo para Cafena

## Propósito del proyecto

Cafena es una aplicación web Django para administrar finanzas, ventas, inventario y rentabilidad de un negocio de café especializado. El repositorio conserva el nombre histórico Kaboha Finance en documentación y varios contextos, pero el proyecto actual debe tratarse como Cafena y no renombrar automáticamente módulos, vistas, URLs, clases ni variables solo porque el viejo nombre aún aparece en textos o nombres heredados.

## Comandos del proyecto

La base de datos selecciona SQLite con `DB_SQLITE=true`; sin esa variable, la configuración usa PostgreSQL. Para ejecutar los comandos localmente con SQLite:

```bash
DB_SQLITE=true python manage.py runserver
DB_SQLITE=true python manage.py test
DB_SQLITE=true python manage.py test sales
DB_SQLITE=true python manage.py test agriculture.tests.AgriculturalCoreTests.test_farm_creation_and_owner_relation
DB_SQLITE=true python manage.py check
DB_SQLITE=true python manage.py makemigrations --check --dry-run
```

El comando de prueba específico acepta tanto un módulo o clase como la ruta completa a un método `test_*`. Las dependencias se instalan con `pip install -r requirements.txt`.

## Mapa de arquitectura y flujos

- `kaboha_finance/settings.py` configura las apps y la base de datos; `kaboha_finance/urls.py` monta el dashboard en `/` y conecta las rutas de cada app.
- La aplicación es Django server-rendered: las apps de dominio contienen modelos, formularios, vistas y rutas; las plantillas compartidas viven en `templates/`, y los estilos propios en `static/css/style.css`. El dashboard usa Chart.js.
- `products` mantiene el catálogo y los cálculos de utilidad/margen de cada producto. `sales` relaciona una venta con sus líneas (`SaleItem`); las operaciones de venta y consumo de inventario deben seguir el flujo de `sales/services.py` y `inventory/services.py`, no duplicarse en vistas.
- `expenses` registra gastos asociados a categorías. `dashboard` agrega ventas y gastos por periodo, actualiza `MonthlySummary` como dato derivado y ofrece el historial y las exportaciones CSV/XLSX. Las transacciones son la fuente de verdad; los resúmenes deben poder recalcularse.
- `agriculture` contiene el dominio agrícola (`Farm`, `Lot`, `CropCycle`, actividades, cosechas, producción, calidad, observaciones sanitarias y tareas). `agriculture/services.py` conecta con el inventario las cosechas (`register_harvest_inventory`), los insumos (`record_activity_input`) y los lotes de producción (`register_batch_transformation`); `agriculture/costing.py` deriva costos (nunca se guardan) y `agriculture/traceability.py` rastrea una venta hasta su finca. Revisa también formularios, rutas y pruebas al cambiar esos flujos.
- Reglas del flujo agrícola: los insumos solo se crean con `record_activity_input` (consumo atómico de inventario; el admin no los crea ni edita); un costo desconocido nunca se reemplaza por 0; `Expense` no se suma a los costos agrícolas (ya es la salida de caja del mismo dinero); las compras entran a inventario con `inventory/purchases.py::receive_purchase`, ligadas a un `Expense` existente; el consumo puede elegir capas explícitas con `source_layers` para conservar el origen. Las vistas agrícolas exigen login (`LOGIN_URL` = login del admin) y filtran por `Farm.owner`.
- Los valores financieros se manejan en COP; el peso base se registra en gramos y los reportes lo presentan en kilos. Mantén separadas las cantidades de bolsas, café molido y pergamino.
- La interfaz y los textos de validación son en español colombiano (`es-co`), con zona horaria `America/Bogota`.

## Gate de arquitectura para Cafena v1

Antes de crear modelos, migraciones, apps, vistas o flujos agrícolas nuevos, el agente debe respetar este orden obligatorio:

1. Auditoría del proyecto actual.
2. Identificación de fuentes de verdad y reutilización del dominio existente.
3. Diseño conceptual del núcleo agrícola sin implementar código.
4. Validación arquitectónica y aprobación explícita del usuario.
5. Implementación incremental con migraciones y pruebas.

La intención productiva del sistema es la trazabilidad completa del café desde finca hasta venta y rentabilidad. La línea de trazabilidad principal es:

Farm → Lot → CropCycle → AgriculturalActivity → Harvest → ProductionBatch → QualityAssessment → InventoryMovement → Sale → FinancialTransaction

En v1, el diseño debe ser simple y mantenible. No crear modelos paralelos para fertilización, deshierbe, fumigación, enfermedades o tareas si pueden representarse con entidades generales y relaciones consistentes.

Reglas obligatorias:
- No crear modelos agrícolas ni migraciones sin una auditoría previa y aprobación del diseño.
- No duplicar fuentes de verdad: `Product`, `InventoryMovement`, `Sale`, `Expense` y `MonthlySummary` deben seguir siendo la base del sistema financiero e inventario.
- No crear una segunda contabilidad ni inventario agrícola paralelo al que ya existe.
- Mantener nombres técnicos heredados como `kaboha_finance` a menos que exista una decisión explícita de renombrado.
- Reutilizar el inventario actual para café cereza, pergamino, verde, tostado y molido mediante movimientos y trazabilidad.
- Diseñar primero las entidades core: `Farm`, `Lot`, `CropCycle`, `AgriculturalActivity`, `ActivityInput`, `ActivityLabor`, `Harvest`, `ProductionBatch`, `QualityAssessment`, `HealthObservation`, `Task`.
- Documentar antes de cada implementación: propósito, responsabilidad, relaciones, campos, reglas, fuente de verdad, y datos calculados.

## Dominio agrícola aprobado para v1

El núcleo agrícola debe basarse en las siguientes entidades conceptuales:

- Farm: finca o unidad productiva.
- Lot: unidad física/productiva dentro de una finca.
- CropCycle: ciclo de cultivo y datos específicos del cultivo.
- AgriculturalActivity: actividad agrícola genérica con tipo y contexto.
- ActivityInput: insumo consumido en una actividad.
- ActivityLabor: mano de obra asociada a la actividad.
- Harvest: café recolectado.
- ProductionBatch: transformación / proceso de producción asociado a una cosecha.
- QualityAssessment: evaluaciones de calidad del café.
- HealthObservation: registro sanitario y observaciones del cultivo.
- Task: sistema transversal de tareas con estados mínimos.

No crear modelos de tipos de actividades separados por nombre (fertilización, mantenimiento, poda, etc.) como entidades independientes; la relación debe generalizarse con `AgriculturalActivity` y su tipo.

## Reglas de diseño y seguridad

- Registrar cada dato una sola vez y reutilizarlo en todo el sistema.
- No crear lógica, servicios, vistas o formularios redundantes si ya existe una solución equivalente.
- Mantener una sola fuente de verdad para inventario, costos, ventas y finanzas.
- Evitar cálculos redundantes, duplicados y tablas que repitan información ya derivada.
- No implementar IA, diagnósticos automáticos, predicción climática o automatizaciones complejas en v1.
- Mantener permisos por usuario, aislamiento de datos y validación de entrada en backend.

## Alcance actual del dominio

Usuarios objetivo:
- Dueños o administradores de negocio de café.
- Personal que registra ventas, gastos e inventario.
- Usuarios que revisan métricas de rendimiento del negocio a diario.

Dominio principal:
- Productos y precios.
- Ventas por día con líneas de venta.
- Gastos por categoría.
- Inventario de bolsas y kilos.
- Dashboard financiero con indicadores clave.
- Resúmenes mensuales y exportación de información.

## Arquitectura actual

Proyecto base:
- Django 6.x
- Python 3.12.x
- Apps principales: dashboard, products, sales, expenses, inventory, agriculture
- Plantillas en templates/
- Estilos en static/css/style.css
- JavaScript con Chart.js
- Templates base en templates/base.html

Aplicaciones actuales:
- dashboard: KPI del negocio, historial mensual, gráficos y exportación CSV/XLSX.
- products: catálogo de productos y cálculo de utilidad/margen.
- sales: registro de ventas y detalle por ítem.
- expenses: registro de gastos por categoría.
- inventory: control de entradas de inventario y stock.

Configuración actual:
- settings.py usa Django apps estándar + apps del negocio.
- El proyecto carga variables de entorno con python-dotenv.
- La base de datos usa SQLite por defecto si la variable DB_SQLITE está activa; de lo contrario usa PostgreSQL.
- Zona horaria configurada para America/Bogota.
- Idioma principal: español colombiano (es-co).

## Modelos y relaciones

Modelos principales y relaciones actuales:
- Product: producto vendible; por ejemplo, café, peso, precio de venta y costo de producción.
- Sale: venta principal con fecha, forma de pago, cliente opcional, notas.
- SaleItem: relación muchos a uno con Sale y muchos a uno con Product; representa cada línea de venta.
- ExpenseCategory: categoría de gasto.
- Expense: gasto general con fecha, categoría, descripción y monto.
- InventoryEntry: entrada de inventario con fecha, bolsas y kilos; incluye kilos molidos y kilos pergamino.
- InventoryMovement: movimiento de inventario asociado a operaciones de entrada y salida; revisar sus servicios y migraciones antes de cambiar el cálculo de existencias.
- MonthlySummary: resumen mensual persistido para historial del dashboard.
- Agriculture: `Farm`, `Lot`, `CropCycle`, `AgriculturalActivity`, `ActivityInput`, `ActivityLabor`, `Harvest`, `ProductionBatch`, `QualityAssessment`, `HealthObservation` y `Task`.

Reglas:
- Revisar relaciones existentes antes de crear nuevos modelos.
- Mantener integridad referencial y evitar borrar datos críticos sin evaluar el impacto.
- No agregar campos redundantes a modelos cuando ya existe una propiedad calculada o una relación reutilizable.
- Preferir ForeignKey + related_name claros y consistentes.
- Mantener Meta.ordering y verbose_name cuando el módulo lo requiera.

## Vistas, formularios y rutas

Patrones existentes:
- Cada app usa views CRUD estándar con render, redirect, get_object_or_404.
- Formularios con ModelForm.
- URLs por app con nombre explícito.
- El dashboard principal vive en la raíz del proyecto.

Reglas:
- Mantener la estructura actual de views, forms y urls; no introducir un patrón completamente distinto sin necesidad.
- Reutilizar lógica de negocio existente antes de duplicarla.
- Mantener nombres de rutas actuales y evitar cambios de URL a menos que se justifique claramente.
- Al crear nuevas vistas, seguir la convención de list, create, edit, delete en el módulo.

## Templates y UI/UX

Patrones observados:
- Templates base con Bootstrap 5.
- Uso de Chart.js para paneles.
- Estilos globales en static/css/style.css.
- Interfaz en español.
- Diseño responsive con layouts adaptables.

Reglas:
- Mantener consistencia visual entre módulos.
- Reutilizar componentes y clases existentes antes de crear estilos nuevos.
- Ser claro con jerarquía visual: título, etiqueta, valor, nota, estado.
- Mejorar legibilidad con espacios y contrastes adecuados.
- No crear estilos aislados si ya existe un componente reutilizable.
- Mantener formularios fáciles de entender y con textos claros en español.
- Considerar estados de vacío, error, éxito y carga cuando aplique.

## Seguridad

Reglas obligatorias:
- No introducir secretos ni credenciales en el código.
- Mantener validación y sanitización de formularios.
- Revisar permisos y autorización antes de exponer vistas.
- No exponer datos sensibles innecesariamente.
- Mantener uso seguro de Django: CSRF, modelos sanitizados, queries seguras y validación de entrada.
- Revisar riesgos de XSS, SQL Injection, control de acceso y datos del usuario.

## Testing

Hay pruebas Django en los módulos `dashboard`, `products`, `sales`, `expenses`, `inventory` y `agriculture`, incluidas pruebas de servicios e integraciones entre apps.

Reglas:
- Crear tests para lógica de negocio relevante.
- Crear tests para modelos importantes y relaciones clave.
- Crear tests para formularios cuando los haya.
- Crear tests para vistas y permisos si se agregan.
- Crear tests para casos límite y regresiones.
- Si una funcionalidad afecta datos o permisos, considerar pruebas de integración.
- No dar una tarea como terminada sin ejecutar los tests correspondientes.

## Base de datos y migraciones

Reglas obligatorias:
- Cualquier cambio en modelos requiere migración Django.
- No producir cambios manuales de schema fuera de migraciones.
- Antes de crear nuevos modelos, revisar modelos y relaciones existentes para no duplicar entidades.
- Mantener compatibilidad con la base de datos actual del proyecto.
- Considerar la naturaleza de SQLite local y PostgreSQL por entorno.
- No eliminar datos, campos o modelos existentes sin evaluar impacto explícito.

## Documentación y mantenimiento

Documentación relevante existente:
- README.md
- infoLocal/README.md
- infoLocal/TODO.md
- infoLocal/CHANGELOG.md
- infoLocal/BUSINESS_RULES.md

Reglas:
- Mantener la documentación central en README y archivos dentro de infoLocal.
- Referenciar documentación existente antes de crear duplicados.
- Documentar decisiones importantes de negocio o arquitectura cuando un cambio lo requiera.

## Reutilización y arquitectura

Reglas clave:
- Antes de crear un módulo nuevo, revisar si existe ya funcionalidad reutilizable.
- No duplicar lógica de negocio, validación, cálculos o componentes visuales.
- Mantener la solución simple, mantenible y fácil de entender.
- Evitar refactorizaciones grandes si el cambio solicitado es pequeño.
- Priorizar mejoras incrementales sobre reescrituras profundas.

## Política de extensión del dominio agrícola

Los módulos de cultivo, cosecha, fertilización, enfermedades, lotes, café verde y factor de rendimiento son una extensión futura. Antes de crear modelos Django nuevos se debe:

1. Identificar las entidades y sus límites de dominio.
2. Definir las relaciones y cardinalidades.
3. Identificar la fuente de verdad de cada dato.
4. Identificar los datos derivados o calculados.
5. Definir las unidades de medida y sus conversiones.
6. Definir las reglas de negocio y los estados del ciclo de vida.
7. Analizar la trazabilidad desde finca y lote hasta café verde y venta.
8. Analizar el impacto sobre el inventario existente y sus movimientos.
9. Analizar el impacto financiero, costos de producción, ingresos y rentabilidad.
10. Analizar permisos, roles y datos sensibles.
11. Definir las pruebas necesarias, incluidos casos de conversión, rendimiento, calidad e integridad histórica.

No crear modelos, migraciones o apps agrícolas como placeholders antes de aprobar este diseño. Mantener el nombre técnico `kaboha_finance` y los identificadores heredados hasta que exista una decisión explícita de renombrado.

## Proceso obligatorio antes de implementar un nuevo módulo

1. Revisar modelos existentes y relaciones.
2. Revisar si ya existe una solución similar o reutilizable.
3. Definir la entidad y la regla de negocio.
4. Definir impacto sobre apps actuales.
5. Definir rutas, formularios y templates necesarios.
6. Definir y preparar tests mínimos antes de la implementación funcional; ejecutarlos y ajustarlos después de implementar.
7. Implementar con compatibilidad y mínimo riesgo.
8. Revisar seguridad, UX y consistencia.
9. Ejecutar tests relevantes.
10. Documentar decisiones importantes.

## Proceso obligatorio después de cualquier modificación relevante

1. Ejecutar tests del dominio afectado.
2. Revisar migraciones si hubo cambios de esquema.
3. Revisar que no se rompió comportamiento existente.
4. Revisar seguridad y validación en formularios y vistas.
5. Confirmar que la UI sigue consistente y responsive.
6. Informar:
   - Qué se modificó.
   - Qué archivos fueron tocados.
   - Qué decisiones arquitectónicas se tomaron.
   - Qué riesgos o pendientes quedaron.
   - Qué tests se ejecutaron.
   - Resultado de los tests.

## Reglas generales para Copilot / Claude

- No inventar información que no esté respaldada por el repositorio.
- No asumir tecnologías que no existan en el proyecto.
- Si algo no está claro, señalarlo explícitamente.
- No reemplazar una arquitectura existente sin una justificación documentada.
- Mantener compatibilidad con módulos actuales.
- Evitar cambios funcionales innecesarios.
- Preferir soluciones pequeñas, simples y mantenibles.
- No eliminar funcionalidades existentes sin analizar impacto y documentarlo.
- Mantener el código en español cuando el proyecto está orientado a usuarios locales, salvo que la convención del dominio lo requiera.
- Respetar el nombre actual del proyecto como Cafena y no renombrar de manera automática elementos heredados de Kaboha Finance sin una decisión explícita.

## Observaciones importantes del repositorio

- El proyecto ya incluye lógica de dashboard, ventas, gastos, inventario, exportación y resúmenes mensuales.
- Hay una intención clara de análisis financiero y control operativo, no una arquitectura microservicios ni una separación de capas compleja.
- El enfoque actual es simple, Django-first y orientado a negocio local.
- La mejor práctica aquí es seguir el patrón ya existente: app por dominio, convenciones CRUD, templates Bootstrap, lógica clara y pruebas por módulo.
