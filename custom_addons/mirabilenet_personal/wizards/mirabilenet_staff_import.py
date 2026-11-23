"""Carga del personal desde la plantilla CSV: crea o actualiza usuarios con su rol, región,
sucursal, WhatsApp, zonas que atiende y jefe directo.

Pasa por las mismas barreras que la administración de usuarios: un admin regional solo carga
personal de su región y nadie se da roles globales que no puede otorgar.
"""
import base64

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..personal import limpieza

TEMPLATE_URL = "/mirabilenet_personal/static/plantillas/plantilla_personal.csv"


class MirabilenetStaffImport(models.TransientModel):
    _name = "mirabilenet.staff.import"
    _description = "MIRABILENET: importar personal"

    file = fields.Binary(string="Plantilla CSV", required=True)
    filename = fields.Char(string="Archivo")
    state = fields.Selection([("draft", "Elegir archivo"), ("preview", "Revisar"),
                              ("done", "Listo")], default="draft")
    summary = fields.Html(string="Resumen", readonly=True)
    review_file = fields.Binary(string="Observaciones", readonly=True)
    review_filename = fields.Char(readonly=True)

    @api.model
    def _check_access(self):
        user = self.env.user
        if not (user.has_group("mirabilenet_base.group_mirabilenet_user_admin")
                or user._mirabilenet_is_super()):
            raise AccessError(_("Su rol no administra usuarios."))

    def _rows(self):
        self.ensure_one()
        raw = base64.b64decode(self.file or b"")
        filas, faltan = limpieza.leer_csv(raw)
        if faltan:
            raise UserError(_("Faltan columnas obligatorias: %s. Descargue la plantilla.",
                              ", ".join(faltan)))
        if not filas:
            raise UserError(_("El archivo no tiene filas."))
        return limpieza.limpiar(filas)

    # ------------------------------------------------------------------
    def _resolve(self, row):
        """Región, sucursal y zonas de la fila. Devuelve (valores, problemas)."""
        problems = []
        Region = self.env["mirabilenet.region"].sudo()
        region = Region.browse()
        if row["region"]:
            region = Region.search(["|", ("code", "=ilike", row["region"]),
                                    ("name", "=ilike", row["region"])], limit=1)
            if not region:
                problems.append(_("región «%s» no existe", row["region"]))
        branch = self.env["mirabilenet.branch"].sudo().browse()
        if row["sucursal"]:
            if not region:
                problems.append(_("la sucursal necesita una región"))
            else:
                branch = branch.search([("region_id", "=", region.id), "|",
                                        ("code", "=ilike", row["sucursal"]),
                                        ("name", "=ilike", row["sucursal"])], limit=1)
                if not branch:
                    problems.append(_("sucursal «%s» no es de %s", row["sucursal"], region.name))
        zones = self.env["mirabilenet.zone"].sudo().browse()
        for code in row["zonas"]:
            zone = zones.search([("region_id", "=", region.id) if region else (1, "=", 1),
                                 "|", ("code", "=ilike", code), ("name", "=ilike", code)], limit=1)
            if zone:
                zones |= zone
            else:
                problems.append(_("zona «%s» no existe en la región", code))
        return {"region": region, "branch": branch, "zones": zones}, problems

    def _plan(self):
        """Qué se haría con cada fila, sin tocar nada."""
        rows, errors = self._rows()
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        plan, notes = [], [(f, "", e) for f, e in errors]
        logins = {r["usuario"] for r in rows}
        for row in rows:
            resolved, problems = self._resolve(row)
            if row["jefe"] and row["jefe"] not in logins and not Users.search_count(
                    [("login", "=", row["jefe"])]):
                problems.append(_("jefe «%s» no existe", row["jefe"]))
            if row["whatsapp"]:
                owner = Users.search([("mirabilenet_whatsapp", "=", row["whatsapp"]),
                                      ("login", "!=", row["usuario"])], limit=1)
                if owner:
                    problems.append(_("el WhatsApp ya es de %s", owner.login))
            if problems:
                notes.append((row["fila"], row["usuario"], "; ".join(problems)))
                continue
            existing = Users.search([("login", "=", row["usuario"])], limit=1)
            plan.append(dict(row, **resolved, user=existing))
        return plan, notes

    def _summary(self, plan, notes, done=False):
        new = sum(1 for p in plan if not p["user"])
        upd = len(plan) - new
        verb = _("Se cargaron") if done else _("Se van a cargar")
        html = Markup("<p><b>%s</b> %s</p><ul><li>%s</li><li>%s</li><li>%s</li></ul>") % (
            verb, _("%s persona(s):", len(plan)), _("%s nueva(s)", new),
            _("%s ya existían (se actualizan)", upd),
            _("%s fila(s) con observaciones (no se cargan)", len(notes)))
        if plan:
            html += Markup("<table class='table table-sm'><tr><th>%s</th><th>%s</th><th>%s</th>"
                           "<th>%s</th><th>%s</th></tr>") % (
                _("Usuario"), _("Nombre"), _("Rol"), _("Región"), _("WhatsApp"))
            for p in plan[:40]:
                html += Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                               "</tr>") % (p["usuario"], p["nombre"], p["rol"],
                                           p["region"].name or "-", p["whatsapp"] or "-")
            html += Markup("</table>")
        return html

    def _set_review(self, notes):
        self.review_file = base64.b64encode(limpieza.avisos_csv(notes)) if notes else False
        self.review_filename = "personal_observaciones.csv" if notes else False

    def action_preview(self):
        self._check_access()
        plan, notes = self._plan()
        self.write({"state": "preview", "summary": self._summary(plan, notes)})
        self._set_review(notes)
        return self._reopen()

    def action_import(self):
        self._check_access()
        plan, notes = self._plan()
        Users = self.env["res.users"]
        loaded = {}
        for item in plan:
            try:
                with self.env.cr.savepoint():
                    loaded[item["usuario"]] = self._load_one(Users, item)
            except (AccessError, UserError, ValidationError) as exc:
                notes.append((item["fila"], item["usuario"], str(exc)))
        # Los jefes, al final: el jefe puede venir en una fila posterior del mismo archivo.
        All = Users.sudo().with_context(active_test=False)
        for item in plan:
            user = loaded.get(item["usuario"])
            if user and item["jefe"]:
                boss = loaded.get(item["jefe"]) or All.search([("login", "=", item["jefe"])],
                                                              limit=1)
                if boss and boss != user:
                    user.sudo().mirabilenet_supervisor_id = boss
        done_plan = [p for p in plan if p["usuario"] in loaded]
        self.write({"state": "done", "summary": self._summary(done_plan, notes, done=True)})
        self._set_review(notes)
        self.env["mirabilenet.audit.log"]._log(
            "importar", "Personal importado: %s persona(s)" % len(done_plan))
        return self._reopen()

    def _load_one(self, Users, item):
        vals = {"name": item["nombre"], "login": item["usuario"], "active": item["activo"],
                "mirabilenet_role": item["rol"],
                "mirabilenet_region_id": item["region"].id or False,
                "mirabilenet_branch_id": item["branch"].id or False}
        if item["correo"]:
            vals["email"] = item["correo"]
        user = item["user"]
        if not user:
            user = Users.mirabilenet_create_user(vals)
        elif user == self.env.user:
            # Nadie se cambia a sí mismo el rol ni la región: de su fila, solo lo demás.
            pass
        else:
            user.mirabilenet_update_user(vals)
        user = user.sudo()
        user.write({"mirabilenet_whatsapp": item["whatsapp"] or False,
                    "mirabilenet_zone_ids": [(6, 0, item["zones"].ids)]})
        return user

    def action_back(self):
        self.write({"state": "draft", "summary": False, "review_file": False})
        return self._reopen()

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new", "name": _("Importar personal")}

    def action_download_template(self):
        return {"type": "ir.actions.act_url", "url": TEMPLATE_URL, "target": "self"}
