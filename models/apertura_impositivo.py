from odoo import fields, models

# Mismas secciones patrimoniales que el ESP (ver estados_contables.py). El
# resultado del ejercicio del impositivo, cuando no está cerrado, se carga como
# una línea de patrimonio neto con su propio concepto.
SECCIONES = [
    ("activo_corriente", "Activo corriente"),
    ("activo_no_corriente", "Activo no corriente"),
    ("pasivo_corriente", "Pasivo corriente"),
    ("pasivo_no_corriente", "Pasivo no corriente"),
    ("patrimonio_neto", "Patrimonio neto"),
]


class AperturaImpositivo(models.Model):
    """Apertura del balance IMPOSITIVO, para comparar contra el contable.

    El balance impositivo es otra fuente del mismo cierre (lo arma el contador)
    y no coincide con el contable: por eso no sale de los asientos de Odoo sino
    que se carga acá, línea por línea, con la fecha de corte de la apertura. La
    solapa «Contable vs impositivo» del reporte de sumas y saldos enfrenta estos
    importes con los rubros del estado de situación patrimonial.

    Se carga por compañía y es editable: cada línea lleva su sección, para que
    el subtotal del impositivo se compare contra el total contable del mismo
    tramo (activo corriente, pasivo corriente, patrimonio neto, etc.).
    """

    _name = "yaguven.apertura.impositivo"
    _description = "Apertura del balance impositivo (para comparar con el contable)"
    _order = "company_id, fecha, sequence, id"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    fecha = fields.Date(
        string="Fecha de la apertura",
        required=True,
        help="Fecha de corte del balance impositivo (por ejemplo 31/05/2025). "
        "La solapa compara contra el saldo contable a esa misma fecha.",
    )
    sequence = fields.Integer(string="Orden", default=10)
    section = fields.Selection(
        SECCIONES,
        string="Sección",
        required=True,
        help="Tramo del estado de situación patrimonial al que pertenece la "
        "línea. El subtotal del impositivo de cada sección se compara con el "
        "total contable de esa sección.",
    )
    concepto = fields.Char(string="Concepto", required=True)
    importe = fields.Monetary(
        string="Importe",
        help="Importe de la línea en el balance impositivo. En el activo, "
        "deudor positivo; en el pasivo y el patrimonio neto, acreedor positivo.",
    )
    es_subtotal = fields.Boolean(
        string="Es subtotal del rubro",
        help="Marcá las líneas que en la foto del impositivo son el subtotal de "
        "un rubro (no se suman al total: ya están en las líneas de detalle).",
    )
    note = fields.Char(
        string="Fundamento",
        help="Aclaración opcional que queda impresa en el papel de trabajo.",
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda",
        readonly=True,
    )

    def name_get(self):
        return [(r.id, f"{dict(SECCIONES).get(r.section, '')} · {r.concepto}") for r in self]
