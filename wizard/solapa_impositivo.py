"""Solapas del balance impositivo.

El balance impositivo es otra fuente del mismo cierre (lo arma el contador) y no
coincide con el contable: se carga en yaguven.apertura.impositivo y no sale de
los asientos. Este archivo agrega dos solapas opcionales al export del SyS:

- «Balance impositivo»: sólo el impositivo, línea por línea, como la foto. Va al
  principio del archivo.
- «Contable vs impositivo»: enfrenta, por sección, el contable (de los asientos)
  con el impositivo, y concilia la diferencia (la del activo tiene que ser igual
  a la del pasivo más la del patrimonio neto). Ninguna cambia asientos: son
  papeles de trabajo.
"""

from odoo import fields, models

from .estados_contables import ACTIVO, PASIVO, SECCIONES_ESP


class SysTangoWizardImpositivo(models.TransientModel):
    _inherit = "yaguven.sys.tango.wizard"

    show_balance_impositivo = fields.Boolean(
        string="Balance impositivo",
        default=False,
        help="Agrega al principio del archivo una solapa con el balance "
        "impositivo cargado en Contabilidad → Configuración → Apertura del "
        "balance impositivo, a la fecha de cierre anterior (la apertura del "
        "ejercicio). Si no hay impositivo cargado para esa fecha, no se agrega.",
    )
    show_impositivo = fields.Boolean(
        string="Contable vs impositivo",
        default=False,
        help="Agrega una solapa que compara, por sección, el balance contable "
        "con el impositivo, y concilia la diferencia.",
    )
    show_impositivo_comparativo = fields.Boolean(
        string="Balance impositivo comparativo (Odoo)",
        default=False,
        help="Agrega una solapa con el balance al cierre del ejercicio según los "
        "saldos de Odoo (a la fecha «hasta»), comparado con el impositivo del "
        "ejercicio anterior (la apertura). Si no hay impositivo cargado, no se "
        "agrega.",
    )

    # -------------------------------------------------------------- datos

    def _impositivo_por_seccion(self, fecha):
        """{seccion: {'detalle': [(concepto, importe, es_subtotal)], 'total'}}.

        El total de la sección sale de las líneas de detalle (las marcadas como
        subtotal no se suman: reproducen la foto, no miden).
        """
        self.ensure_one()
        lineas = self.env["yaguven.apertura.impositivo"].search(
            [("company_id", "=", self.company_id.id), ("fecha", "=", fecha)],
            order="sequence, id",
        )
        datos = {}
        for ln in lineas:
            d = datos.setdefault(ln.section, {"detalle": [], "total": 0.0})
            d["detalle"].append((ln.codigo, ln.concepto, ln.importe, ln.es_subtotal))
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
        sin = (datos.get("esp_sin_rubro") or {}).get("comparativo") or {}
        neto = sum(sin.values())
        if neto >= 0:
            out["activo_corriente"] += neto
        else:
            out["pasivo_corriente"] += -neto
        return out

    def _odoo_por_seccion(self, datos, columna):
        """{seccion: saldo Odoo} para la columna «actual» o «comparativo», con el
        patrimonio neto SIN el resultado y el resultado del ejercicio aparte
        (clave «resultado»), para comparar contra el layout del impositivo."""
        self.ensure_one()
        Rubro = self.env["yaguven.rubro"]
        out = {}
        for seccion, _t in SECCIONES_ESP:
            total = 0.0
            for rubro in Rubro.search([("section", "=", seccion),
                                       ("company_id", "=", self.company_id.id)]):
                d = datos["esp"][columna].get(rubro)
                if not d:
                    continue
                bruto = sum(d["partidas"].values()) + sum(d["regul"].values())
                total += -bruto if (seccion in PASIVO or seccion == "patrimonio_neto") else bruto
            out[seccion] = total
        sin = (datos.get("esp_sin_rubro") or {}).get(columna) or {}
        neto = sum(sin.values())
        if neto >= 0:
            out["activo_corriente"] += neto
        else:
            out["pasivo_corriente"] += -neto
        out["resultado"] = datos["resultado_acumulado"][columna]
        return out

    # -------------------------------------------------------------- estilos

    def _estilos_impositivo(self):
        from openpyxl.styles import Border, Font, Side
        return {
            "big": Font(bold=True, size=12),
            "bold": Font(bold=True),
            "sec": Font(bold=True, size=11),
            "det": Font(italic=True, color="555555"),
            "top": Border(top=Side(style="thin")),
        }

    # -------------------------------------------------- hoja: balance impositivo

    def _hoja_balance_impositivo(self, wb, fecha, impositivo):
        from openpyxl.styles import Alignment
        st = self._estilos_impositivo()
        num = "#,##0.00"
        ws = wb.create_sheet("Balance impositivo", 0)  # al principio
        ws.append([f"{self.company_id.name} — Balance impositivo al {fecha.strftime('%d/%m/%Y')}"])
        ws.cell(ws.max_row, 1).font = st["big"]
        ws.append(["Cargado en Contabilidad → Configuración → Apertura del balance "
                   "impositivo. No sale de los asientos."])
        ws.append([])
        ws.append(["Código", "Concepto", "Importe"])
        for cell in ws[ws.max_row]:
            cell.font = st["bold"]
            cell.alignment = Alignment(horizontal="center")

        def renglon(codigo, concepto, importe, kind):
            sangria = "    " if kind == "det" else ""
            ws.append([codigo or "", f"{sangria}{concepto}", importe])
            r = ws.max_row
            if importe is not None:
                ws.cell(r, 3).number_format = num
            font = {"sec": st["sec"], "subtot": st["bold"], "total": st["bold"],
                    "det": st["det"]}.get(kind)
            if font:
                for cell in ws[r]:
                    cell.font = font
            if kind == "total":
                for cell in ws[r]:
                    cell.border = st["top"]

        secciones = list(SECCIONES_ESP) + [
            ("resultado", "RESULTADO DEL EJERCICIO (ganancias y pérdidas)")]
        tot = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0, "resultado": 0.0}
        for seccion, titulo in secciones:
            d = impositivo.get(seccion)
            if not d:
                continue
            renglon(None, titulo, None, "sec")
            for codigo, concepto, importe, es_sub in d["detalle"]:
                etiqueta = f"{concepto} (subtotal foto)" if es_sub else concepto
                renglon(codigo, etiqueta, importe, "det")
            renglon(None, f"Total {titulo.lower()}", d["total"], "subtot")
            destino = ("activo" if seccion in ACTIVO
                       else "pasivo" if seccion in PASIVO
                       else "resultado" if seccion == "resultado" else "pn")
            tot[destino] += d["total"]
        ws.append([])
        renglon(None, "TOTAL ACTIVO", tot["activo"], "total")
        renglon(None, "TOTAL PASIVO", tot["pasivo"], "total")
        renglon(None, "TOTAL PATRIMONIO NETO", tot["pn"], "total")
        if abs(tot["resultado"]) >= 0.005:
            renglon(None, "TOTAL RESULTADO DEL EJERCICIO", tot["resultado"], "total")
        renglon(None, "TOTAL PASIVO + PN + RESULTADO",
                tot["pasivo"] + tot["pn"] + tot["resultado"], "total")
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 52
        ws.column_dimensions["C"].width = 22
        ws.freeze_panes = "A5"

    # ---------------------------------------------- hoja: contable vs impositivo

    def _hoja_contable_vs_impositivo(self, wb, fecha, impositivo):
        from openpyxl.styles import Alignment
        st = self._estilos_impositivo()
        num = "#,##0.00"
        datos = self._datos_estados()
        contable = self._contable_por_seccion(datos)
        ws = wb.create_sheet("Contable vs impositivo")

        def fila(concepto, c, i, kind="det"):
            dif = round((c or 0.0) - (i or 0.0), 2) if (c is not None and i is not None) else None
            sangria = "        " if kind == "det" else ""
            ws.append([f"{sangria}{concepto}", c, i, dif])
            r = ws.max_row
            for col in (2, 3, 4):
                ws.cell(r, col).number_format = num
            font = {"sec": st["sec"], "subtot": st["bold"], "total": st["bold"],
                    "det": st["det"]}.get(kind)
            if font:
                for cell in ws[r]:
                    cell.font = font
            if kind == "total":
                for cell in ws[r]:
                    cell.border = st["top"]

        ws.append([f"{self.company_id.name} — Apertura al {fecha.strftime('%d/%m/%Y')}"])
        ws.cell(ws.max_row, 1).font = st["big"]
        ws.append(["Balance contable (legalizado) frente al impositivo. No modifica asientos."])
        ws.append([])
        ws.append(["Concepto", "Contable", "Impositivo", "Diferencia (C − I)"])
        for cell in ws[ws.max_row]:
            cell.font = st["bold"]
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        tot_c = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0}
        tot_i = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0}
        for seccion, titulo in SECCIONES_ESP:
            d = impositivo.get(seccion)
            c_sec = contable.get(seccion, 0.0)
            # el resultado impositivo va sin cerrar; el contable ya está dentro
            # del PN, así que lo pliego en el patrimonio neto para comparar.
            extra = impositivo.get("resultado") if seccion == "patrimonio_neto" else None
            if not d and not extra and abs(c_sec) < 0.005:
                continue
            ws.append([titulo])
            ws.cell(ws.max_row, 1).font = st["sec"]
            for codigo, concepto, importe, es_sub in (d["detalle"] if d else []):
                etiqueta = f"{concepto} (subtotal foto)" if es_sub else concepto
                if codigo:
                    etiqueta = f"{codigo}  {etiqueta}"
                fila(etiqueta, None, importe, "det")
            if extra:
                for codigo, concepto, importe, es_sub in extra["detalle"]:
                    etiqueta = f"{codigo}  {concepto}" if codigo else concepto
                    fila(etiqueta, None, importe, "det")
            i_sec = (d["total"] if d else 0.0) + (extra["total"] if extra else 0.0)
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
        ws.cell(ws.max_row, 1).font = st["bold"]
        dif_act = round(tot_c["activo"] - tot_i["activo"], 2)
        dif_pas = round(tot_c["pasivo"] - tot_i["pasivo"], 2)
        dif_pn = round(tot_c["pn"] - tot_i["pn"], 2)
        fila("Diferencia de activo", dif_act, None, "subtot")
        fila("    = diferencia de pasivo", dif_pas, None, "det")
        fila("    + diferencia de patrimonio neto", dif_pn, None, "det")
        descuadre = round(dif_act - (dif_pas + dif_pn), 2)
        ws.append([f"Control: activo − (pasivo + patrimonio neto) = {self._fmt(descuadre)}"])
        ws.cell(ws.max_row, 1).font = st["det"]
        ws.column_dimensions["A"].width = 56
        for letra in "BCD":
            ws.column_dimensions[letra].width = 20
        ws.freeze_panes = "A5"

    # ------------------------------ hoja: balance impositivo comparativo (Odoo)

    def _hoja_balance_impositivo_comparativo(self, wb, impositivo):
        from openpyxl.styles import Alignment
        st = self._estilos_impositivo()
        num = "#,##0.00"
        datos = self._datos_estados()
        odoo = self._odoo_por_seccion(datos, "actual")
        actual = self.date_to.strftime("%d/%m/%Y")
        anterior = fields.Date.subtract(self.date_from, days=1).strftime("%d/%m/%Y")
        ws = wb.create_sheet("Balance impositivo comparativo", 0)
        ws.append([f"{self.company_id.name} — Balance impositivo comparativo"])
        ws.cell(ws.max_row, 1).font = st["big"]
        ws.append([f"Saldos de Odoo al {actual} frente al balance impositivo del "
                   f"ejercicio anterior al {anterior} (cargado). Odoo por rubro."])
        ws.append([])
        ws.append(["Código", "Concepto", f"Odoo al {actual}", f"Impositivo al {anterior}"])
        for cell in ws[ws.max_row]:
            cell.font = st["bold"]
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        def renglon(codigo, concepto, od, im, kind):
            sangria = "    " if kind == "det" else ""
            ws.append([codigo or "", f"{sangria}{concepto}", od, im])
            r = ws.max_row
            for col in (3, 4):
                ws.cell(r, col).number_format = num
            font = {"sec": st["sec"], "subtot": st["bold"], "total": st["bold"],
                    "det": st["det"]}.get(kind)
            if font:
                for cell in ws[r]:
                    cell.font = font
            if kind == "total":
                for cell in ws[r]:
                    cell.border = st["top"]

        secciones = list(SECCIONES_ESP) + [
            ("resultado", "RESULTADO DEL EJERCICIO (ganancias y pérdidas)")]
        tot_o = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0, "resultado": 0.0}
        tot_i = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0, "resultado": 0.0}
        for seccion, titulo in secciones:
            d = impositivo.get(seccion)
            od_sec = odoo.get(seccion, 0.0)
            if not d and abs(od_sec) < 0.005:
                continue
            renglon(None, titulo, None, None, "sec")
            for codigo, concepto, importe, es_sub in (d["detalle"] if d else []):
                etiqueta = f"{concepto} (subtotal foto)" if es_sub else concepto
                renglon(codigo, etiqueta, None, importe, "det")
            im_sec = d["total"] if d else 0.0
            renglon(None, f"Total {titulo.lower()}", od_sec, im_sec, "subtot")
            destino = ("activo" if seccion in ACTIVO
                       else "pasivo" if seccion in PASIVO
                       else "resultado" if seccion == "resultado" else "pn")
            tot_o[destino] += od_sec
            tot_i[destino] += im_sec
        ws.append([])
        renglon(None, "TOTAL ACTIVO", tot_o["activo"], tot_i["activo"], "total")
        renglon(None, "TOTAL PASIVO", tot_o["pasivo"], tot_i["pasivo"], "total")
        renglon(None, "TOTAL PATRIMONIO NETO", tot_o["pn"], tot_i["pn"], "total")
        renglon(None, "TOTAL RESULTADO DEL EJERCICIO", tot_o["resultado"], tot_i["resultado"], "total")
        renglon(None, "TOTAL PASIVO + PN + RESULTADO",
                tot_o["pasivo"] + tot_o["pn"] + tot_o["resultado"],
                tot_i["pasivo"] + tot_i["pn"] + tot_i["resultado"], "total")
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 48
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 20
        ws.freeze_panes = "A5"

    # -------------------------------------------------------------- orquesta

    def _build_workbook(self):
        wb = super()._build_workbook()
        if not (self.show_impositivo or self.show_balance_impositivo
                or self.show_impositivo_comparativo):
            return wb
        fecha = fields.Date.subtract(self.date_from, days=1)
        impositivo, hay = self._impositivo_por_seccion(fecha)
        if not hay:
            return wb
        # primero la comparación (se agrega al final); después los balances
        # (se insertan al principio), para que queden primeros.
        if self.show_impositivo:
            self._hoja_contable_vs_impositivo(wb, fecha, impositivo)
        if self.show_balance_impositivo:
            self._hoja_balance_impositivo(wb, fecha, impositivo)
        if self.show_impositivo_comparativo:
            self._hoja_balance_impositivo_comparativo(wb, impositivo)
        return wb
