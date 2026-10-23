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
    show_balance_odoo = fields.Boolean(
        string="Balance Odoo (formato impositivo)",
        default=False,
        help="Agrega una solapa con el balance de Odoo al cierre (a la fecha "
        "«hasta»), en el mismo formato que el balance impositivo: por sección, "
        "patrimonio neto sin el resultado y resultado del ejercicio aparte. Sale "
        "de los asientos; no necesita impositivo cargado.",
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
        self._hoja_balance_formato(
            wb, "Balance impositivo",
            f"{self.company_id.name} — Balance impositivo al {fecha.strftime('%d/%m/%Y')}",
            "Cargado en Contabilidad → Configuración → Apertura del balance "
            "impositivo. No sale de los asientos.",
            impositivo)

    # qué sección le toca a una cuenta sin rubro, según su naturaleza
    _SECCION_POR_NATURALEZA = {
        "asset": "activo_corriente", "liability": "pasivo_corriente",
        "equity": "patrimonio_neto", "income": "resultado", "expense": "resultado",
    }

    def _odoo_detallado_por_seccion(self, datos, columna):
        """El balance de Odoo en el formato del impositivo, abierto para poder
        analizarlo, con los CÓDIGOS Y NOMBRES DE CUENTA DE TANGO (vía
        yaguven.tango.mapping), no los de Odoo, y agrupado por SECCIÓN → RUBRO
        RT 59 → código Tango. Cada saldo Odoo se agrega bajo su cuenta Tango
        (respetando el reparto por diario), en el rubro del ESP (o «sin rubro» si
        no tiene). El activo suma su saldo deudor; el pasivo, el patrimonio neto y
        el resultado, su saldo acreedor. El patrimonio neto queda sin el resultado
        del ejercicio, que arma su propia sección.

        Devuelve {seccion: {"rubros": [{"code","name","detalle","total"}], "total"}}
        con los rubros ordenados por su código."""
        self.ensure_one()
        hasta = self.date_to if columna == "actual" else fields.Date.subtract(self.date_from, days=1)
        exclusion = self._excluded_moves()
        por_cuenta, por_grupo = self._mapeos_por_clave()

        # La sección y el RUBRO se deciden con el saldo TOTAL de la cuenta
        # (estable): si se usara el saldo por diario, una cuenta con condición por
        # signo se partiría entre activo y pasivo e inflaría los totales.
        seccion_de, rubro_de = {}, {}
        for account, saldo in self._saldos_por_cuenta(hasta, exclusion["move_ids"]).items():
            if abs(saldo) < 0.005:
                continue
            rubro, _r, _m = self._rubro_de(account, saldo, por_cuenta, por_grupo)
            if rubro:
                seccion_de[account.id] = rubro.section
                rubro_de[account.id] = (rubro.sequence, rubro.code or "", rubro.name)
            else:
                seccion_de[account.id] = self._SECCION_POR_NATURALEZA.get(
                    account.internal_group, "activo_corriente")
                rubro_de[account.id] = (9999, "", "(sin rubro asignado)")

        # mapeo Odoo -> Tango (con reparto por diario cuando existe)
        tango_of, split = {}, set()
        for m in self.env["yaguven.tango.mapping"].search(
                [("company_id", "=", self.company_id.id)]):
            tango_of[(m.account_id.id, m.journal_id.id or 0)] = m.tango_account_id
            if m.journal_id:
                split.add(m.account_id.id)

        dominio = [("company_id", "=", self.company_id.id), ("parent_state", "=", "posted"),
                   ("date", "<=", hasta)]
        if exclusion["move_ids"]:
            dominio.append(("move_id", "not in", list(exclusion["move_ids"])))
        AML = self.env["account.move.line"].with_company(self.company_id)

        # agregado por (sección, rubro, código Tango)
        agregado = {}
        for account, journal, debit, credit in AML._read_group(
                dominio, ["account_id", "journal_id"], ["debit:sum", "credit:sum"]):
            if not account:
                continue
            saldo = (debit or 0.0) - (credit or 0.0)
            if abs(saldo) < 0.005:
                continue
            seccion = seccion_de.get(account.id) or self._SECCION_POR_NATURALEZA.get(
                account.internal_group, "activo_corriente")
            rubro = rubro_de.get(account.id) or (9999, "", "(sin rubro asignado)")
            jid = journal.id if (account.id in split and journal) else 0
            tango = tango_of.get((account.id, jid)) or tango_of.get((account.id, 0))
            if tango:
                codigo, nombre, clave = tango.code, tango.name, ("t", tango.id)
            else:
                codigo, nombre, clave = (account.code or ""), account.name, ("o", account.id)
            valor = saldo if seccion in ACTIVO else -saldo
            d = agregado.setdefault((seccion, rubro, clave),
                                    {"codigo": codigo, "nombre": nombre, "valor": 0.0})
            d["valor"] += valor

        # salida: cada sección con sus rubros (ordenados por código), y cada rubro
        # con su detalle de códigos Tango y su subtotal.
        porsec = {}
        for (seccion, rubro, _clave), d in agregado.items():
            if abs(d["valor"]) < 0.005:
                continue
            porsec.setdefault(seccion, {}).setdefault(rubro, []).append(
                (d["codigo"], d["nombre"], round(d["valor"], 2)))
        out = {}
        for seccion, rubros in porsec.items():
            lista, total = [], 0.0
            for rubro in sorted(rubros):
                detalle = sorted(rubros[rubro], key=lambda x: x[0])
                rtot = round(sum(x[2] for x in detalle), 2)
                lista.append({"code": rubro[1], "name": rubro[2],
                              "detalle": detalle, "total": rtot})
                total += rtot
            out[seccion] = {"rubros": lista, "total": round(total, 2)}
        return out

    def _hoja_balance_odoo(self, wb):
        """Balance de Odoo al cierre en layout impositivo, abierto por
        SECCIÓN → RUBRO RT 59 (con subtotal) → códigos de cuenta de Tango."""
        from openpyxl.styles import Alignment
        st = self._estilos_impositivo()
        num = "#,##0.00"
        data = self._odoo_detallado_por_seccion(self._datos_estados(), "actual")
        actual = self.date_to.strftime("%d/%m/%Y")
        ws = wb.create_sheet("Balance Odoo (impositivo)", 0)
        ws.append([f"{self.company_id.name} — Balance al {actual} (formato impositivo, datos de Odoo)"])
        ws.cell(ws.max_row, 1).font = st["big"]
        ws.append(["Saldos de Odoo al cierre, abiertos por rubro de la RT 59. "
                   "Patrimonio neto sin el resultado; resultado del ejercicio aparte."])
        ws.append([])
        ws.append(["Código", "Concepto", "Importe"])
        for cell in ws[ws.max_row]:
            cell.font = st["bold"]
            cell.alignment = Alignment(horizontal="center")

        def fila(codigo, concepto, importe, kind):
            sang = {"rubro": "  ", "det": "      ", "rsub": "    "}.get(kind, "")
            ws.append([codigo or "", f"{sang}{concepto}", importe])
            r = ws.max_row
            if importe is not None:
                ws.cell(r, 3).number_format = num
            font = {"sec": st["sec"], "rubro": st["bold"], "det": st["det"],
                    "rsub": st["det"]}.get(kind)
            if font:
                for cell in ws[r]:
                    cell.font = font
            if kind in ("total", "sectot"):
                for cell in ws[r]:
                    cell.border = st["top"]
                    cell.font = st["bold"]

        secciones = list(SECCIONES_ESP) + [
            ("resultado", "RESULTADO DEL EJERCICIO (ganancias y pérdidas)")]
        tot = {"activo": 0.0, "pasivo": 0.0, "pn": 0.0, "resultado": 0.0}
        for seccion, titulo in secciones:
            d = data.get(seccion)
            if not d:
                continue
            fila(None, titulo, None, "sec")
            for rubro in d["rubros"]:
                etiqueta = f"{rubro['code']} {rubro['name']}".strip()
                fila(rubro["code"] or None, etiqueta, None, "rubro")
                for cod, nom, imp in rubro["detalle"]:
                    fila(cod, nom, imp, "det")
                fila(None, f"Subtotal {etiqueta}", rubro["total"], "rsub")
            fila(None, f"Total {titulo.lower()}", d["total"], "sectot")
            destino = ("activo" if seccion in ACTIVO
                       else "pasivo" if seccion in PASIVO
                       else "resultado" if seccion == "resultado" else "pn")
            tot[destino] += d["total"]
        ws.append([])
        fila(None, "TOTAL ACTIVO", tot["activo"], "total")
        fila(None, "TOTAL PASIVO", tot["pasivo"], "total")
        fila(None, "TOTAL PATRIMONIO NETO", tot["pn"], "total")
        if abs(tot["resultado"]) >= 0.005:
            fila(None, "TOTAL RESULTADO DEL EJERCICIO", tot["resultado"], "total")
        fila(None, "TOTAL PASIVO + PN + RESULTADO",
             tot["pasivo"] + tot["pn"] + tot["resultado"], "total")
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 56
        ws.column_dimensions["C"].width = 22
        ws.freeze_panes = "A5"
        self._footer_exclusion(ws)

    def _hoja_balance_formato(self, wb, sheet_name, titulo, subtitulo, datos_sec):
        from openpyxl.styles import Alignment
        st = self._estilos_impositivo()
        num = "#,##0.00"
        ws = wb.create_sheet(sheet_name, 0)  # al principio
        ws.append([titulo])
        ws.cell(ws.max_row, 1).font = st["big"]
        ws.append([subtitulo])
        ws.append([])
        ws.append(["Código", "Concepto", "Importe"])
        for cell in ws[ws.max_row]:
            cell.font = st["bold"]
            cell.alignment = Alignment(horizontal="center")

        impositivo = datos_sec

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
        return ws

    def _footer_exclusion(self, ws):
        """Pie que deja constancia de las cuentas excluidas del SyS Tango (y los
        asientos que, con sus contrapartidas, quedaron afuera), igual que la
        solapa «Balance de saldos». Sólo para los balances que salen de Odoo."""
        st = self._estilos_impositivo()
        exclusion = self._excluded_moves()
        if not exclusion["accounts"]:
            return
        codes = ", ".join(f"{a.code} {a.name}" for a in exclusion["accounts"])
        ws.append([])
        ws.append([f"Cuentas excluidas del SyS Tango: {len(exclusion['accounts'])} ({codes})"])
        ws.cell(ws.max_row, 1).font = st["det"]
        ws.append([f"Asientos que las tocan y quedaron afuera: {exclusion['moves']} asientos · "
                   f"{exclusion['count']} líneas del período · débitos {self._fmt(exclusion['debit'])}"])
        ws.cell(ws.max_row, 1).font = st["det"]

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
            # estado de resultados de Odoo (columna actual), por rubro
            if seccion == "resultado":
                Rubro = self.env["yaguven.rubro"]
                for rubro in Rubro.search([("section", "=", "resultado"),
                                           ("company_id", "=", self.company_id.id)]):
                    dd = datos["er"].get(rubro)
                    valor = -(sum(dd["partidas"].values()) + sum(dd["regul"].values())) if dd else 0.0
                    if abs(valor) >= 0.005:
                        renglon(rubro.code, f"{rubro.name} (Odoo)", valor, None, "det")
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
        self._footer_exclusion(ws)

    # -------------------------------------------------------------- orquesta

    def _build_workbook(self):
        wb = super()._build_workbook()
        if self.show_balance_odoo:
            self._hoja_balance_odoo(wb)
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
