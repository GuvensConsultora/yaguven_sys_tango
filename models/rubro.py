from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .rubros_catalogo import CATALOGO_RT59

SECCIONES = [
    ("activo_corriente", "Activo corriente"),
    ("activo_no_corriente", "Activo no corriente"),
    ("pasivo_corriente", "Pasivo corriente"),
    ("pasivo_no_corriente", "Pasivo no corriente"),
    ("patrimonio_neto", "Patrimonio neto"),
    ("resultado", "Estado de resultados"),
]


class Rubro(models.Model):
    """Rubro de exposición de los estados contables.

    Los rubros son los de la RT 59 (texto ordenado de la RT 54, Norma Unificada
    Argentina de Contabilidad), según el modelo de estados contables del Informe
    CENCyA N° 27. El catálogo se carga por compañía —así cada una puede ajustar
    el orden, el nombre o dar de baja un rubro que no usa sin tocar a las demás—
    y la asociación con el plan de cuentas vive en yaguven.rubro.mapping.
    """

    _name = "yaguven.rubro"
    _description = "Rubro de exposición de los estados contables (RT 59)"
    _order = "sequence, code"
    _rec_names_search = ["code", "name"]

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Rubro", required=True)
    section = fields.Selection(
        SECCIONES,
        string="Sección",
        required=True,
        help="Dónde se expone el rubro. Las cuatro primeras arman el estado de "
        "situación patrimonial junto con el patrimonio neto; la última, el "
        "estado de resultados.",
    )
    sequence = fields.Integer(
        string="Orden",
        default=10,
        help="Posición del rubro dentro de su sección, en el orden de exposición "
        "del modelo del Informe CENCyA N° 27.",
    )
    expense_function = fields.Selection(
        [
            ("comercializacion", "Comercialización"),
            ("administracion", "Administración"),
            ("financiero", "Financieros"),
        ],
        string="Función del gasto",
        help="Si se completa, el rubro entra en el cuadro de gastos por función "
        "con esta columna. Se deja vacío en los rubros que no son gastos.",
    )
    mapping_ids = fields.One2many(
        "yaguven.rubro.mapping",
        "rubro_id",
        string="Cuentas y grupos asociados",
    )
    mapping_count = fields.Integer(
        string="Asociaciones",
        compute="_compute_mapping_count",
    )
    active = fields.Boolean(string="Activo", default=True)

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(company_id, code)",
            "Ya existe un rubro con ese código en esta compañía.",
        ),
    ]

    @api.depends("mapping_ids")
    def _compute_mapping_count(self):
        data = self.env["yaguven.rubro.mapping"]._read_group(
            [("rubro_id", "in", self.ids)], ["rubro_id"], ["__count"]
        )
        contados = {rubro.id: cantidad for rubro, cantidad in data}
        for rubro in self:
            rubro.mapping_count = contados.get(rubro.id, 0)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rubro in self:
            rubro.display_name = f"{rubro.code} {rubro.name}"

    def es_patrimonial(self):
        self.ensure_one()
        return self.section != "resultado"

    @api.model
    def cargar_catalogo(self, companies=None):
        """Carga los rubros de la RT 59 en las compañías indicadas.

        Crea sólo los que faltan, comparando por (compañía, código): se puede
        volver a correr sin duplicar nada y sin pisar lo que alguien haya
        ajustado a mano.
        """
        companies = companies or self.env["res.company"].search([])
        existentes = {
            (r.company_id.id, r.code)
            for r in self.with_context(active_test=False).search(
                [("company_id", "in", companies.ids)]
            )
        }
        nuevos = [
            {
                "company_id": company.id,
                "code": code,
                "name": name,
                "section": section,
                "sequence": sequence,
                "expense_function": expense_function,
            }
            for company in companies
            for code, name, section, sequence, expense_function in CATALOGO_RT59
            if (company.id, code) not in existentes
        ]
        return self.create(nuevos) if nuevos else self.browse()

    @api.model
    def action_cargar_catalogo(self):
        """Acción del menú: carga el catálogo en la compañía activa."""
        creados = self.cargar_catalogo(self.env.company)
        mensaje = (
            f"Se cargaron {len(creados)} rubros en {self.env.company.display_name}."
            if creados
            else f"{self.env.company.display_name} ya tiene el catálogo completo."
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Rubros de los estados contables",
                       "message": mensaje, "type": "info", "sticky": False},
        }


class RubroMapping(models.Model):
    """Asociación entre el plan de cuentas y el rubro con el que se expone.

    Se puede mapear un grupo entero (todas sus cuentas) o una cuenta puntual; la
    cuenta le gana al grupo. Dos situaciones que el mapeo plano no resuelve y
    acá sí:

    - El rubro depende del SIGNO del saldo. Una cuenta bancaria a favor es
      «Caja y bancos» (RT 59 párr. 205: medio de pago) y la misma cuenta en
      descubierto es «Préstamos y otros pasivos financieros» (párr. 610 b). No
      se netean entre bancos distintos (párr. 626), así que el rubro se decide
      cuenta por cuenta y a la fecha de cada columna del informe.
    - La cuenta REGULARIZA un rubro en vez de integrarlo como partida propia:
      la amortización acumulada respecto de bienes de uso, o las mercaderías
      entregadas y recibidas pendientes de facturar respecto de bienes de
      cambio. Hace a la medición del rubro, no es la compensación del párr. 626.
    """

    _name = "yaguven.rubro.mapping"
    _description = "Equivalencia plan de cuentas → rubro de exposición"
    _order = "company_id, rubro_id"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Cuenta",
        index=True,
        ondelete="cascade",
        help="Si se completa, la regla vale sólo para esta cuenta y le gana a la "
        "del grupo.",
    )
    group_id = fields.Many2one(
        "account.group",
        string="Grupo de cuentas",
        index=True,
        ondelete="cascade",
        help="Si se completa, la regla vale para todas las cuentas del grupo que "
        "no tengan una regla propia.",
    )
    rubro_id = fields.Many2one(
        "yaguven.rubro",
        string="Rubro",
        required=True,
        ondelete="restrict",
    )
    condition = fields.Selection(
        [
            ("always", "Siempre"),
            ("debit", "Si el saldo es deudor"),
            ("credit", "Si el saldo es acreedor"),
        ],
        string="Condición",
        required=True,
        default="always",
        help="Con «Siempre», la cuenta va al rubro cualquiera sea su saldo. Con "
        "las otras dos, va al rubro cuando el saldo tiene ese signo y al rubro "
        "alternativo cuando tiene el contrario.",
    )
    rubro_alt_id = fields.Many2one(
        "yaguven.rubro",
        string="Rubro alternativo",
        ondelete="restrict",
        help="El rubro que corresponde cuando el saldo tiene el signo contrario "
        "al de la condición.",
    )
    is_regularizing = fields.Boolean(
        string="Regulariza el rubro",
        help="La cuenta no se expone como partida propia: netea el rubro. Es el "
        "caso de la amortización acumulada o de las mercaderías pendientes de "
        "facturar.",
    )
    subrubro = fields.Char(
        string="Sub-rubro",
        help="Agrupa la cuenta dentro del rubro en un sub-rubro (ej. cada clase de "
        "bien de uso con su amortización), para exponer el valor actual neto. Las "
        "cuentas con el mismo texto de sub-rubro se muestran juntas.",
    )
    note = fields.Char(
        string="Fundamento",
        help="Por qué esta cuenta se expone en este rubro. Queda a la vista en el "
        "papel de trabajo del contador.",
    )

    @api.constrains("account_id", "group_id")
    def _check_account_or_group(self):
        for mapeo in self:
            if bool(mapeo.account_id) == bool(mapeo.group_id):
                raise ValidationError(
                    "Cada equivalencia se define por una cuenta o por un grupo, "
                    "no por los dos ni por ninguno."
                )

    @api.constrains("condition", "rubro_alt_id")
    def _check_rubro_alt(self):
        for mapeo in self:
            if mapeo.condition != "always" and not mapeo.rubro_alt_id:
                raise ValidationError(
                    f"La equivalencia de {mapeo.display_name} depende del signo "
                    "del saldo: falta el rubro alternativo."
                )
            if mapeo.condition == "always" and mapeo.rubro_alt_id:
                raise ValidationError(
                    "El rubro alternativo sólo tiene sentido cuando la "
                    "equivalencia depende del signo del saldo."
                )

    @api.constrains("company_id", "account_id", "group_id")
    def _check_company(self):
        for mapeo in self:
            cuenta = mapeo.account_id
            if cuenta and mapeo.company_id not in cuenta.company_ids:
                raise ValidationError(
                    f"La cuenta {cuenta.display_name} no pertenece a "
                    f"{mapeo.company_id.display_name}."
                )
            grupo = mapeo.group_id
            if grupo and grupo.company_id and grupo.company_id != mapeo.company_id:
                raise ValidationError(
                    f"El grupo {grupo.display_name} no pertenece a "
                    f"{mapeo.company_id.display_name}."
                )

    @api.depends("account_id", "group_id", "rubro_id")
    def _compute_display_name(self):
        for mapeo in self:
            origen = mapeo.account_id.display_name or mapeo.group_id.display_name
            mapeo.display_name = f"{origen} → {mapeo.rubro_id.name}"

    def rubro_por_saldo(self, saldo):
        """El rubro que corresponde a este saldo, resolviendo la condición."""
        self.ensure_one()
        if self.condition == "always":
            return self.rubro_id
        if self.condition == "debit":
            return self.rubro_id if saldo >= 0 else self.rubro_alt_id
        return self.rubro_id if saldo <= 0 else self.rubro_alt_id
