"""Catálogo de rubros de exposición de la RT 59 (texto ordenado de la RT 54, Norma
Unificada Argentina de Contabilidad), en el orden del modelo de estados contables del
Informe CENCyA N° 27.

Es la plantilla con la que se carga cada compañía: los rubros se crean por compañía,
de modo que una pueda ajustar nombre, orden o dar de baja el que no usa sin afectar a
las otras. Cargarlo de nuevo sólo agrega los que falten.

Cada fila: (código, nombre, sección, orden, función del gasto).
"""

CATALOGO_RT59 = [
    # ── Activo corriente
    ("AC.01", "Caja y bancos", "activo_corriente", 10, None),
    ("AC.02", "Inversiones financieras", "activo_corriente", 20, None),
    ("AC.03", "Cuentas por cobrar a clientes en moneda", "activo_corriente", 30, None),
    ("AC.04", "Cuentas por cobrar a clientes en especie", "activo_corriente", 40, None),
    ("AC.05", "Créditos impositivos", "activo_corriente", 50, None),
    ("AC.06", "Créditos con partes relacionadas", "activo_corriente", 60, None),
    ("AC.07", "Otras cuentas por cobrar en moneda", "activo_corriente", 70, None),
    ("AC.08", "Otras cuentas por cobrar en especie", "activo_corriente", 80, None),
    ("AC.09", "Bienes de cambio", "activo_corriente", 90, None),
    ("AC.10", "Otras inversiones", "activo_corriente", 100, None),
    ("AC.11", "Otros activos", "activo_corriente", 110, None),
    # ── Activo no corriente
    ("ANC.01", "Inversiones financieras", "activo_no_corriente", 10, None),
    ("ANC.02", "Cuentas por cobrar a clientes en moneda", "activo_no_corriente", 20, None),
    ("ANC.03", "Créditos impositivos", "activo_no_corriente", 30, None),
    ("ANC.04", "Créditos con partes relacionadas", "activo_no_corriente", 40, None),
    ("ANC.05", "Otras cuentas por cobrar en moneda", "activo_no_corriente", 50, None),
    ("ANC.06", "Bienes de cambio", "activo_no_corriente", 60, None),
    ("ANC.07", "Bienes de uso", "activo_no_corriente", 70, None),
    ("ANC.08", "Propiedades de inversión", "activo_no_corriente", 80, None),
    ("ANC.09", "Otras inversiones", "activo_no_corriente", 90, None),
    ("ANC.10", "Activos intangibles", "activo_no_corriente", 100, None),
    ("ANC.11", "Otros activos", "activo_no_corriente", 110, None),
    # ── Pasivo corriente
    ("PC.01", "Proveedores de bienes y servicios", "pasivo_corriente", 10, None),
    ("PC.02", "Préstamos y otros pasivos financieros", "pasivo_corriente", 20, None),
    ("PC.03", "Deudas fiscales", "pasivo_corriente", 30, None),
    ("PC.04", "Deudas laborales y previsionales", "pasivo_corriente", 40, None),
    ("PC.05", "Deudas en especie", "pasivo_corriente", 50, None),
    ("PC.06", "Deudas con partes relacionadas", "pasivo_corriente", 60, None),
    ("PC.07", "Otras deudas", "pasivo_corriente", 70, None),
    ("PC.08", "Subsidios y otras ayudas gubernamentales", "pasivo_corriente", 80, None),
    ("PC.09", "Previsiones", "pasivo_corriente", 90, None),
    # ── Pasivo no corriente
    ("PNC.01", "Proveedores de bienes y servicios", "pasivo_no_corriente", 10, None),
    ("PNC.02", "Préstamos y otros pasivos financieros", "pasivo_no_corriente", 20, None),
    ("PNC.03", "Deudas fiscales", "pasivo_no_corriente", 30, None),
    ("PNC.04", "Deudas laborales y previsionales", "pasivo_no_corriente", 40, None),
    ("PNC.05", "Deudas con partes relacionadas", "pasivo_no_corriente", 50, None),
    ("PNC.06", "Otras deudas", "pasivo_no_corriente", 60, None),
    ("PNC.07", "Pasivo neto por impuesto diferido", "pasivo_no_corriente", 70, None),
    ("PNC.08", "Previsiones", "pasivo_no_corriente", 80, None),
    # ── Patrimonio neto
    ("PN.01", "Patrimonio neto", "patrimonio_neto", 10, None),
    # ── Estado de resultados
    ("ER.01", "Ingresos netos por la venta de bienes y prestación de servicios", "resultado", 10, None),
    ("ER.02", "Costo de los bienes vendidos y servicios prestados", "resultado", 20, None),
    ("ER.03", "Gastos de comercialización", "resultado", 30, "comercializacion"),
    ("ER.04", "Gastos de administración", "resultado", 40, "administracion"),
    ("ER.05", "Otros gastos operativos", "resultado", 50, None),
    ("ER.06", "Cambios en el valor razonable de propiedades de inversión", "resultado", 60, None),
    ("ER.07", "Pérdidas por desvalorización y sus reversiones", "resultado", 70, None),
    ("ER.08", "Otros resultados financieros y por tenencia (incluye el resultado por los cambios en el poder adquisitivo de la moneda)", "resultado", 80, "financiero"),
    ("ER.09", "Otros ingresos", "resultado", 90, None),
    ("ER.10", "Otros egresos", "resultado", 100, None),
    ("ER.11", "Impuesto a las ganancias", "resultado", 110, None),
    ("ER.12", "Resultado por actividades u operaciones discontinuadas", "resultado", 120, None),
]
