{
    'name': 'Sumas y Saldos con plan Tango - Yagüven',
    'version': '19.0.2.10.0',
    'category': 'Accounting',
    'summary': 'Balance de sumas y saldos agrupado por el plan de cuentas de Tango',
    'description': """
Presenta el balance de sumas y saldos de Odoo con la estructura del plan de
cuentas de Tango (código, descripción, orden y columnas Activo / Pasivo /
Resultado negativo / Resultado positivo), para que los papeles de trabajo del
contador sigan siendo comparables después de la migración.

- Plan Tango por compañía, importado desde el xlsx de sumas y saldos de Tango.
- Equivalencias cuenta Odoo -> cuenta Tango en tabla propia (en account.account
  sólo se agrega el tilde de exclusión, sin tocar ningún campo nativo).
- Equivalencias por diario (opcionales): una cuenta Odoo que en Tango estaría
  repartida (p. ej. cobros pendientes de acreditación → tarjeta o banco) se
  reparte según el diario del movimiento; lo que no tiene regla va a la general.
- Renglón «Sin equivalencia» para que el total cuadre siempre con el SyS de Odoo.
- Tilde «Excluir del SyS Tango» en la cuenta: esa cuenta no aparece en el listado y
  tampoco los asientos que la tocan, con todas sus contrapartidas. El pie informa
  cuántos asientos y qué importe quedaron afuera.

Hereda sólo de nativos: lee account.move.line como datasource.
""",
    'author': 'Yagüven C.G.',
    'license': 'AGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/acciones.xml',
        'views/tango_account_views.xml',
        'views/account_account_views.xml',
        'views/rubro_views.xml',
        'views/apertura_impositivo_views.xml',
        'wizard/tango_import_wizard_views.xml',
        'wizard/sys_tango_wizard_views.xml',
        'views/menu.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
