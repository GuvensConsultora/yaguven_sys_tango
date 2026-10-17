from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TangoAccount(models.Model):
    """Cuenta del plan de Tango, tal como figura en el SyS del contador."""

    _name = "yaguven.tango.account"
    _description = "Cuenta del plan Tango"
    _order = "company_id, sequence, code"
    _rec_names_search = ["code", "name"]

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    code = fields.Char(string="Código Tango", required=True, index=True)
    name = fields.Char(string="Descripción", required=True)
    sequence = fields.Integer(
        string="Orden",
        default=10,
        help="Posición de la cuenta en el SyS de Tango. El reporte respeta este orden.",
    )
    nature = fields.Selection(
        [
            ("patrimonial", "Patrimonial"),
            ("resultado", "Resultado"),
        ],
        string="Tipo",
        required=True,
        default="patrimonial",
        help="Patrimonial: el saldo deudor va a Activo y el acreedor a Pasivo.\n"
        "Resultado: el saldo deudor va a Resultado negativo y el acreedor a "
        "Resultado positivo.",
    )
    mapping_ids = fields.One2many(
        "yaguven.tango.mapping",
        "tango_account_id",
        string="Cuentas Odoo",
    )
    mapping_count = fields.Integer(
        string="Cuentas Odoo asignadas",
        compute="_compute_mapping_count",
    )
    active = fields.Boolean(default=True)

    _code_company_uniq = models.Constraint(
        "UNIQUE(company_id, code)",
        "Ese código Tango ya existe en esta compañía.",
    )

    @api.depends("mapping_ids")
    def _compute_mapping_count(self):
        for rec in self:
            rec.mapping_count = len(rec.mapping_ids)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} {rec.name}" if rec.code else rec.name


class TangoMapping(models.Model):
    """Equivalencia cuenta Odoo -> cuenta Tango, por compañía.

    Varias cuentas Odoo pueden ir a una misma cuenta Tango (el plan de Odoo es
    una apertura del de Tango); cada cuenta Odoo va a una sola cuenta Tango.
    """

    _name = "yaguven.tango.mapping"
    _description = "Equivalencia cuenta Odoo - cuenta Tango"
    _order = "company_id, tango_account_id, account_id"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Cuenta Odoo",
        required=True,
        index=True,
        ondelete="cascade",
        domain="[('company_ids', 'in', company_id)]",
    )
    tango_account_id = fields.Many2one(
        "yaguven.tango.account",
        string="Cuenta Tango",
        required=True,
        index=True,
        ondelete="cascade",
        domain="[('company_id', '=', company_id)]",
    )
    note = fields.Char(
        string="Criterio",
        help="Por qué esta cuenta Odoo va a esa cuenta Tango (queda como documentación).",
    )

    _account_company_uniq = models.Constraint(
        "UNIQUE(company_id, account_id)",
        "Esa cuenta Odoo ya tiene equivalencia Tango en esta compañía.",
    )

    @api.constrains("company_id", "tango_account_id", "account_id")
    def _check_company(self):
        for rec in self:
            if rec.tango_account_id.company_id != rec.company_id:
                raise ValidationError(
                    "La cuenta Tango pertenece a otra compañía."
                )
            if rec.company_id not in rec.account_id.company_ids:
                raise ValidationError(
                    "La cuenta Odoo no está habilitada en esta compañía."
                )
