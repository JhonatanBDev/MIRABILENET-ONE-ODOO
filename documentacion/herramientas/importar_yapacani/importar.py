# Se ejecuta con: odoo-bin shell -c odoo.conf -d <base> < importar.py
# Importa datosyapacani_limpio.csv: planes, clientes, servicios activos, cuentas PPPoE y ONU.
# Repetirlo no duplica: busca cada registro por su clave antes de crearlo.
import collections
import csv
import re

CSV = r'C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo\Static\Datos\datosyapacani_limpio.csv'
env = env(su=True, context=dict(env.context, tracking_disable=True, mail_create_nolog=True,
                                 mail_notrack=True))
rows = list(csv.DictReader(open(CSV, encoding='utf-8-sig', newline=''), delimiter=';'))

Region = env['mirabilenet.region']
region = Region.search([('code', '=', 'YAP')], limit=1)
assert region, 'falta la región Yapacaní (código YAP)'
bo = env.ref('base.bo')
scz = env['res.country.state'].search([('country_id', '=', bo.id), ('name', 'ilike', 'Santa Cruz')],
                                      limit=1)
Tmpl = env['product.template'].with_context(active_test=False)
Partner = env['res.partner'].with_context(active_test=False)
Service = env['mirabilenet.service']
Pppoe = env['mirabilenet.pppoe.account']
Lot = env['stock.lot']
plan_categ = env['product.category'].search([('name', '=', 'Planes de internet')], limit=1)
onu_categ = env['product.category'].search([('complete_name', 'ilike', 'ONU / ONT')], limit=1)
siat = 'mira_siat_complement' in Partner._fields
cnt = collections.Counter()
errores = []


def slug(s):
    return re.sub(r'[^A-Z0-9]+', '-', s.upper()).strip('-')


# 1. Planes: uno por perfil de Winbox --------------------------------------------------------
planes = {}
for perfil in sorted({r['perfil_winbox'] for r in rows}):
    muestra = [r for r in rows if r['perfil_winbox'] == perfil]
    precio = collections.Counter(r['precio'] for r in muestra).most_common(1)[0][0]
    mbps = int(muestra[0]['mbps'])
    tv = muestra[0]['incluye_tv'] == 'si'
    code = 'YAP-' + slug(perfil)
    plan = Tmpl.search([('mirabilenet_plan_code', '=', code)], limit=1)
    if not plan:
        vals = {'name': '%s Mbps%s · Bs %s (%s)' % (mbps, ' + TV' if tv else '', precio, perfil),
                'type': 'service', 'mirabilenet_is_plan': True, 'mirabilenet_plan_code': code,
                'mirabilenet_region_id': region.id, 'mirabilenet_down_mbps': mbps,
                'mirabilenet_up_mbps': mbps, 'mirabilenet_includes_tv': tv,
                'mirabilenet_ppp_profile': perfil, 'list_price': float(precio),
                'mirabilenet_publish_web': False, 'taxes_id': [(5, 0, 0)],
                'sale_ok': True, 'purchase_ok': False}
        if plan_categ:
            vals['categ_id'] = plan_categ.id
        plan = Tmpl.create(vals)
        cnt['planes creados'] += 1
    else:
        cnt['planes existentes'] += 1
    planes[perfil] = plan

# 2. Productos de ONU --------------------------------------------------------------------------
productos = {}
for marca, modelo in sorted({(r['onu_marca'], r['onu_modelo']) for r in rows if r['onu_serie']}):
    nombre = 'ONU %s %s' % (marca or 'sin marca', modelo or '(modelo sin dato)')
    code = 'ONU-' + slug('%s %s' % (marca or 'SM', modelo or 'SD'))
    prod = Tmpl.search([('default_code', '=', code)], limit=1)
    if not prod:
        vals = {'name': nombre, 'default_code': code, 'type': 'consu', 'is_storable': True,
                'tracking': 'serial', 'mirabilenet_brand': marca or False,
                'mirabilenet_model': modelo or False, 'taxes_id': [(5, 0, 0)],
                'sale_ok': False}
        if onu_categ:
            vals['categ_id'] = onu_categ.id
        prod = Tmpl.create(vals)
        cnt['productos ONU creados'] += 1
    productos[(marca, modelo)] = prod

# 3. Clientes, servicios, cuentas PPPoE y ONU --------------------------------------------------
clientes = {}
for r in rows:
    fila = r['fila_original']
    try:
        with env.cr.savepoint():
            key = (r['ci'] or r['nombre'], r['nombre'])
            partner = clientes.get(key)
            if not partner:
                dom = [('mirabilenet_is_customer', '=', True), ('mirabilenet_region_id', '=', region.id),
                       ('name', '=', r['nombre'])]
                if r['ci']:
                    dom.append(('vat', '=', r['ci']))
                partner = Partner.search(dom, limit=1)
            notas_cliente = [x for x in (r['observaciones'], r['revisar_en_campo']) if x]
            if r['expedido']:
                notas_cliente.insert(0, 'C.I. expedido en %s' % r['expedido'])
            if not partner:
                vals = {'name': r['nombre'], 'mirabilenet_is_customer': True,
                        'mirabilenet_region_id': region.id,
                        'mirabilenet_customer_type': 'residencial', 'mirabilenet_state': 'activo',
                        'phone': r['telefono'] or False,
                        'mirabilenet_whatsapp': r['telefono'] or False,
                        'vat': r['ci'] or False, 'street': r['direccion'] or False,
                        'street2': ('B/ ' + r['barrio']) if r['barrio'] else False,
                        'city': 'Yapacaní', 'state_id': scz.id or False, 'country_id': bo.id,
                        'comment': '\n'.join(notas_cliente) or False}
                if r['latitud']:
                    vals.update(partner_latitude=float(r['latitud']),
                                partner_longitude=float(r['longitud']))
                if siat and r['complemento']:
                    vals['mira_siat_complement'] = r['complemento']
                partner = Partner.create(vals)
                cnt['clientes creados'] += 1
            elif key not in clientes:
                cnt['clientes existentes'] += 1
            clientes[key] = partner

            if Pppoe.search_count([('username', '=', r['usuario_pppoe'])]):
                cnt['servicios ya importados'] += 1
                continue
            direccion = ', '.join(x for x in (r['direccion'], ('B/ ' + r['barrio']) if r['barrio'] else '') if x)
            notas_servicio = ['Importado de datosyapacani_completo.csv, fila %s.' % fila]
            notas_servicio += [x for x in (r['observaciones'], r['revisar_en_campo']) if x]
            if r['onu_serie']:
                notas_servicio.append('ONU: %s %s, serie %s, MAC %s' % (
                    r['onu_marca'] or 'sin marca', r['onu_modelo'] or '(modelo sin dato)',
                    r['onu_serie'], r['onu_mac'] or 'sin dato'))
            service = Service.create({
                'partner_id': partner.id, 'region_id': region.id,
                'plan_id': planes[r['perfil_winbox']].id, 'state': 'activo',
                'payment_mode': r['modalidad'] or 'prepago',
                'date_start': r['fecha_alta'] or False,
                'monthly_price': float(r['precio']),
                'install_address': direccion or False, 'notes': '\n'.join(notas_servicio)})
            cnt['servicios creados'] += 1
            Pppoe.create({'service_id': service.id, 'username': r['usuario_pppoe'],
                          'fixed_ip': r['ip'] or False, 'profile': r['perfil_winbox'],
                          'synced': False})
            cnt['cuentas PPPoE creadas'] += 1

            if r['onu_serie']:
                prod = productos[(r['onu_marca'], r['onu_modelo'])].product_variant_id
                lot = Lot.search([('name', '=', r['onu_serie'])], limit=1)
                if lot:
                    cnt['ONU repetidas (no se duplican)'] += 1
                else:
                    Lot.create({'name': r['onu_serie'], 'product_id': prod.id,
                                'mirabilenet_state': 'en_cliente',
                                'mirabilenet_region_id': region.id,
                                'mirabilenet_partner_id': partner.id,
                                'mirabilenet_mac': r['onu_mac'] or False})
                    cnt['ONU registradas'] += 1
    except Exception as exc:  # pylint: disable=broad-except
        errores.append((fila, r['nombre'], str(exc).splitlines()[0][:200]))

env.cr.commit()
for k, v in cnt.items():
    print('%s: %s' % (k, v))
print('errores: %s' % len(errores))
for e in errores:
    print('  fila %s %s: %s' % e)
print('TOTALES region YAP -> clientes %s, servicios %s, PPPoE %s, planes %s' % (
    Partner.search_count([('mirabilenet_region_id', '=', region.id), ('mirabilenet_is_customer', '=', True)]),
    Service.search_count([('region_id', '=', region.id)]),
    Pppoe.search_count([('region_id', '=', region.id)]),
    Tmpl.search_count([('mirabilenet_region_id', '=', region.id), ('mirabilenet_is_plan', '=', True)])))
