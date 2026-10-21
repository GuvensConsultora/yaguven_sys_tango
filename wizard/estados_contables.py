"""Estado de situación patrimonial y estado de resultados sobre el mismo wizard.

Los rubros son los de la RT 59 (texto ordenado de la RT 54, Norma Unificada
Argentina de Contabilidad), en el orden del modelo del Informe CENCyA N° 27, y
la asociación con el plan de cuentas vive en yaguven.rubro.mapping.

Tres cosas que el mapeo plano no resuelve y acá sí:

- El rubro de una cuenta puede depender del SIGNO de su saldo, y por eso se
  decide a la fecha de cada columna: una cuenta bancaria a favor es «Caja y
  bancos» y la misma en descubierto es «Préstamos y otros pasivos financieros».
- Una cuenta puede REGULARIZAR el rubro en vez de integrarlo (amortizaciones
  acumuladas, mercaderías pendientes de facturar): suma al rubro, pero el
  reporte la muestra aparte para que se vea cómo se compone.
- Las cuentas sin equivalencia no se fuerzan a ningún rubro: van a un renglón
  propio «Sin rubro asignado», para que el estado cuadre igual y la falta quede
  a la vista.
"""

from odoo import fields, models

SECCIONES_ESP = [
    ("activo_corriente", "ACTIVO CORRIENTE"),
    ("activo_no_corriente", "ACTIVO NO CORRIENTE"),
    ("pasivo_corriente", "PASIVO CORRIENTE"),
    ("pasivo_no_corriente", "PASIVO NO CORRIENTE"),
    ("patrimonio_neto", "PATRIMONIO NETO"),
]
ACTIVO = ("activo_corriente", "activo_no_corriente")
PASIVO = ("pasivo_corriente", "pasivo_no_corriente")
RESULTADO_GROUPS = ("income", "expense")

# Subtotales del modelo CENCyA 27: después de qué rubro va cada uno.
SUBTOTALES_ER = {
    "ER.02": "Ganancia (pérdida) bruta",
    "ER.10": "Ganancia (pérdida) antes del impuesto a las ganancias de operaciones que continúan",
    "ER.11": "Ganancia (pérdida) de las operaciones que continúan",
}


class SysTangoWizardEstados(models.TransientModel):
    _inherit = "yaguven.sys.tango.wizard"

    show_statements = fields.Boolean(
        string="Estados contables",
        default=True,
        help="Agrega al archivo la solapa con el estado de situación "
        "patrimonial, el estado de resultados y el cuadro de gastos por "
        "función. Usa los rubros de la RT 59 configurados en Contabilidad → "
        "Configuración → Rubros de los estados contables.",
    )

    # -------------------------------------------------------------- saldos

    def _saldos_por_cuenta(self, hasta, excluded_move_ids=(), desde=None):
        """{account: saldo} a una fecha. Con «desde», sólo el período."""
        self.ensure_one()
        dominio = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", "<=", hasta),
        ]
        if desde:
            dominio.append(("date", ">=", desde))
        if excluded_move_ids:
            dominio.append(("move_id", "not in", list(excluded_move_ids)))
        AML = self.env["account.move.line"].with_company(self.company_id)
        saldos = {}
        for account, debit, credit in AML._read_group(
            dominio, ["account_id"], ["debit:sum", "credit:sum"]
        ):
            if account:
                saldos[account] = debit - credit
        return saldos

    def _mapeos_por_clave(self):
        """Las equivalencias de la compañía, indexadas por cuenta y por grupo."""
        self.ensure_one()
        mapeos = self.env["yaguven.rubro.mapping"].search(
            [("company_id", "=", self.company_id.id)]
        )
        return (
            {m.account_id: m for m in mapeos if m.account_id},
            {m.group_id: m for m in mapeos if m.group_id},
        )

    def _rubro_de(self, account, saldo, por_cuenta, por_grupo):
        """(rubro, regulariza, mapeo) para esa cuenta con ese saldo.

        La regla de la cuenta le gana a la del grupo; si el grupo no tiene
        regla, se prueba con sus padres antes de darla por no asignada.
        """
        mapeo = por_cuenta.get(account)
        if not mapeo:
            grupo = account.group_id
            while grupo and not mapeo:
                mapeo = por_grupo.get(grupo)
                grupo = grupo.parent_id
        if not mapeo:
            return None, False, None
        return mapeo.rubro_por_saldo(saldo), mapeo.is_regularizing, mapeo

    def _agrupar_por_rubro(self, saldos, por_cuenta, por_grupo):
        """{rubro: {'partidas': {grupo: importe}, 'regul': {grupo: importe}}}.

        El grupo es el de la cuenta, que es el nivel inmediato anterior a ella
        (3 o 4 según la rama del plan): es la apertura que se expone.
        """
        datos, sin_rubro = {}, {}
        for account, saldo in saldos.items():
            if not saldo:
                continue
            rubro, regulariza, _m = self._rubro_de(
                account, saldo, por_cuenta, por_grupo
            )
            if not rubro:
                sin_rubro[account] = sin_rubro.get(account, 0.0) + saldo
                continue
            d = datos.setdefault(rubro, {"partidas": {}, "regul": {}})
            destino = d["regul"] if regulariza else d["partidas"]
            clave = account.group_id or account
            destino[clave] = destino.get(clave, 0.0) + saldo
        return datos, sin_rubro

    @staticmethod
    def _etiqueta(clave):
        """Nombre del renglón de apertura: el grupo, o la cuenta si no tiene."""
        if clave._name == "account.group":
            prefijo = clave.code_prefix_start or ""
            return f"{prefijo} {clave.name}".strip()
        return f"{clave.code} {clave.name}"

    # ---------------------------------------------------- estados contables

    def _datos_estados(self, exclusion=None):
        """Todo lo que necesitan las tres tablas, en una sola pasada de datos."""
        self.ensure_one()
        exclusion = exclusion if exclusion is not None else self._excluded_moves()
        excluidos = exclusion["move_ids"]
        por_cuenta, por_grupo = self._mapeos_por_clave()

        cierre_anterior = fields.Date.subtract(self.date_from, days=1)
        actual = self._saldos_por_cuenta(self.date_to, excluidos)
        comparativo = self._saldos_por_cuenta(cierre_anterior, excluidos)

        patrimoniales = {}
        resultados = {}
        for saldos, destino in ((actual, "actual"), (comparativo, "comparativo")):
            pat = {a: s for a, s in saldos.items()
                   if a.internal_group not in RESULTADO_GROUPS}
            res = {a: s for a, s in saldos.items()
                   if a.internal_group in RESULTADO_GROUPS}
            patrimoniales[destino] = self._agrupar_por_rubro(pat, por_cuenta, por_grupo)
            # el resultado acumulado hasta cada fecha, para cerrar el patrimonio
            resultados[destino] = -sum(res.values())

        # el estado de resultados es del PERÍODO, no acumulado
        del_periodo = self._saldos_por_cuenta(
            self.date_to, excluidos, desde=self.date_from
        )
        er = {a: s for a, s in del_periodo.items()
              if a.internal_group in RESULTADO_GROUPS}
        er_datos, er_sin_rubro = self._agrupar_por_rubro(er, por_cuenta, por_grupo)

        return {
            "esp": patrimoniales,
            "resultado_acumulado": resultados,
            "er": er_datos,
            "er_sin_rubro": er_sin_rubro,
            "cierre_anterior": cierre_anterior,
        }

    def _filas_esp(self, datos):
        """Renglones del estado de situación patrimonial, a dos columnas."""
        Rubro = self.env["yaguven.rubro"]
        filas = []
        totales = {"activo": [0.0, 0.0], "pasivo": [0.0, 0.0], "pn": [0.0, 0.0]}

        def importe(seccion, rubro, columna):
            d = datos["esp"][columna].get(rubro)
            if not d:
                return 0.0
            bruto = sum(d["partidas"].values()) + sum(d["regul"].values())
            return -bruto if seccion in PASIVO or seccion == "patrimonio_neto" else bruto

        for seccion, titulo in SECCIONES_ESP:
            rubros = Rubro.search([("section", "=", seccion),
                                   ("company_id", "=", self.company_id.id)])
            visibles = [
                r for r in rubros
                if any(abs(importe(seccion, r, c)) >= 0.005
                       for c in ("actual", "comparativo"))
            ]
            resultado_pn = [0.0, 0.0]
            if seccion == "patrimonio_neto":
                resultado_pn = [datos["resultado_acumulado"]["actual"],
                                datos["resultado_acumulado"]["comparativo"]]
            if not visibles and not any(resultado_pn):
                continue
            filas.append({"kind": "seccion", "label": titulo, "valores": [None, None]})
            subtotal = [0.0, 0.0]
            for rubro in visibles:
                vals = [importe(seccion, rubro, c) for c in ("actual", "comparativo")]
                subtotal = [subtotal[i] + vals[i] for i in (0, 1)]
                filas.append({"kind": "rubro", "label": rubro.name, "valores": vals})
                # apertura por grupo (nivel 3 o 4 del plan, según la rama)
                aperturas = {}
                for columna, idx in (("actual", 0), ("comparativo", 1)):
                    d = datos["esp"][columna].get(rubro) or {"partidas": {}, "regul": {}}
                    for tipo in ("partidas", "regul"):
                        for clave, v in d[tipo].items():
                            fila = aperturas.setdefault(
                                (clave, tipo), {"valores": [0.0, 0.0]}
                            )
                            signo = -1 if (seccion in PASIVO
                                           or seccion == "patrimonio_neto") else 1
                            fila["valores"][idx] += signo * v
                for (clave, tipo), f in sorted(
                    aperturas.items(), key=lambda x: self._etiqueta(x[0][0])
                ):
                    if all(abs(v) < 0.005 for v in f["valores"]):
                        continue
                    etiqueta = self._etiqueta(clave)
                    if tipo == "regul":
                        etiqueta = f"{etiqueta} (regularizadora)"
                    filas.append({"kind": "apertura", "label": etiqueta,
                                  "valores": f["valores"]})
            if seccion == "patrimonio_neto" and any(resultado_pn):
                filas.append({"kind": "rubro",
                              "label": "Resultado del ejercicio y de ejercicios anteriores "
                                       "no asignado a rubros del patrimonio",
                              "valores": resultado_pn})
                subtotal = [subtotal[i] + resultado_pn[i] for i in (0, 1)]
            filas.append({"kind": "subtotal", "label": f"Total del {titulo.lower()}",
                          "valores": subtotal})
            destino = ("activo" if seccion in ACTIVO
                       else "pasivo" if seccion in PASIVO else "pn")
            for i in (0, 1):
                totales[destino][i] += subtotal[i]

        filas.append({"kind": "total", "label": "Total del activo",
                      "valores": totales["activo"]})
        filas.append({"kind": "total", "label": "Total del pasivo",
                      "valores": totales["pasivo"]})
        filas.append({"kind": "total", "label": "Total del pasivo y patrimonio neto",
                      "valores": [totales["pasivo"][i] + totales["pn"][i] for i in (0, 1)]})
        return filas, totales

    def _filas_er(self, datos):
        """Renglones del estado de resultados, con los subtotales del modelo."""
        Rubro = self.env["yaguven.rubro"]
        filas, acumulado, total = [], 0.0, 0.0
        for rubro in Rubro.search([("section", "=", "resultado"),
                                   ("company_id", "=", self.company_id.id)]):
            d = datos["er"].get(rubro)
            valor = -(sum(d["partidas"].values()) + sum(d["regul"].values())) if d else 0.0
            if abs(valor) >= 0.005:
                filas.append({"kind": "rubro", "label": rubro.name, "valores": [valor]})
                for tipo in ("partidas", "regul"):
                    for clave, v in sorted(
                        d[tipo].items(), key=lambda x: self._etiqueta(x[0])
                    ):
                        if abs(v) < 0.005:
                            continue
                        filas.append({"kind": "apertura",
                                      "label": self._etiqueta(clave),
                                      "valores": [-v]})
                acumulado += valor
                total += valor
            if rubro.code in SUBTOTALES_ER and abs(acumulado) >= 0.005:
                filas.append({"kind": "subtotal",
                              "label": SUBTOTALES_ER[rubro.code],
                              "valores": [acumulado]})
        if datos["er_sin_rubro"]:
            suma = -sum(datos["er_sin_rubro"].values())
            filas.append({"kind": "rubro", "label": "Sin rubro asignado",
                          "valores": [suma]})
            for cuenta, v in sorted(datos["er_sin_rubro"].items(),
                                    key=lambda x: x[0].code or ""):
                filas.append({"kind": "apertura",
                              "label": f"{cuenta.code} {cuenta.name}",
                              "valores": [-v]})
            total += suma
        filas.append({"kind": "total", "label": "Ganancia (pérdida) del ejercicio",
                      "valores": [total]})
        return filas, total

    def _filas_gastos(self, datos):
        """Cuadro de gastos por función: comercialización, administración y
        financieros, abierto por grupo."""
        Rubro = self.env["yaguven.rubro"]
        funciones = [
            ("comercializacion", "Comercialización"),
            ("administracion", "Administración"),
            ("financiero", "Financieros"),
        ]
        rubros = {
            f: Rubro.search([("section", "=", "resultado"),
                             ("expense_function", "=", f),
                             ("company_id", "=", self.company_id.id)])
            for f, _t in funciones
        }
        aperturas, totales = {}, {f: 0.0 for f, _t in funciones}
        for idx, (funcion, _titulo) in enumerate(funciones):
            for rubro in rubros[funcion]:
                d = datos["er"].get(rubro)
                if not d:
                    continue
                for tipo in ("partidas", "regul"):
                    for clave, v in d[tipo].items():
                        fila = aperturas.setdefault(clave, [0.0] * len(funciones))
                        fila[idx] += v
                        totales[funcion] += v
        filas = [
            {"label": self._etiqueta(clave), "valores": vals}
            for clave, vals in sorted(aperturas.items(), key=lambda x: self._etiqueta(x[0]))
            if any(abs(v) >= 0.005 for v in vals)
        ]
        return funciones, filas, [totales[f] for f, _t in funciones]

    def _controles_estados(self, datos, totales_esp, resultado_er):
        """Los controles propios de los estados, como texto."""
        currency = self.company_id.currency_id
        activo = totales_esp["activo"][0]
        pasivo_pn = totales_esp["pasivo"][0] + totales_esp["pn"][0]
        resultado_esp = (datos["resultado_acumulado"]["actual"]
                         - datos["resultado_acumulado"]["comparativo"])
        checks = [
            ("Activo = Pasivo + Patrimonio neto (columna actual)", activo - pasivo_pn),
            ("Activo = Pasivo + Patrimonio neto (comparativo)",
             totales_esp["activo"][1] - (totales_esp["pasivo"][1] + totales_esp["pn"][1])),
            ("Resultado del estado de resultados = variación del resultado acumulado "
             "en el patrimonio", resultado_er - resultado_esp),
        ]
        lineas = [
            f"{nombre}: {'OK' if currency.is_zero(d) else f'DIFERENCIA {self._fmt(d)}'}"
            for nombre, d in checks
        ]
        sin_rubro = datos["er_sin_rubro"]
        lineas.append(
            "Cuentas sin rubro asignado en el estado de resultados: "
            + (f"{len(sin_rubro)} (ver renglón «Sin rubro asignado»)"
               if sin_rubro else "ninguna")
        )
        lineas.append(
            "Comparativo: el estado de situación patrimonial sale de los saldos al "
            f"{datos['cierre_anterior'].strftime('%d/%m/%Y')}. El estado de resultados "
            "se presenta por un solo ejercicio mientras el anterior no esté registrado "
            "en el sistema."
        )
        return lineas

    # ------------------------------------------------------------- la solapa

    def _build_workbook(self):
        """Suma la solapa de estados contables al libro, como primera hoja."""
        wb = super()._build_workbook()
        if not self.show_statements:
            return wb
        from openpyxl.styles import Alignment, Font

        exclusion = self._excluded_moves()
        datos = self._datos_estados(exclusion)
        filas_esp, totales_esp = self._filas_esp(datos)
        filas_er, resultado_er = self._filas_er(datos)
        funciones, filas_gastos, totales_gastos = self._filas_gastos(datos)

        ws = wb.create_sheet("Estados contables", 0)
        bold = Font(bold=True)
        seccion_font = Font(bold=True, size=11)
        apertura_font = Font(italic=True, color="555555")
        titulo_font = Font(bold=True, size=12)
        num_fmt = "#,##0.00"
        company = self.company_id
        actual = self.date_to.strftime("%d/%m/%Y")
        anterior = datos["cierre_anterior"].strftime("%d/%m/%Y")

        def titulo(texto, subtitulo=None):
            ws.append([texto])
            ws.cell(ws.max_row, 1).font = titulo_font
            if subtitulo:
                ws.append([subtitulo])
            ws.append([
                f"Cifras expresadas en {company.currency_id.name}. "
                "Rubros según la RT 59 (NUA), modelo del Informe CENCyA N° 27."
            ])
            ws.append([])

        def encabezado(columnas):
            ws.append(columnas)
            for cell in ws[ws.max_row]:
                cell.font = bold
                cell.alignment = Alignment(horizontal="center", wrap_text=True)

        def renglon(label, valores, kind):
            sangria = "        " if kind == "apertura" else ("    " if kind == "rubro" else "")
            ws.append([f"{sangria}{label}"] + list(valores))
            fila = ws.max_row
            for col in range(2, 2 + len(valores)):
                ws.cell(fila, col).number_format = num_fmt
            font = {"seccion": seccion_font, "subtotal": bold,
                    "total": bold, "apertura": apertura_font}.get(kind)
            if font:
                for cell in ws[fila]:
                    cell.font = font

        titulo(f"{company.name} — CUIT {company.vat or ''}")
        titulo(
            "ESTADO DE SITUACIÓN PATRIMONIAL",
            f"Al {actual}, comparativo con el ejercicio anterior al {anterior}",
        )
        encabezado(["Concepto", f"Al {actual}", f"Al {anterior}"])
        for f in filas_esp:
            valores = [v if v is not None else "" for v in f["valores"]]
            renglon(f["label"], valores, f["kind"])

        ws.append([])
        ws.append([])
        titulo(
            "ESTADO DE RESULTADOS",
            f"Por el ejercicio del {self.date_from.strftime('%d/%m/%Y')} al {actual}",
        )
        encabezado(["Concepto", f"Ejercicio al {actual}"])
        for f in filas_er:
            renglon(f["label"], f["valores"], f["kind"])

        ws.append([])
        ws.append([])
        titulo(
            "GASTOS POR FUNCIÓN",
            f"Por el ejercicio del {self.date_from.strftime('%d/%m/%Y')} al {actual}",
        )
        encabezado(["Concepto"] + [t for _f, t in funciones] + ["Total"])
        for f in filas_gastos:
            renglon(f["label"], f["valores"] + [sum(f["valores"])], "apertura")
        renglon("TOTAL", totales_gastos + [sum(totales_gastos)], "total")

        ws.append([])
        ws.append(["Controles"])
        ws.cell(ws.max_row, 1).font = bold
        for linea in self._controles_estados(datos, totales_esp, resultado_er):
            ws.append([linea])

        ws.column_dimensions["A"].width = 72
        for letra in "BCDE":
            ws.column_dimensions[letra].width = 22
        return wb
