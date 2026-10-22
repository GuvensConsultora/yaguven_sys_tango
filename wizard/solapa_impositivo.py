"""Solapa «Contable vs impositivo»: enfrenta el balance contable (legalizado,
que sale de los asientos) con el balance impositivo (que carga el contador en
yaguven.apertura.impositivo) a la fecha de apertura del ejercicio.

Son dos fuentes del mismo cierre y no coinciden. La solapa muestra el detalle
del impositivo línea por línea, el subtotal de cada sección contra el total
contable de esa sección, y la conciliación de la diferencia (la del activo tiene
que ser igual a la del pasivo más la del patrimonio neto). No cambia ningún
asiento: es un papel de trabajo.
"""

from odoo import fields, models

from .estados_contables import ACTIVO, PASIVO, SECCIONES_ESP


class SysTangoWizardImpositivo(models.TransientModel):
    _inherit = "yaguven.sys.tango.wizard"

    show_impositivo = fields.Boolean(
        string="Contable vs impositivo",
        default=False,
        help="Agrega una solapa que compara el balance contable con el "
        "impositivo cargado en Contabilidad → Configuración → Apertura del "
        "balance impositivo, a la fecha de cierre anterior (la apertura del "
        "ejercicio). Si no hay impositivo cargado para esa fecha, no se agrega.",
    )

    # -------------------------------------------------------------- datos

    def _impositivo_por_seccion(self, fecha):
        """{seccion: {'detalle': [(concepto, importe)], 'total': importe}}.

        El total de la sección sale de las líneas de detalle (las marcadas como
        subtotal no se suman: están para reproducir la foto, no para medir).
        """
        self.ensure_one()
        lineas = self.env["yaguven.apertura.impositivo"].search(
            [("company_id", "=", self.company_id.id), ("fecha", "=", fecha)],
            order="sequence, id",
        )
        datos = {}
        for ln in lineas:
            d = datos.setdefault(ln.section, {"detalle": [], "total": 0.0})
            d["detalle"].append((ln.concepto, ln.importe, ln.es_subtotal))
            if not ln.es_subtotal:
                d["total"] += ln.importe
        return datos, bool(lineas)

    def _contable_por_seccion(self, datos):
        """{seccion: saldo contable al cierre anterior}, en signo de exposición
        (activo deudor positivo; pasivo y patrimonio neto acreedor positivo)."""
        self.ensure_one()
        Rubro = self.env["yaguven.rubro"]
        out = {}
        for seccion, _t in SECCIONES_ESP:
            total = 0.0
            for rubro in Rubro.search([("section", "=", seccion),
                                       ("company_id", "=", self.company_id.id)]):
                d = datos["esp"]["comparativo"].get(rubro)
                if not d:
                    continue
                bruto = sum(d["partidas"].values()) + sum(d["regul"].values())
                total += -bruto if (seccion in PASIVO or seccion == "patrimonio_neto") else bruto
            if seccion == "patrimonio_neto":
                total += datos["resultado_acumulado"]["comparativo"]
            out[seccion] = total
        # las cuentas sin rubro, netas, van al corriente para que el total cuadre
        sin = (datos.get("esp_sin_rubro") or {}).get("comparativo") or {}
        neto = sum(sin.values())
        if neto >= 0:
            out["activo_corriente"] += neto
        else:
            out["pasivo_corriente"] += -neto
        return out

    # -------------------------------------------------------------- la hoja

    def _build_workbook(self):
        wb = super()._build_workbook()
        if not self.show_impositivo:
            return wb
        fecha = fields.Date.subtract(self.date_from, days=1)
        impositivo, hay = self._impositivo_por_seccion(fecha)
        if not hay:
            return wb
        from openpyxl.styles import Alignment, Border, Font, Side

        datos = self._datos_estados()
        contable = self._contable_por_seccion(datos)

        ws = wb.create_sheet("Contable vs impositivo")
        bold = Font(bold=True)
        big = Font(bold=True, size=12)
        sec_f = Font(bold=True, size=11)
        det_f = Font(italic=True, color="555555")
        top = Border(top=Side(style="thin"))
        num = "#,##0.00"
        company = self.company_id

        def fila(concepto, c, i, kind="det"):
            dif = round((c or 0.0) - (i or 0.0), 2) if (c is not None and i is not None) else None
            sangria = "        " if kind == "det" else ""
            ws.append([f"{sangria}{concepto}", c, i, dif])
            r = ws.max_row
            for col in (2, 3, 4):
                ws.cell(r, col).number_format = num
            font = {"sec": sec_f, "subtot": bold, "total": bold, "det": det_f}.get(kind)
            if font:
                for cell in ws[r]:
                    cell.font = font
            if kind == "total":
                for cell in ws[r]:
                    cell.border = top

        ws.append([f"{company.name} — Apertura al {fecha.strftime('%d/%m/%Y')}"])
        ws.cell(ws.max_row, 1).font = big
        ws.append(["Balance contable (legalizado) frente al impositivo. "
                   "El impositivo se carga en Contabilidad → Configuración → "
                   "Apertura del balance impositivo. No modifica asientos."])
        ws.append([])
        ws.append(["Concepto", "Contable", "Impositivo", "Diferencia (C − I)"])
        for cell in ws[ws.max_row]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        tot_c = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0}
        tot_i = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0}
        for seccion, titulo in SECCIONES_ESP:
            d = impositivo.get(seccion)
            c_sec = contable.get(seccion, 0.0)
            if not d and abs(c_sec) < 0.005:
                continue
            ws.append([titulo])
            ws.cell(ws.max_row, 1).font = sec_f
            for concepto, importe, es_sub in (d["detalle"] if d else []):
                etiqueta = f"{concepto} (subtotal foto)" if es_sub else concepto
                fila(etiqueta, None, importe, "det")
            i_sec = d["total"] if d else 0.0
            fila(f"Total {titulo.lower()}", c_sec, i_sec, "subtot")
            destino = ("activo" if seccion in ACTIVO
                       else "pasivo" if seccion in PASIVO else "pn")
            tot_c[destino] += c_sec
            tot_i[destino] += i_sec

        ws.append([])
        fila("TOTAL ACTIVO", tot_c["activo"], tot_i["activo"], "total")
        fila("TOTAL PASIVO", tot_c["pasivo"], tot_i["pasivo"], "total")
        fila("TOTAL PATRIMONIO NETO", tot_c["pn"], tot_i["pn"], "total")
        fila("TOTAL PASIVO + PATRIMONIO NETO",
             tot_c["pasivo"] + tot_c["pn"], tot_i["pasivo"] + tot_i["pn"], "total")

        ws.append([])
        ws.append(["Conciliación de la diferencia"])
        ws.cell(ws.max_row, 1).font = bold
        dif_act = round(tot_c["activo"] - tot_i["activo"], 2)
        dif_pas = round(tot_c["pasivo"] - tot_i["pasivo"], 2)
        dif_pn = round(tot_c["pn"] - tot_i["pn"], 2)
        fila("Diferencia de activo", dif_act, None, "subtot")
        fila("    = diferencia de pasivo", dif_pas, None, "det")
        fila("    + diferencia de patrimonio neto", dif_pn, None, "det")
        descuadre = round(dif_act - (dif_pas + dif_pn), 2)
        ws.append([f"Control: activo − (pasivo + patrimonio neto) = {self._fmt(descuadre)}"])
        ws.cell(ws.max_row, 1).font = det_f

        ws.column_dimensions["A"].width = 56
        for letra in "BCD":
            ws.column_dimensions[letra].width = 20
        ws.freeze_panes = "A5"
        return wb
