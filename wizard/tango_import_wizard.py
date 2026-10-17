import base64
import io
import unicodedata

from odoo import fields, models
from odoo.exceptions import UserError


def _norm(value):
    """Texto de encabezado sin acentos, en minúsculas y sin espacios de más."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def _code(value):
    """Código de cuenta como texto: 10003.0 -> '10003'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class TangoImportWizard(models.TransientModel):
    _name = "yaguven.tango.import.wizard"
    _description = "Importar plan Tango / equivalencias desde xlsx"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    import_type = fields.Selection(
        [
            ("plan", "Plan de cuentas Tango (xlsx de sumas y saldos)"),
            ("mapping", "Equivalencias cuenta Odoo -> cuenta Tango"),
        ],
        string="Qué importar",
        required=True,
        default="plan",
    )
    file = fields.Binary(string="Archivo xlsx")
    filename = fields.Char()
    result = fields.Text(string="Resultado", readonly=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("done", "Hecho")], default="draft"
    )

    # ------------------------------------------------------------------ lectura

    def _read_rows(self, raw):
        """Filas del primer hoja. Sin read_only: los exports de Tango declaran mal
        el rango y en ese modo devuelven sólo el encabezado."""
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
        except Exception as exc:
            raise UserError(f"No se pudo leer el xlsx: {exc}") from exc
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]

    def _find_header(self, rows, required):
        """Índice de la fila de encabezado y mapa nombre normalizado -> columna."""
        for idx, row in enumerate(rows[:30]):
            names = {_norm(c): col for col, c in enumerate(row) if c not in (None, "")}
            if all(any(n.startswith(req) for n in names) for req in required):
                return idx, names
        raise UserError(
            "No encontramos el encabezado en el archivo. Columnas esperadas: "
            + ", ".join(required)
        )

    @staticmethod
    def _col(names, *prefixes):
        for prefix in prefixes:
            for name, col in names.items():
                if name.startswith(prefix):
                    return col
        return None

    # ------------------------------------------------------------------ plan

    def _nature_from_row(self, row, cols, code):
        """Tipo de la cuenta: primero por la columna del SyS donde cae el saldo;
        si el saldo es cero, por el primer dígito del código (1-3 patrimonial)."""
        act, pas, res_neg, res_pos = (
            _num(row[c]) if c is not None else 0.0 for c in cols
        )
        if act or pas:
            return "patrimonial"
        if res_neg or res_pos:
            return "resultado"
        return "patrimonial" if code[:1] in ("1", "2", "3") else "resultado"

    def _import_plan(self, rows):
        hdr, names = self._find_header(rows, ["codigo", "descripcion"])
        c_code = self._col(names, "codigo")
        c_name = self._col(names, "descripcion")
        nat_cols = (
            self._col(names, "activo"),
            self._col(names, "pasivo"),
            self._col(names, "resultado negativo"),
            self._col(names, "resultado positivo"),
        )
        Tango = self.env["yaguven.tango.account"].with_context(active_test=False)
        existing = {
            a.code: a
            for a in Tango.search([("company_id", "=", self.company_id.id)])
        }
        created = updated = 0
        skipped = []
        seen = set()
        for pos, row in enumerate(rows[hdr + 1:], start=1):
            code = _code(row[c_code])
            name = str(row[c_name] or "").strip()
            if not code:
                if name:
                    skipped.append(name)
                continue
            if code in seen:
                skipped.append(f"{code} {name} (repetido en el archivo)")
                continue
            seen.add(code)
            vals = {"name": name or code, "sequence": pos * 10}
            if code in existing:
                existing[code].write(vals)
                updated += 1
            else:
                vals.update(
                    company_id=self.company_id.id,
                    code=code,
                    nature=self._nature_from_row(row, nat_cols, code),
                )
                Tango.create(vals)
                created += 1
        lines = [
            f"Compañía: {self.company_id.name}",
            f"Cuentas Tango creadas: {created}",
            f"Cuentas Tango actualizadas (descripción y orden): {updated}",
        ]
        if skipped:
            lines.append(f"Renglones sin código, no importados: {len(skipped)}")
            lines += [f"  - {s}" for s in skipped]
        return "\n".join(lines)

    # ------------------------------------------------------------------ equivalencias

    def _import_mapping(self, rows):
        hdr, names = self._find_header(rows, ["codigo odoo", "codigo tango"])
        c_odoo = self._col(names, "codigo odoo")
        c_tango = self._col(names, "codigo tango")
        c_note = self._col(names, "criterio")
        company = self.company_id
        Account = self.env["account.account"].with_company(company)
        accounts = {
            a.code: a
            for a in Account.search([("company_ids", "in", company.id)])
        }
        tango = {
            a.code: a
            for a in self.env["yaguven.tango.account"].search(
                [("company_id", "=", company.id)]
            )
        }
        Mapping = self.env["yaguven.tango.mapping"]
        current = {
            m.account_id.id: m
            for m in Mapping.search([("company_id", "=", company.id)])
        }
        created = updated = 0
        missing = []
        for row in rows[hdr + 1:]:
            code_odoo = _code(row[c_odoo])
            code_tango = _code(row[c_tango])
            if not code_odoo and not code_tango:
                continue
            account = accounts.get(code_odoo)
            tango_acc = tango.get(code_tango)
            if not account or not tango_acc:
                missing.append(
                    f"{code_odoo or '(vacío)'} -> {code_tango or '(vacío)'}: "
                    + ("cuenta Odoo inexistente" if not account else "cuenta Tango inexistente")
                )
                continue
            vals = {"tango_account_id": tango_acc.id}
            if c_note is not None and row[c_note]:
                vals["note"] = str(row[c_note]).strip()
            if account.id in current:
                current[account.id].write(vals)
                updated += 1
            else:
                vals.update(company_id=company.id, account_id=account.id)
                current[account.id] = Mapping.create(vals)
                created += 1
        lines = [
            f"Compañía: {company.name}",
            f"Equivalencias creadas: {created}",
            f"Equivalencias actualizadas: {updated}",
        ]
        if missing:
            lines.append(f"Renglones no importados: {len(missing)}")
            lines += [f"  - {m}" for m in missing]
        return "\n".join(lines)

    # ------------------------------------------------------------------ acciones

    def _run(self, raw):
        rows = self._read_rows(raw)
        if self.import_type == "plan":
            result = self._import_plan(rows)
        else:
            result = self._import_mapping(rows)
        self.write({"result": result, "state": "done"})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError("Adjuntá el archivo xlsx.")
        return self._run(base64.b64decode(self.file))

    def action_import_from_attachment(self, attachment_id):
        """Para scripts: el archivo se sube antes como ir.attachment (C.3)."""
        self.ensure_one()
        attachment = self.env["ir.attachment"].browse(attachment_id)
        if not attachment.exists():
            raise UserError("No existe el adjunto indicado.")
        self._run(attachment.raw)
        return self.result
