"""Solapas de respaldo del balance: composición de deudas y mayores.

Cada una cierra contra la contabilidad: el pie de la hoja compara su total con
el saldo de las cuentas que la componen, así el papel de trabajo no se despega
del balance. Las cuentas no se nombran en el código: salen del rubro al que
están mapeadas, de modo que si mañana se agrega una cuenta al rubro, entra sola.
"""

from odoo import fields, models

# Qué rubros alimentan cada solapa.
RUBROS_PROVEEDORES = ("PC.01", "PNC.01")
RUBROS_ACREEDORES = ("PC.02", "PC.07", "PNC.02", "PNC.06")
RUBROS_VENTAS = ("ER.01",)
RUBROS_COSTO = ("ER.02",)
RUBROS_MERCADERIAS = ("AC.09", "ANC.06")


class SysTangoWizardDetalle(models.TransientModel):
    _inherit = "yaguven.sys.tango.wizard"

    show_detail_sheets = fields.Boolean(
        string="Solapas de respaldo",
        default=True,
        help="Agrega al archivo la composición de proveedores y acreedores y "
        "los mayores de ventas, costo de mercaderías vendidas y mercaderías. "
        "Cada solapa cierra contra el saldo de las cuentas que la componen.",
    )

    # ------------------------------------------------------------ selección

    def _cuentas_de_rubros(self, codigos, saldos=None):
        """Las cuentas de la compañía cuyo rubro cae en esos códigos.

        El rubro se resuelve con el saldo de cada cuenta, porque puede depender
        del signo (una cuenta bancaria en descubierto es un pasivo financiero y
        por eso entra en la solapa de acreedores).
        """
        self.ensure_one()
        por_cuenta, por_grupo = self._mapeos_por_clave()
        if saldos is None:
            saldos = self._saldos_por_cuenta(self.date_to)
        cuentas = self.env["account.account"]
        for account, saldo in saldos.items():
            rubro, _reg, _m = self._rubro_de(account, saldo, por_cuenta, por_grupo)
            if rubro and rubro.code in codigos:
                cuentas |= account
        return cuentas

    def _cuentas_recpam(self):
        """La(s) cuenta(s) de RECPAM de la compañía (resultado por exposición a los
        cambios en el poder adquisitivo de la moneda).

        Se busca por el código del plan Tango con fallback por nombre, para no atar
        el reporte a un id y que resuelva igual en otra compañía.
        """
        self.ensure_one()
        return self.env["account.account"].with_company(self.company_id).search([
            ("company_ids", "in", self.company_id.ids),
            "|",
            ("code", "=", "5.6.1.01.070"),
            ("name", "ilike", "R.E.C.P.A.M"),
        ])

    # -------------------------------------------------------------- lectura

    def _composicion_por_partner(self, cuentas, excluidos=()):
        """[(partner, saldo, abiertas)] por cuenta corriente, más el total."""
        self.ensure_one()
        if not cuentas:
            return [], 0.0
        dominio = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("account_id", "in", cuentas.ids),
            ("date", "<=", self.date_to),
        ]
        if excluidos:
            dominio.append(("move_id", "not in", list(excluidos)))
        AML = self.env["account.move.line"].with_company(self.company_id)
        filas, total = [], 0.0
        abiertas = {}
        for partner, cantidad in AML._read_group(
            dominio + [("full_reconcile_id", "=", False)], ["partner_id"], ["__count"]
        ):
            abiertas[partner] = cantidad
        for partner, debit, credit in AML._read_group(
            dominio, ["partner_id"], ["debit:sum", "credit:sum"]
        ):
            saldo = debit - credit
            total += saldo
            if abs(saldo) < 0.005 and not abiertas.get(partner):
                continue
            filas.append((partner, saldo, abiertas.get(partner, 0)))
        filas.sort(key=lambda f: f[1])
        return filas, total

    def _mayor(self, cuentas, con_saldo_inicial, excluidos=()):
        """[(fecha, asiento, diario, referencia, partner, cuenta, debe, haber,
        acumulado)] del período, precedido por el saldo inicial si corresponde."""
        self.ensure_one()
        if not cuentas:
            return [], 0.0, 0.0
        base = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("account_id", "in", cuentas.ids),
        ]
        if excluidos:
            base.append(("move_id", "not in", list(excluidos)))
        AML = self.env["account.move.line"].with_company(self.company_id)
        inicial = 0.0
        if con_saldo_inicial:
            grupos = AML._read_group(
                base + [("date", "<", self.date_from)], [], ["debit:sum", "credit:sum"]
            )
            if grupos:
                debit, credit = grupos[0]
                inicial = debit - credit
        lineas = AML.search(
            base + [("date", ">=", self.date_from), ("date", "<=", self.date_to)],
            order="date, move_id, id",
        )
        filas, acumulado = [], inicial
        for linea in lineas:
            acumulado += linea.debit - linea.credit
            filas.append((
                linea.date,
                linea.move_id.name,
                linea.journal_id.name,
                linea.move_id.ref or linea.name or "",
                linea.partner_id.display_name or "",
                f"{linea.account_id.code} {linea.account_id.name}",
                linea.debit,
                linea.credit,
                acumulado,
            ))
        return filas, inicial, acumulado

    # -------------------------------------------------------------- escritura

    def _hoja_composicion(self, wb, titulo, cuentas, excluidos):
        from openpyxl.styles import Alignment, Font

        filas, total = self._composicion_por_partner(cuentas, excluidos)
        ws = wb.create_sheet(titulo)
        bold = Font(bold=True)
        ws.append([f"{titulo} al {self.date_to.strftime('%d/%m/%Y')}"])
        ws.cell(1, 1).font = Font(bold=True, size=12)
        ws.append([])
        ws.append(["Razón social", "CUIT", "Saldo", "Partidas abiertas"])
        for cell in ws[ws.max_row]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        encabezado = ws.max_row
        for partner, saldo, abiertas in filas:
            ws.append([
                partner.display_name if partner else "Sin contacto asignado",
                partner.vat or "" if partner else "",
                -saldo,
                abiertas,
            ])
            ws.cell(ws.max_row, 3).number_format = "#,##0.00"
        ws.append(["TOTAL", "", -total, sum(f[2] for f in filas)])
        for cell in ws[ws.max_row]:
            cell.font = bold
        ws.cell(ws.max_row, 3).number_format = "#,##0.00"

        saldo_contable = sum(
            self._saldos_por_cuenta(self.date_to, excluidos).get(c, 0.0)
            for c in cuentas
        )
        diferencia = total - saldo_contable
        ws.append([])
        ws.append(["Control"])
        ws.cell(ws.max_row, 1).font = bold
        ws.append([
            "Suma del listado contra el saldo de las cuentas que lo componen: "
            + ("OK" if self.company_id.currency_id.is_zero(diferencia)
               else f"DIFERENCIA {self._fmt(diferencia)}")
        ])
        ws.append([
            "Cuentas incluidas: "
            + (", ".join(f"{c.code} {c.name}" for c in cuentas) or "ninguna")
        ])
        ws.column_dimensions["A"].width = 52
        for letra, ancho in (("B", 16), ("C", 20), ("D", 18)):
            ws.column_dimensions[letra].width = ancho
        ws.freeze_panes = ws.cell(encabezado + 1, 1)
        return ws

    def _hoja_mayor(self, wb, titulo, cuentas, con_saldo_inicial, excluidos):
        from openpyxl.styles import Alignment, Font

        filas, inicial, final = self._mayor(cuentas, con_saldo_inicial, excluidos)
        ws = wb.create_sheet(titulo)
        bold = Font(bold=True)
        ws.append([
            f"{titulo} — del {self.date_from.strftime('%d/%m/%Y')} "
            f"al {self.date_to.strftime('%d/%m/%Y')}"
        ])
        ws.cell(1, 1).font = Font(bold=True, size=12)
        ws.append([])
        ws.append(["Fecha", "Asiento", "Diario", "Referencia", "Contacto",
                   "Cuenta", "Debe", "Haber", "Saldo acumulado"])
        for cell in ws[ws.max_row]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        encabezado = ws.max_row
        if con_saldo_inicial:
            ws.append(["", "", "", "Saldo al inicio del ejercicio", "", "",
                       "", "", inicial])
            for cell in ws[ws.max_row]:
                cell.font = bold
            ws.cell(ws.max_row, 9).number_format = "#,##0.00"
        for fila in filas:
            ws.append(list(fila))
            for col in (7, 8, 9):
                ws.cell(ws.max_row, col).number_format = "#,##0.00"
            ws.cell(ws.max_row, 1).number_format = "DD/MM/YYYY"
        ws.append(["", "", "", "TOTAL", "", "",
                   sum(f[6] for f in filas), sum(f[7] for f in filas), final])
        for cell in ws[ws.max_row]:
            cell.font = bold
        for col in (7, 8, 9):
            ws.cell(ws.max_row, col).number_format = "#,##0.00"

        saldo_contable = sum(
            self._saldos_por_cuenta(self.date_to, excluidos).get(c, 0.0)
            for c in cuentas
        )
        diferencia = final - saldo_contable
        ws.append([])
        ws.append(["Control"])
        ws.cell(ws.max_row, 1).font = bold
        ws.append([
            "Saldo final del mayor contra el saldo de las cuentas: "
            + ("OK" if self.company_id.currency_id.is_zero(diferencia)
               else f"DIFERENCIA {self._fmt(diferencia)}")
        ])
        ws.append([
            "Cuentas incluidas: "
            + (", ".join(f"{c.code} {c.name}" for c in cuentas) or "ninguna")
        ])
        ws.append([f"Movimientos listados: {len(filas)}"])
        for letra, ancho in (("A", 12), ("B", 22), ("C", 20), ("D", 40),
                             ("E", 36), ("F", 40), ("G", 18), ("H", 18), ("I", 20)):
            ws.column_dimensions[letra].width = ancho
        ws.freeze_panes = ws.cell(encabezado + 1, 1)
        return ws

    def _mayor_mensual(self, cuentas, excluidos=()):
        """[(etiqueta_mes, debe, haber, movimiento, acumulado)] por mes del
        período. Para mayores de resultado (ventas, costo), que no arrastran saldo
        inicial, agrupados por mes en vez de línea por línea."""
        self.ensure_one()
        if not cuentas:
            return [], 0.0
        import calendar
        from datetime import date
        MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        base = [("company_id", "=", self.company_id.id), ("parent_state", "=", "posted"),
                ("account_id", "in", cuentas.ids)]
        if excluidos:
            base.append(("move_id", "not in", list(excluidos)))
        AML = self.env["account.move.line"].with_company(self.company_id)
        filas, acum = [], 0.0
        y, m = self.date_from.year, self.date_from.month
        while (y, m) <= (self.date_to.year, self.date_to.month):
            desde = max(date(y, m, 1), self.date_from)
            hasta = min(date(y, m, calendar.monthrange(y, m)[1]), self.date_to)
            g = AML._read_group(base + [("date", ">=", desde), ("date", "<=", hasta)],
                                [], ["debit:sum", "credit:sum"])
            debit, credit = (g[0] if g else (0.0, 0.0))
            debit, credit = debit or 0.0, credit or 0.0
            acum += debit - credit
            filas.append((f"{MESES[m - 1]} {y}", debit, credit, debit - credit, acum))
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return filas, acum

    def _hoja_mayor_mensual(self, wb, titulo, cuentas, excluidos):
        from openpyxl.styles import Alignment, Font

        filas, final = self._mayor_mensual(cuentas, excluidos)
        ws = wb.create_sheet(titulo)
        bold = Font(bold=True)
        ws.append([f"{titulo} por mes — del {self.date_from.strftime('%d/%m/%Y')} "
                   f"al {self.date_to.strftime('%d/%m/%Y')}"])
        ws.cell(1, 1).font = Font(bold=True, size=12)
        ws.append([])
        ws.append(["Mes", "Debe", "Haber", "Movimiento del mes", "Saldo acumulado"])
        for cell in ws[ws.max_row]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        encabezado = ws.max_row
        for mes, debe, haber, mov, acum in filas:
            ws.append([mes, debe, haber, mov, acum])
            for col in (2, 3, 4, 5):
                ws.cell(ws.max_row, col).number_format = "#,##0.00"
        ws.append(["TOTAL", sum(f[1] for f in filas), sum(f[2] for f in filas),
                   sum(f[3] for f in filas), final])
        for cell in ws[ws.max_row]:
            cell.font = bold
        for col in (2, 3, 4, 5):
            ws.cell(ws.max_row, col).number_format = "#,##0.00"

        saldo_contable = sum(
            self._saldos_por_cuenta(self.date_to, excluidos).get(c, 0.0) for c in cuentas)
        diferencia = final - saldo_contable
        ws.append([])
        ws.append(["Control"])
        ws.cell(ws.max_row, 1).font = bold
        ws.append(["Saldo final del mayor contra el saldo de las cuentas: "
                   + ("OK" if self.company_id.currency_id.is_zero(diferencia)
                      else f"DIFERENCIA {self._fmt(diferencia)}")])
        ws.append(["Cuentas incluidas: "
                   + (", ".join(f"{c.code} {c.name}" for c in cuentas) or "ninguna")])
        for letra, ancho in (("A", 18), ("B", 20), ("C", 20), ("D", 22), ("E", 20)):
            ws.column_dimensions[letra].width = ancho
        ws.freeze_panes = ws.cell(encabezado + 1, 1)
        return ws

    def _build_workbook(self):
        wb = super()._build_workbook()
        if not self.show_detail_sheets:
            return wb
        exclusion = self._excluded_moves()
        excluidos = exclusion["move_ids"]
        saldos = self._saldos_por_cuenta(self.date_to, excluidos)

        self._hoja_composicion(
            wb, "Proveedores", self._cuentas_de_rubros(RUBROS_PROVEEDORES, saldos), excluidos
        )
        self._hoja_composicion(
            wb, "Acreedores", self._cuentas_de_rubros(RUBROS_ACREEDORES, saldos), excluidos
        )
        self._hoja_mayor_mensual(
            wb, "Mayor de ventas", self._cuentas_de_rubros(RUBROS_VENTAS, saldos), excluidos
        )
        self._hoja_mayor_mensual(
            wb, "Mayor de costo de mercaderías",
            self._cuentas_de_rubros(RUBROS_COSTO, saldos), excluidos
        )
        self._hoja_mayor(
            wb, "Mayor de mercaderías", self._cuentas_de_rubros(RUBROS_MERCADERIAS, saldos),
            True, excluidos
        )
        recpam = self._cuentas_recpam()
        if recpam:
            self._hoja_mayor(wb, "Mayor del RECPAM", recpam, True, excluidos)
        return wb
