import base64
import collections

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..cartera import limpieza

PLAN_MANAGER = "mirabilenet_isp.group_mirabilenet_plan_manager"
QUIET = {"tracking_disable": True, "mail_create_nolog": True, "mail_notrack": True}


class MirabilenetPortfolioImport(models.TransientModel):
    """Importa una planilla de cartera: planes, clientes, servicios activos, PPPoE y ONU."""
    _name = "mirabilenet.portfolio.import"
    _description = "MIRABILENET: importar cartera de clientes"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                default=lambda self: self.env.user.mirabilenet_region_id)
    file = fields.Binary(string="Planilla (CSV)", attachment=False)
    filename = fields.Char(string="Nombre del archivo")
    state = fields.Selection([("draft", "Subir"), ("preview", "Revisar"), ("done", "Hecho")],
                             default="draft")
    summary = fields.Html(string="Resumen", readonly=True, sanitize=True)
    review_file = fields.Binary(string="Lista para revisar en campo", readonly=True,
                                attachment=False)
    review_filename = fields.Char(default="revisar_en_campo.csv")
    replace_data = fields.Boolean(
        string="Reemplazar con los datos de esta planilla",
        help="Apagado (lo normal): en lo ya cargado solo se completan los datos vacíos y lo que "
             "venga distinto se lista sin cambiarlo. Encendido: lo distinto se reemplaza por lo "
             "de la planilla (teléfono, C.I., dirección, coordenadas, precio, fecha de alta, IP). "
             "El plan y la modalidad de pago nunca se cambian solos.")

    # ------------------------------------------------------------------
    # Permisos
    # ------------------------------------------------------------------
    def _mirabilenet_check_import_access(self):
        user = self.env.user
        if not self.env.su and not user.has_group(PLAN_MANAGER):
            raise AccessError(_("Solo gerencia y administración regional importan cartera: "
                                "la importación también crea planes."))
        if (not self.env.su and not user.mirabilenet_is_global
                and not user._mirabilenet_is_super()
                and user.mirabilenet_region_id != self.region_id):
            raise AccessError(_("Solo puede importar cartera de su propia región."))

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def _read(self):
        if not self.file:
            raise UserError(_("Suba la planilla en CSV."))
        try:
            columnas, filas, desconocidas = limpieza.leer_csv(base64.b64decode(self.file))
        except (ValueError, UnicodeError) as error:
            raise UserError(_("No se pudo leer %(file)s: %(error)s",
                              file=self.filename or "", error=error)) from error
        faltan = [c for c in limpieza.OBLIGATORIAS if c not in columnas]
        if faltan:
            raise UserError(_(
                "A la planilla le faltan columnas obligatorias: %(cols)s. Descargue la plantilla "
                "desde este asistente para ver los nombres que se reconocen.",
                cols=", ".join(faltan)))
        if not filas:
            raise UserError(_("La planilla no tiene filas con datos."))
        registros, avisos = limpieza.limpiar(filas)
        return registros, avisos, desconocidas

    def _plan_code(self, perfil):
        return "%s-%s" % (self.region_id.code, limpieza.codigo(perfil))

    def _onu_code(self, marca, modelo):
        return "ONU-" + limpieza.codigo("%s %s" % (marca or "SM", modelo or "SD"))

    def _nap_index(self):
        """Cajas de la región por código y por nombre corto (solo si el nombre no se repite)."""
        naps = self.env["mirabilenet.fiber.nap"].sudo().with_context(active_test=False).search(
            [("region_id", "=", self.region_id.id)])
        index = {nap.code.upper(): nap for nap in naps if nap.code}
        names = collections.Counter((nap.name or "").upper() for nap in naps if nap.name)
        for nap in naps:
            name = (nap.name or "").upper()
            if name and names[name] == 1:
                index.setdefault(name, nap)
        return index

    def _port_problem(self, r, naps, taken):
        """-> (puerto, problema). Sin caja en la fila devuelve (None, None)."""
        if not r["caja_nap"]:
            return None, None
        nap = naps.get(r["caja_nap"])
        if not nap:
            return None, "la caja %s no existe en la región: no se asigna" % r["caja_nap"]
        port = nap.port_ids.filtered(lambda p: p.number == r["puerto"])
        if not port:
            return None, "la caja %s tiene %s puertos: no existe el puerto %s" % (
                nap.code, nap.port_count, r["puerto"])
        usuario = port.service_id.pppoe_ids[:1].username
        if port.service_id and usuario != r["usuario_pppoe"]:
            return None, "el puerto %s de %s ya es de %s: no se asigna" % (
                port.number, nap.code, port.service_id.partner_id.name)
        if taken.get(port.id, r["usuario_pppoe"]) != r["usuario_pppoe"]:
            return None, "el puerto %s de %s también figura para %s en la planilla" % (
                port.number, nap.code, taken[port.id])
        if port.state == "danado":
            return None, "el puerto %s de %s está marcado como dañado: no se asigna" % (
                port.number, nap.code)
        taken[port.id] = r["usuario_pppoe"]
        return port, None

    @staticmethod
    def _key(r):
        return (r["ci"] or r["nombre"], r["nombre"])

    def _find_partner(self, r, Partner, Pppoe):
        """El cliente de la fila, sin duplicarlo:

        1. el titular del servicio, si el usuario PPPoE ya está cargado;
        2. el cliente de la región con ese nombre y ese C.I.;
        3. el único cliente con ese nombre cuyo C.I. no choca (vacío en uno de los dos).

        Si el C.I. coincide pero el nombre no, es otra persona (familias que comparten carnet):
        no se mezcla.
        """
        account = Pppoe.search([("username", "=", r["usuario_pppoe"])], limit=1)
        if account and account.region_id == self.region_id:
            return account.service_id.partner_id
        base = [("mirabilenet_is_customer", "=", True),
                ("mirabilenet_region_id", "=", self.region_id.id), ("name", "=", r["nombre"])]
        if r["ci"]:
            exact = Partner.search(base + [("vat", "=", r["ci"])], limit=1)
            if exact:
                return exact
        same_name = Partner.search(base)
        if r["ci"]:
            same_name = same_name.filtered(lambda p: not p.vat)
        return same_name if len(same_name) == 1 else Partner.browse()

    # ------------------------------------------------------------------
    # Completar lo ya cargado
    # ------------------------------------------------------------------
    @staticmethod
    def _same(current, new):
        if isinstance(current, float) or isinstance(new, float):
            try:
                return abs(float(current or 0) - float(new or 0)) < 1e-5
            except (TypeError, ValueError):
                return False
        return str(current or "").strip().upper() == str(new or "").strip().upper()

    @staticmethod
    def _show(value):
        if isinstance(value, float):
            return "%g" % value
        return str(value)

    def _reconcile(self, record, pairs, cnt, notas, apply=True):
        """Completa los vacíos; lo distinto lo reemplaza o lo anota según la opción.

        ``pairs``: (campo, etiqueta, valor de la planilla). Con ``apply=False`` solo cuenta
        (para la revisión).
        """
        vals = {}
        for field, label, new in pairs:
            if new in (None, "", False):
                continue
            current = record[field]
            if current in (None, "", False):
                vals[field] = new
                cnt["datos completados"] += 1
            elif not self._same(current, new):
                if self.replace_data:
                    vals[field] = new
                    cnt["datos reemplazados"] += 1
                    notas.append("%s reemplazado: antes %s, ahora %s" % (
                        label, self._show(current), self._show(new)))
                else:
                    cnt["datos distintos sin cambiar"] += 1
                    notas.append("%s distinto: en Odoo %s, en la planilla %s (no se cambió)" % (
                        label, self._show(current), self._show(new)))
        if vals and apply:
            record.write(vals)

    def _reconcile_partner(self, partner, r, cnt, notas, apply=True):
        """Cliente: los datos de la planilla y el WhatsApp, que sigue al teléfono.

        Con varios servicios, la dirección y las coordenadas de cada fila son las del servicio
        (que se comparan con su dirección de instalación): en el cliente solo se completan.
        """
        pairs = self._partner_pairs(r)
        services = self.env["mirabilenet.service"].sudo().search_count(
            [("partner_id", "=", partner.id)])
        if services > 1:
            location = {"street", "street2", "partner_latitude", "partner_longitude"}
            self._reconcile(partner, [p for p in pairs if p[0] in location and not partner[p[0]]],
                            cnt, notas, apply)
            pairs = [p for p in pairs if p[0] not in location]
        self._reconcile(partner, pairs, cnt, notas, apply)
        if apply and r["telefono"] and (not partner.mirabilenet_whatsapp or (
                self.replace_data and partner.phone == r["telefono"])):
            partner.mirabilenet_whatsapp = r["telefono"]

    def _partner_pairs(self, r):
        pairs = [("vat", "C.I.", r["ci"]), ("phone", "teléfono", r["telefono"]),
                 ("street", "dirección", r["direccion"]),
                 ("street2", "barrio", ("B/ " + r["barrio"]) if r["barrio"] else "")]
        if r["latitud"] is not None:
            pairs += [("partner_latitude", "latitud", r["latitud"]),
                      ("partner_longitude", "longitud", r["longitud"])]
        if r["complemento"] and "mira_siat_complement" in self.env["res.partner"]._fields:
            pairs.append(("mira_siat_complement", "complemento del C.I.", r["complemento"]))
        return pairs

    def _complete_existing(self, r, partner, service, account, cnt, notas, Pppoe, apply=True):
        """Una fila de un servicio ya cargado: completa cliente, servicio y cuenta PPPoE."""
        if not self._same(partner.name, r["nombre"]):
            notas.append("nombre distinto: en Odoo %s, en la planilla %s (no se cambió)" % (
                partner.name, r["nombre"]))
            cnt["datos distintos sin cambiar"] += 1
        self._reconcile_partner(partner, r, cnt, notas, apply)
        direccion = ", ".join(x for x in (
            r["direccion"], ("B/ " + r["barrio"]) if r["barrio"] else "") if x)
        self._reconcile(service, [
            ("install_address", "dirección de instalación", direccion),
            ("date_start", "fecha de alta", r["fecha_alta"]),
            ("monthly_price", "precio mensual", r["precio"])], cnt, notas, apply)
        # El plan y la modalidad cambian el perfil del router y el cobro: nunca solos.
        if r["perfil"] and not self._same(service.plan_id.mirabilenet_ppp_profile, r["perfil"]):
            notas.append("plan distinto: en Odoo %s, en la planilla %s (cámbielo desde el "
                         "servicio)" % (service.plan_id.mirabilenet_ppp_profile
                                        or service.plan_id.name, r["perfil"]))
            cnt["datos distintos sin cambiar"] += 1
        if r["modalidad"] and service.payment_mode != r["modalidad"]:
            notas.append("modalidad distinta: en Odoo %s, en la planilla %s (cámbiela desde el "
                         "servicio)" % (service.payment_mode, r["modalidad"]))
            cnt["datos distintos sin cambiar"] += 1
        ip = r["ip"]
        if ip:
            owner = Pppoe.search([("fixed_ip", "=", ip), ("id", "!=", account.id)], limit=1)
            if owner and not self._same(account.fixed_ip, ip):
                notas.append("la IP %s ya es de %s: no se carga" % (
                    ip, owner.service_id.partner_id.name))
                ip = ""
        pairs = [("fixed_ip", "IP", ip)]
        if not account.profile:
            # El perfil va con el plan: si difiere, ya quedó anotado arriba como plan distinto.
            pairs.append(("profile", "perfil", r["perfil"]))
        self._reconcile(account, pairs, cnt, notas, apply)

    # ------------------------------------------------------------------
    # Paso 1: revisar sin guardar nada
    # ------------------------------------------------------------------
    def action_preview(self):
        self.ensure_one()
        self._mirabilenet_check_import_access()
        registros, avisos, desconocidas = self._read()
        validos = [r for r in registros if not r["error"]]
        Tmpl = self.env["product.template"].sudo().with_context(active_test=False)
        Partner = self.env["res.partner"].sudo().with_context(active_test=False)
        Pppoe = self.env["mirabilenet.pppoe.account"].sudo()
        perfiles = sorted({r["perfil"] for r in validos})
        planes_nuevos = [p for p in perfiles
                         if not Tmpl.search_count([("mirabilenet_plan_code", "=",
                                                    self._plan_code(p))])]
        sin_velocidad = [p for p in planes_nuevos
                         if not next(r for r in validos if r["perfil"] == p)["mbps"]]
        clientes = {}
        for r in validos:
            partner = self._find_partner(r, Partner, Pppoe)
            clientes.setdefault(("p", partner.id) if partner else ("n",) + self._key(r),
                                bool(partner))
        clientes_existentes = sum(1 for found in clientes.values() if found)
        cambios = collections.Counter()
        ya_importados = 0
        for r in validos:
            account = Pppoe.search([("username", "=", r["usuario_pppoe"])], limit=1)
            if account and account.region_id == self.region_id:
                ya_importados += 1
                notas = []
                self._complete_existing(r, account.service_id.partner_id, account.service_id,
                                        account, cambios, notas, Pppoe, apply=False)
                avisos.extend({"fila": r["fila"], "cliente": r["nombre"], "que_revisar": n}
                              for n in notas)
        onu = {r["serie"] for r in validos if r["serie"]}
        naps, taken, puertos_ok = self._nap_index(), {}, 0
        for r in validos:
            port, problema = self._port_problem(r, naps, taken)
            if problema:
                avisos.append({"fila": r["fila"], "cliente": r["nombre"],
                               "que_revisar": problema})
            elif port:
                puertos_ok += 1
        avisos.sort(key=lambda a: a["fila"])
        lineas = [
            _("Filas leídas: %s", len(registros) + sum(
                1 for a in avisos if a["que_revisar"].startswith("fila de prueba"))),
            _("Servicios a crear: %s (ya importados: %s)", len(validos) - ya_importados,
              ya_importados),
            _("Clientes: %s nuevos, %s ya existen", len(clientes) - clientes_existentes,
              clientes_existentes),
            _("Planes nuevos: %s", len(planes_nuevos)),
            _("ONU con número de serie: %s", len(onu)),
            _("Servicios con caja NAP y puerto: %s", puertos_ok),
            _("En lo ya cargado: %(fill)s datos a completar, %(diff)s distintos (%(what)s)",
              fill=cambios["datos completados"],
              diff=cambios["datos distintos sin cambiar"] + cambios["datos reemplazados"],
              what=_("se reemplazan") if self.replace_data else _("no se cambian")),
            _("Avisos para revisar en campo: %s", len(avisos)),
        ]
        errores = [r for r in registros if r["error"]]
        if errores:
            lineas.append(_("Filas que NO se importan: %s", len(errores)))
        if sin_velocidad:
            lineas.append(_("Perfiles sin velocidad legible (sus filas no se importan): %s",
                            ", ".join(sin_velocidad)))
        if desconocidas:
            lineas.append(_("Columnas que no se reconocen y se ignoran: %s",
                            ", ".join(desconocidas)))
        detalle = ""
        if planes_nuevos:
            detalle = "<p><b>%s</b></p><ul>%s</ul>" % (_("Planes que se crearán"), "".join(
                "<li>%s</li>" % self._plan_name(p, validos) for p in planes_nuevos))
        self.write({
            "state": "preview",
            "summary": "<ul>%s</ul>%s<p>%s</p>" % (
                "".join("<li>%s</li>" % line for line in lineas), detalle,
                _("Los servicios entran activos, sin órdenes a los routers y sin contrato de "
                  "cobro. Nada se guarda hasta pulsar «Importar».")),
            "review_file": base64.b64encode(limpieza.avisos_csv(avisos)),
            "review_filename": "revisar_en_campo_%s.csv" % (self.region_id.code or "region"),
        })
        return self._reopen()

    def _plan_name(self, perfil, registros):
        muestra = [r for r in registros if r["perfil"] == perfil]
        precio = collections.Counter(r["precio"] for r in muestra).most_common(1)[0][0]
        mbps, tv = muestra[0]["mbps"], muestra[0]["tv"]
        moneda = self.region_id.currency_id.symbol or self.region_id.currency_id.name or ""
        return "%s Mbps%s · %s %s (%s)" % (mbps, " + TV" if tv else "", moneda,
                                           ("%g" % precio), perfil)

    # ------------------------------------------------------------------
    # Paso 2: importar
    # ------------------------------------------------------------------
    def action_import(self):
        self.ensure_one()
        self._mirabilenet_check_import_access()
        registros, avisos, _desconocidas = self._read()
        env = self.sudo().with_context(**QUIET).env
        region = self.region_id
        Tmpl = env["product.template"].with_context(active_test=False)
        Partner = env["res.partner"].with_context(active_test=False)
        Service, Pppoe, Lot = (env["mirabilenet.service"], env["mirabilenet.pppoe.account"],
                               env["stock.lot"])
        bolivia = env.ref("base.bo")
        plan_categ = env["product.category"].search([("name", "=", "Planes de internet")],
                                                    limit=1)
        onu_categ = env["product.category"].search([("complete_name", "ilike", "ONU / ONT")],
                                                   limit=1)
        siat = "mira_siat_complement" in Partner._fields
        cnt = collections.Counter()
        fallas = []
        validos = [r for r in registros if not r["error"]]
        cnt["filas que no se importan"] = len(registros) - len(validos)

        planes = {}
        for perfil in sorted({r["perfil"] for r in validos}):
            code = self._plan_code(perfil)
            plan = Tmpl.search([("mirabilenet_plan_code", "=", code)], limit=1)
            if not plan:
                muestra = [r for r in validos if r["perfil"] == perfil]
                mbps, tv = muestra[0]["mbps"], muestra[0]["tv"]
                if not mbps:
                    continue
                precio = collections.Counter(r["precio"] for r in muestra).most_common(1)[0][0]
                vals = {"name": self._plan_name(perfil, validos), "type": "service",
                        "mirabilenet_is_plan": True, "mirabilenet_plan_code": code,
                        "mirabilenet_region_id": region.id, "mirabilenet_down_mbps": mbps,
                        "mirabilenet_up_mbps": mbps, "mirabilenet_includes_tv": tv,
                        "mirabilenet_ppp_profile": perfil, "list_price": precio,
                        "mirabilenet_publish_web": False,
                        "sale_ok": True, "purchase_ok": False}
                if "taxes_id" in Tmpl._fields:
                    vals["taxes_id"] = [(5, 0, 0)]
                if plan_categ:
                    vals["categ_id"] = plan_categ.id
                plan = Tmpl.create(vals)
                cnt["planes creados"] += 1
            planes[perfil] = plan

        productos = {}
        for marca, modelo in sorted({(r["marca"], r["modelo"]) for r in validos if r["serie"]}):
            code = self._onu_code(marca, modelo)
            prod = Tmpl.search([("default_code", "=", code)], limit=1)
            if not prod:
                vals = {"name": "ONU %s %s" % (marca or "sin marca", modelo or "(modelo sin dato)"),
                        "default_code": code, "type": "consu", "is_storable": True,
                        "tracking": "serial", "mirabilenet_brand": marca or False,
                        "mirabilenet_model": modelo or False, "sale_ok": False}
                if "taxes_id" in Tmpl._fields:
                    vals["taxes_id"] = [(5, 0, 0)]
                if onu_categ:
                    vals["categ_id"] = onu_categ.id
                prod = Tmpl.create(vals)
                cnt["productos ONU creados"] += 1
            productos[(marca, modelo)] = prod

        clientes, naps, taken = {}, self._nap_index(), {}
        for r in validos:
            if r["perfil"] not in planes:
                fallas.append((r["fila"], r["nombre"], _("el perfil no tiene velocidad legible")))
                continue
            # Lo de la fila cuenta solo si la fila se guarda: si falla, el savepoint la deshace
            # y su cliente recién creado no debe quedar en memoria para las filas siguientes.
            row_cnt, row_notas = collections.Counter(), []
            try:
                with env.cr.savepoint():
                    key, partner, service = self._import_row(
                        r, region, planes, productos, clientes, row_cnt, bolivia, siat,
                        Partner, Service, Pppoe, Lot, row_notas)
            except Exception as error:  # pylint: disable=broad-except
                fallas.append((r["fila"], r["nombre"], str(error).splitlines()[0][:200]))
                continue
            clientes[key] = partner
            cnt.update(row_cnt)
            avisos.extend({"fila": r["fila"], "cliente": r["nombre"], "que_revisar": n}
                          for n in row_notas)
            # El puerto va aparte: un problema con la caja no deshace el cliente ni el servicio.
            port, problema = self._port_problem(r, naps, taken)
            if problema:
                avisos.append({"fila": r["fila"], "cliente": r["nombre"],
                               "que_revisar": problema})
            elif port:
                try:
                    with env.cr.savepoint():
                        nota = self._assign_port(port.sudo(), service, cnt)
                except Exception as error:  # pylint: disable=broad-except
                    nota = "no se pudo asignar el puerto: %s" % str(error).splitlines()[0][:150]
                if nota:
                    avisos.append({"fila": r["fila"], "cliente": r["nombre"],
                                   "que_revisar": nota})
        for fila, cliente, motivo in fallas:
            avisos.append({"fila": fila, "cliente": cliente,
                           "que_revisar": "NO SE IMPORTÓ: %s" % motivo})
        avisos.sort(key=lambda a: a["fila"])
        env["mirabilenet.audit.log"]._log(
            "importar_cartera", "Importación de cartera %s: %s servicios, %s clientes nuevos" % (
                self.filename or "", cnt["servicios creados"], cnt["clientes creados"]),
            region=region, payload=dict(cnt, fallas=len(fallas)))
        orden = ["planes creados", "clientes creados", "clientes que ya existían",
                 "servicios creados", "servicios ya importados (no se duplican)",
                 "cuentas PPPoE creadas", "productos ONU creados", "ONU registradas",
                 "ONU que ya estaban registradas", "ONU repetidas (no se duplican)",
                 "puertos NAP asignados",
                 "puertos NAP que ya estaban asignados", "servicios cambiados de puerto",
                 "datos completados", "datos reemplazados", "datos distintos sin cambiar",
                 "filas que no se importan"]
        lineas = ["%s: %s" % (k[:1].upper() + k[1:], cnt[k]) for k in orden if cnt[k]]
        lineas.append(_("Filas con error al guardar: %s", len(fallas)))
        lineas.append(_("Avisos para revisar en campo: %s", len(avisos)))
        self.write({
            "state": "done",
            "summary": "<ul>%s</ul><p>%s</p>" % (
                "".join("<li>%s</li>" % line for line in lineas),
                _("Los avisos también quedaron en las notas de cada cliente y servicio. Los "
                  "contratos de cobro se crean cuando se decida desde qué fecha cobra Odoo.")),
            "review_file": base64.b64encode(limpieza.avisos_csv(avisos)),
        })
        return self._reopen()

    def _import_row(self, r, region, planes, productos, clientes, cnt, bolivia, siat,
                    Partner, Service, Pppoe, Lot, notas_fila):
        key = self._key(r)
        notas = list(r["observaciones"]) + list(r["campo"])
        existing = Pppoe.search([("username", "=", r["usuario_pppoe"])], limit=1)
        if existing and existing.region_id != region:
            raise UserError(_("el usuario PPPoE %s ya existe en otra región",
                              r["usuario_pppoe"]))
        if existing:
            service = existing.service_id
            partner = service.partner_id
            if key not in clientes:
                cnt["clientes que ya existían"] += 1
            cnt["servicios ya importados (no se duplican)"] += 1
            self._complete_existing(r, partner, service, existing, cnt, notas_fila, Pppoe)
            self._register_onu(r, partner, productos, region, Lot, cnt, notas_fila)
            return key, partner, service

        partner = clientes.get(key) or self._find_partner(r, Partner, Pppoe)
        if partner:
            if key not in clientes:
                cnt["clientes que ya existían"] += 1
                self._reconcile_partner(partner, r, cnt, notas_fila)
        else:
            notas_cliente = (["C.I. expedido en %s" % r["expedido"]] if r["expedido"] else []) \
                + notas
            if r["ci"]:
                otro = Partner.search([("mirabilenet_is_customer", "=", True),
                                       ("mirabilenet_region_id", "=", region.id),
                                       ("vat", "=", r["ci"])], limit=1)
                if otro:
                    nota = "C.I. %s también es de %s: se crea otro cliente" % (r["ci"], otro.name)
                    notas_cliente.append(nota)
                    notas_fila.append(nota)
            vals = {"name": r["nombre"], "mirabilenet_is_customer": True,
                    "mirabilenet_region_id": region.id,
                    "mirabilenet_customer_type": "residencial", "mirabilenet_state": "activo",
                    "phone": r["telefono"] or False, "mirabilenet_whatsapp": r["telefono"] or False,
                    "vat": r["ci"] or False, "street": r["direccion"] or False,
                    "street2": ("B/ " + r["barrio"]) if r["barrio"] else False,
                    "city": region.name, "country_id": bolivia.id,
                    "comment": "<br>".join(notas_cliente) or False}
            if r["latitud"] is not None:
                vals.update(partner_latitude=r["latitud"], partner_longitude=r["longitud"])
            if siat and r["complemento"]:
                vals["mira_siat_complement"] = r["complemento"]
            partner = Partner.create(vals)
            cnt["clientes creados"] += 1

        ip = r["ip"]
        if ip:
            owner = Pppoe.search([("fixed_ip", "=", ip)], limit=1)
            if owner:
                nota = "la IP %s ya es de %s: no se carga" % (ip, owner.service_id.partner_id.name)
                notas.append(nota)
                notas_fila.append(nota)
                ip = ""
        direccion = ", ".join(x for x in (
            r["direccion"], ("B/ " + r["barrio"]) if r["barrio"] else "") if x)
        notas_servicio = ["Importado de %s, fila %s." % (self.filename or "la planilla",
                                                        r["fila"])] + notas
        if r["serie"]:
            notas_servicio.append("ONU: %s %s, serie %s, MAC %s" % (
                r["marca"] or "sin marca", r["modelo"] or "(modelo sin dato)", r["serie"],
                r["mac"] or "sin dato"))
        service = Service.create({
            "partner_id": partner.id, "region_id": region.id,
            "plan_id": planes[r["perfil"]].id, "state": "activo",
            "payment_mode": r["modalidad"], "date_start": r["fecha_alta"] or False,
            "monthly_price": r["precio"], "install_address": direccion or False,
            "notes": "\n".join(notas_servicio)})
        cnt["servicios creados"] += 1
        Pppoe.create({"service_id": service.id, "username": r["usuario_pppoe"],
                      "fixed_ip": ip or False, "profile": r["perfil"], "synced": False})
        cnt["cuentas PPPoE creadas"] += 1
        self._register_onu(r, partner, productos, region, Lot, cnt, notas_fila)
        return key, partner, service

    def _register_onu(self, r, partner, productos, region, Lot, cnt, notas):
        if not r["serie"]:
            return
        lot = Lot.search([("name", "=", r["serie"])], limit=1)
        if not lot:
            Lot.create({"name": r["serie"],
                        "product_id": productos[(r["marca"], r["modelo"])].product_variant_id.id,
                        "mirabilenet_state": "en_cliente", "mirabilenet_region_id": region.id,
                        "mirabilenet_partner_id": partner.id,
                        "mirabilenet_mac": r["mac"] or False})
            cnt["ONU registradas"] += 1
        elif lot.mirabilenet_partner_id and lot.mirabilenet_partner_id != partner:
            notas.append("la ONU serie %s figura en %s: no se cambia" % (
                r["serie"], lot.mirabilenet_partner_id.name))
            cnt["ONU repetidas (no se duplican)"] += 1
        else:
            if not lot.mirabilenet_mac and r["mac"]:
                lot.mirabilenet_mac = r["mac"]
            cnt["ONU que ya estaban registradas"] += 1

    def _assign_port(self, port, service, cnt):
        """Conecta el servicio al puerto. Si estaba en otro puerto, lo mueve. Devuelve una nota
        para la lista de revisión cuando cambia algo que ya estaba cargado."""
        if port.service_id == service:
            cnt["puertos NAP que ya estaban asignados"] += 1
            return None
        before = service.sudo().fiber_port_id
        if before:
            before.action_release()
        port.with_context(**QUIET).write({"service_id": service.id})
        cnt["puertos NAP asignados"] += 1
        if before:
            cnt["servicios cambiados de puerto"] += 1
            return "se cambió de %s puerto %s a %s puerto %s" % (
                before.nap_id.code, before.number, port.nap_id.code, port.number)
        return None

    # ------------------------------------------------------------------
    def action_back(self):
        self.write({"state": "draft", "summary": False, "review_file": False})
        return self._reopen()

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new", "name": _("Importar cartera")}

    @api.model
    def action_download_template(self):
        return {"type": "ir.actions.act_url", "target": "download",
                "url": "/mirabilenet_cartera/static/plantillas/plantilla_cartera_clientes.csv"}
