from odoo import fields, models


class AccountAccount(models.Model):
    """Campo propio para dejar una cuenta (y sus asientos) fuera del SyS Tango.

    Sólo agrega un campo nuevo: no redefine ninguno nativo. Cada cuenta del plan
    pertenece a una sola compañía, así que un tilde por cuenta alcanza.
    """

    _inherit = "account.account"

    sys_tango_excluded = fields.Boolean(
        string="Excluir del SyS Tango",
        index=True,
        help="Tildada, esta cuenta no aparece en el balance de sumas y saldos con "
        "plan Tango y tampoco aparecen los asientos que la tocan, con todas sus "
        "contrapartidas. El listado informa al pie cuántos asientos y qué importe "
        "quedaron afuera. No afecta a la contabilidad ni a ningún otro reporte.",
    )
