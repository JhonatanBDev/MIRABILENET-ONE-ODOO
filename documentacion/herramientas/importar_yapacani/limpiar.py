"""Limpia datosyapacani_completo.csv: deja una version lista para importar y una lista para revisar."""
import collections
import csv
import datetime
import re

SRC = r'C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo\Static\Datos\datosyapacani_completo.csv'
OUT = r'C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo\Static\Datos\datosyapacani_limpio.csv'
REV = r'C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo\Static\Datos\datosyapacani_revisar_en_campo.csv'

rows = list(csv.reader(open(SRC, encoding='utf-8-sig', newline=''), delimiter=';'))
head = [h.strip() for h in rows[0]]
R = [dict(zip(head, [re.sub(r'\s+', ' ', c).strip() for c in r]), fila=i + 2)
     for i, r in enumerate(rows[1:])]
NODATA = {'', 'SIN DATO', 'ACTUALIZAR', 'S/D', '-', '0'}


def nd(v):
    return v.upper() in NODATA


BARRIO_FIX = {'24 DE SEPRIEMBRE': '24 DE SEPTIEMBRE', 'LUI ESPINAL': 'LUIS ESPINAL',
              'AMBORO2': 'AMBORO 2', 'AMBORO I': 'AMBORO 1',
              'CRISTO ES LA RESPUESTA': 'CRISTO LA RESPUESTA',
              'VILLA ESTUDIANTE': 'VILLA DEL ESTUDIANTE', 'BELEN': 'VILLA BELEN'}


def barrio(v):
    b = re.sub(r'^(B\s*/|B\.|BARRIO)\s*', '', v.upper()).strip()
    if nd(b):
        return ''
    return BARRIO_FIX.get(b, b)


DEPTO = {'SC': 'SC', 'SCZ': 'SC', 'S.C.': 'SC', 'S.C': 'SC', 'SC.': 'SC', 'CBBA': 'CB',
         'CBBA.': 'CB', 'CB': 'CB', 'ORURO': 'OR', 'OR': 'OR', 'LP': 'LP', 'PT': 'PT',
         'CH': 'CH', 'TJ': 'TJ', 'BE': 'BN', 'PA': 'PD'}


def documento(v):
    """Devuelve (numero, complemento, expedido, nota)."""
    if nd(v) or v.upper() == 'PRUEBA':
        return '', '', '', 'sin C.I.'
    u = v.upper().replace(' ', '')
    if u.startswith('E-'):
        return v.upper(), '', '', 'documento de extranjero'
    m = re.fullmatch(r'(\d{5,9})(?:-(\w{2}))?([A-Z.]*)', u)
    if not m:
        return '', '', '', 'C.I. ilegible: %s' % v
    num, comp, ext = m.groups()
    exp = DEPTO.get(ext, '') if ext else ''
    nota = '' if (not ext or exp) else 'expedido ilegible: %s' % ext
    return num, (comp or '').upper(), exp, nota


def mac(v):
    if nd(v) or v.upper() == 'PRUEBA':
        return '', 'sin MAC'
    u = re.sub(r'\(.*?\)', '', v.upper()).replace(':', '').replace('-', '').replace(' ', '')
    u = u.replace('O', '0')
    if re.fullmatch(r'[0-9A-F]{12}', u):
        return u, ('' if u == v.upper() else 'MAC corregida (%s)' % v)
    return '', 'MAC ilegible: %s' % v


BRAND = {'V-SOL': 'V-SOL', 'V-SOL_TV': 'V-SOL', 'V-SOL_24': 'V-SOL', 'V-SOL-CATV': 'V-SOL',
         'C-DATA': 'C-DATA', 'C- DATA': 'C-DATA', 'HUAWEI': 'HUAWEI', 'ZTE': 'ZTE',
         'LANLY': 'LANLY', 'XPON ONU GENERICO': 'GENERICO XPON'}
MODEL_FIX = {'V-2802GW': 'V2802GW', '2802GW': 'V2802GW', 'V282GW': 'V2802GW',
             'V28026W': 'V2802GW', 'FD51GW-X-R310': 'FD511GW-X-R310',
             'FD511GWX': 'FD511GW-X-R310', 'ED511GW-XR310': 'ED511GW-X-R310',
             'EG88141AS': 'EG8141A5'}


def equipo(b, m):
    brand = BRAND.get(b.upper(), '')
    model = m.upper()
    notas = []
    if nd(model) or model == 'PRUEBA':
        model = ''
    if re.fullmatch(r'(HGW|WGD)-[0-9A-F]{4,6}', model):
        notas.append('modelo %s parece el nombre de la red wifi' % model)
        model = ''
    elif re.fullmatch(r'(V\d{10,11}|GPON[0-9A-F]{8})', model):
        notas.append('en el modelo venía un número de serie: %s' % model)
        model = ''
    elif model in ('4 PUERTOS', 'G/EPON ONU'):
        notas.append('modelo no indicado (%s)' % m)
        model = ''
    if model in MODEL_FIX:
        notas.append('modelo corregido (%s)' % m)
        model = MODEL_FIX[model]
    if not brand and b.upper() not in NODATA:
        notas.append('marca desconocida: %s' % b)
    return brand, model, notas


def fecha(v):
    try:
        return datetime.datetime.strptime(v, '%d/%m/%Y').date()
    except ValueError:
        return None


def coord(v):
    try:
        return float(v.replace(',', '.'))
    except ValueError:
        return None


def nombre(v):
    n = v.upper()
    nota = ''
    m = re.search(r'\s*(\+.*|\bEN WS\b.*)$', n)
    if m:
        nota = m.group(1).strip(' +')
        n = n[:m.start()].strip()
    return n, nota


def plan(perfil):
    m = re.match(r'\s*(\d+)\s*MB', perfil.upper())
    return int(m.group(1)) if m else 0, 'CATV' in perfil.upper()


limpio, revisar = [], []
for r in R:
    if 'PRUEBA' in r['NOMBRE'].upper():
        revisar.append({'fila': r['fila'], 'cliente': r['NOMBRE'],
                        'que revisar': 'fila de prueba: no se importa'})
        continue
    obs, campo = [], []
    name, nota_nombre = nombre(r['NOMBRE'])
    if nota_nombre:
        obs.append('Nota en el nombre: ' + nota_nombre)
    num, comp, exp, nci = documento(r['C.I.'])
    if nci:
        (campo if ('ilegible' in nci or 'sin' in nci) else obs).append(nci)
    phone = re.sub(r'\D', '', r['TELEFONO'])
    if not re.fullmatch(r'[67]\d{7}', phone):
        campo.append('teléfono con %d dígitos: %s' % (len(phone), r['TELEFONO']))
    macv, nmac = mac(r['No. MAC'])
    if nmac:
        (campo if ('ilegible' in nmac or 'sin' in nmac) else obs).append(nmac)
    brand, model, nequ = equipo(r['MARCA'], r['MODELO'])
    obs += nequ
    serie = '' if nd(r['No. De SERIE']) else r['No. De SERIE'].upper()
    if not serie:
        campo.append('ONU sin número de serie')
    fs, fa = fecha(r['FECHA SOLICITUD']), fecha(r['FECHA ACTIVACION'])
    alta = fa or fs
    if not fa:
        campo.append('sin fecha de activación' + (' (se usa la de solicitud)' if fs else ''))
    if fs and fa and fa < fs:
        campo.append('activación %s antes de la solicitud %s'
                     % (r['FECHA ACTIVACION'], r['FECHA SOLICITUD']))
    lat, lon = coord(r['LATITUD']), coord(r['LONGITUD'])
    if lat is None or lon is None or not (-18.5 < lat < -16.5 and -65 < lon < -63):
        if r['LATITUD'] or r['LONGITUD']:
            campo.append('coordenadas inválidas: %s, %s' % (r['LATITUD'], r['LONGITUD']))
        else:
            campo.append('sin coordenadas')
        lat = lon = None
    mbps, tv = plan(r['PLAN win box'])
    direccion = '' if nd(r['DIRECCION']) else r['DIRECCION']
    limpio.append({
        'fila_original': r['fila'], 'nombre': name, 'ci': num, 'complemento': comp,
        'expedido': exp, 'telefono': phone, 'barrio': barrio(r['BARRIO']),
        'direccion': direccion, 'perfil_winbox': r['PLAN win box'], 'mbps': mbps,
        'incluye_tv': 'si' if tv else 'no', 'precio': r['PRECIO DEL PAQUETE'],
        'modalidad': r['MODALIDAD DE PAGO'].lower(), 'usuario_pppoe': r['USUARIO PPPoE'],
        'ip': r['IP REMOTA'], 'onu_marca': brand, 'onu_modelo': model, 'onu_serie': serie,
        'onu_mac': macv, 'fecha_solicitud': fs.isoformat() if fs else '',
        'fecha_alta': alta.isoformat() if alta else '',
        'latitud': '%.6f' % lat if lat is not None else '',
        'longitud': '%.6f' % lon if lon is not None else '',
        'observaciones': '; '.join(obs), 'revisar_en_campo': '; '.join(campo)})
    for c in campo:
        revisar.append({'fila': r['fila'], 'cliente': name, 'que revisar': c})

byci = collections.defaultdict(set)
for x in limpio:
    if x['ci']:
        byci[x['ci']].add(x['nombre'])
byserie = collections.defaultdict(list)
for x in limpio:
    if x['onu_serie']:
        byserie[x['onu_serie']].append(x)
for x in limpio:
    if x['ci'] and len(byci[x['ci']]) > 1:
        t = 'C.I. %s compartido con: %s' % (
            x['ci'], ', '.join(sorted(byci[x['ci']] - {x['nombre']})))
        x['revisar_en_campo'] = '; '.join(filter(None, [x['revisar_en_campo'], t]))
        revisar.append({'fila': x['fila_original'], 'cliente': x['nombre'], 'que revisar': t})
    if x['onu_serie'] and len(byserie[x['onu_serie']]) > 1:
        otros = [o['nombre'] for o in byserie[x['onu_serie']] if o is not x]
        t = 'misma ONU (serie %s) que: %s' % (x['onu_serie'], ', '.join(otros))
        x['revisar_en_campo'] = '; '.join(filter(None, [x['revisar_en_campo'], t]))
        revisar.append({'fila': x['fila_original'], 'cliente': x['nombre'], 'que revisar': t})

with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(limpio[0]), delimiter=';')
    w.writeheader()
    w.writerows(limpio)
with open(REV, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['fila', 'cliente', 'que revisar'], delimiter=';')
    w.writeheader()
    w.writerows(sorted(revisar, key=lambda x: x['fila']))

clientes = {(x['ci'] or x['nombre'], x['nombre']) for x in limpio}
print('servicios a importar:', len(limpio), '| clientes:', len(clientes),
      '| planes (perfiles):', len({x['perfil_winbox'] for x in limpio}))
print('con observaciones:', sum(1 for x in limpio if x['observaciones']),
      '| avisos para campo:', len(revisar), 'en', len({x['fila'] for x in revisar}), 'filas')
print(collections.Counter(re.sub(r'[:(].*', '', x['que revisar']).strip()
                          for x in revisar).most_common())
print('productos ONU:', sorted(collections.Counter(
    (x['onu_marca'], x['onu_modelo']) for x in limpio).items(), key=lambda kv: -kv[1]))
