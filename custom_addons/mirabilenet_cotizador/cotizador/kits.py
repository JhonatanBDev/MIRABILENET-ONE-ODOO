"""Arma una cotización a partir de un kit plantilla. Traída de referencia/core/kits.py:
recibe el catálogo `cat` (Odoo) en vez de una sesión SQLAlchemy."""
import math
from datetime import datetime
from decimal import Decimal

from . import almacenamiento as storage
from . import selector
from .precios import D, money, precio_venta, recargo_para
from .quote import Cotizacion, Linea

def _edad_horas(p, now):
    return (now - p.precio_en).total_seconds() / 3600 if p.precio_en else float("inf")


def linea_producto(cfg, cand, cantidad, now, grupo="equipos"):
    p = cand.p
    r = recargo_para(cfg, p.categoria, p.subcategoria, costo_item=D(p.costo))
    titulo = cand.specs.get("titulo") or p.nombre
    l = Linea(grupo=grupo, descripcion=f"{titulo} — {p.marca or ''} {p.sku}".strip(),
              cantidad=D(cantidad), unidad="u", precio_unit=precio_venta(cfg, D(p.costo), r),
              sku=p.sku, marca=p.marca, costo_unit=D(p.costo), recargo=r,
              stock_ciudad=cand.stock, motivo=cand.motivo)
    edad = _edad_horas(p, now)
    if edad > cfg.precio_max_horas:
        l.alertas.append(f"Precio con {edad:.0f} h de antigüedad (máx. {cfg.precio_max_horas:g} h): "
                         f"actualizar {p.sku} desde DigiCorp")
    return l


def linea_material(cfg, m, cantidad):
    r = recargo_para(cfg, m.categoria, costo_item=m.precio_item) if m.categoria else cfg.recargo_defecto
    return Linea(grupo="materiales", descripcion=m.descripcion, cantidad=cantidad, unidad=m.unidad,
                 precio_unit=precio_venta(cfg, m.costo_unit, r), sku=m.sku, costo_unit=money(m.costo_unit),
                 recargo=r, stock_ciudad=m.stock, alertas=list(m.alertas))


def consumo_w(cfg, specs):
    c = cfg.consumo_camara_w
    if specs.get("tipo") in ("PT", "PTZ") and specs["tipo"] in c:
        return c[specs["tipo"]]
    if specs.get("full_color") and "full_color" in c:
        return c["full_color"]
    return c.get("defecto", 6.5)


def armar_kit(cat, cfg, kit, ciudad, facturar=None, metros=None, km=0, titulo=None):
    ciudades = list(cfg.viaticos.por_ciudad) or [cfg.viaticos.ciudad_base]
    if ciudad not in ciudades:
        raise ValueError(f"Ciudad '{ciudad}' no válida. Opciones: {', '.join(ciudades)}")
    now = datetime.utcnow()
    q = Cotizacion(cfg=cfg, ciudad=ciudad,
                   facturar=cfg.facturar_por_defecto if facturar is None else facturar,
                   tipo_cambio=cat.tipo_cambio(), titulo=titulo or kit.get("nombre", ""))

    tecnologia = kit.get("tecnologia", "ip")
    gama = kit.get("gama", "estandar")
    if tecnologia not in ("ip", "analogica") or gama not in selector.GAMAS:
        raise ValueError(f"Kit con tecnologia '{tecnologia}' o gama '{gama}' no válida")
    analog = tecnologia == "analogica"

    # ---- cámaras
    n_cam, mp_max, watts, grupos_alm, no_poe = 0, 0.0, 0.0, [], 0
    for req in kit["camaras"]:
        e = selector.elegir_camara(cat, cfg, req, ciudad, tecnologia, gama)
        q.alertas += e.alertas
        if not e.cand:
            continue
        cant = int(req["cantidad"])
        q.lineas.append(linea_producto(cfg, e.cand, cant, now))
        mp = float(e.cand.specs.get("resolucion_mp", req.get("resolucion_min", 4)))
        n_cam += cant
        mp_max = max(mp_max, mp)
        grupos_alm.append(storage.GrupoCamaras(cant, mp))
        if not analog and e.cand.specs.get("poe"):
            watts += consumo_w(cfg, e.cand.specs) * cant
        else:
            no_poe += cant

    # ---- almacenamiento
    dias = int(kit.get("dias_grabacion", 15))
    codec, modo = kit.get("codec", "H.265"), kit.get("modo_grabacion") or "continua"
    disco_gb = float(kit["disco_gb"]) if kit.get("disco_gb") and grupos_alm else None   # disco pedido explícito
    if disco_gb:
        calc = storage.calcular_disco_fijo(cfg, grupos_alm, disco_gb / 1000,
                                           selector.etq_tb(disco_gb / 1000), codec, modo)
    else:
        calc = storage.calcular(cfg, grupos_alm, dias, codec, modo)
    q.almacenamiento = calc

    # ---- NVR (+ switch si hace falta)
    nvr_cfg = kit.get("nvr", {})
    canales = n_cam + int(nvr_cfg.get("canales_extra", 0))
    poe_cams = 0 if analog else n_cam - no_poe
    nvr = None
    if nvr_cfg.get("poe_integrado") and poe_cams:
        e = selector.elegir_nvr(cat, cfg, canales, mp_max, poe_cams, ciudad, calc.tb_requeridos, gama=gama)
        if e.cand and (e.cand.stock or 0) >= 1:
            nvr = e
    poe_en_nvr = nvr is not None
    if nvr is None:
        nvr = selector.elegir_nvr(cat, cfg, canales, mp_max, 0, ciudad, calc.tb_requeridos,
                                  analogico=analog, gama=gama)
        if nvr_cfg.get("poe_integrado") and poe_cams:
            q.alertas.append("Sin NVR con PoE integrado y stock: se usa NVR sin PoE + switch PoE")
    q.alertas += nvr.alertas
    bahias, max_tb = 1, None
    if nvr.cand:
        q.lineas.append(linea_producto(cfg, nvr.cand, 1, now))
        bahias = int(nvr.cand.specs.get("hdd_bahias", 1))
        max_tb = nvr.cand.specs.get("hdd_max_tb")
        if nvr.cand.specs.get("canales", 0) < canales:
            q.alertas.append(f"NVR con {nvr.cand.specs.get('canales')} canales < {canales} requeridos")
    if poe_en_nvr:
        q.notas.append(f"Consumo PoE estimado {watts:.0f} W: verificar presupuesto PoE del NVR "
                       f"{nvr.cand.p.sku if nvr.cand else ''}")
    elif poe_cams:
        sw = selector.elegir_switch(cat, cfg, poe_cams, watts * 1.2, ciudad)   # 20 % de holgura
        q.alertas += sw.alertas
        if sw.cand:
            q.lineas.append(linea_producto(cfg, sw.cand, 1, now))

    # ---- discos
    if calc.tb_requeridos > 0:
        if max_tb and calc.tb_requeridos > bahias * max_tb:
            q.alertas.append(f"El NVR admite {bahias} × {max_tb} TB = {bahias * max_tb} TB "
                             f"< {calc.tb_requeridos} TB requeridos: reducir días o cambiar NVR")
        if disco_gb:
            d = selector.elegir_disco_fijo(cat, cfg, disco_gb / 1000, max_tb, ciudad,
                                           permitir_pull=bool(kit.get("disco_pull")))
        else:
            d = selector.elegir_discos(cat, cfg, calc.tb_requeridos, bahias, max_tb, ciudad,
                                       permitir_pull=bool(kit.get("disco_pull")))
        q.alertas += d.alertas
        if d.cand:
            q.lineas.append(linea_producto(cfg, d.cand, d.cantidad, now))
            cap = (d.cand.specs.get("capacidad_tb") or 0) * d.cantidad
            if not disco_gb:
                calc.lineas.insert(-1, f"Disco elegido: {d.cand.motivo.split('|')[0].strip()} → "
                                       f"≈ {dias * cap / max(calc.tb_requeridos, 0.01):.0f} días de grabación")
            else:
                if abs(cap - disco_gb / 1000) > 0.01:        # no había el pedido: días con el disco real
                    calc = q.almacenamiento = storage.calcular_disco_fijo(
                        cfg, grupos_alm, cap, selector.etq_tb(cap), codec, modo)
                if calc.dias < 7:
                    otro = calc.dias_por_modo.get("movimiento", 0)
                    q.alertas.append(
                        f"Con disco de {selector.etq_tb(cap)} solo se graban ≈ {calc.dias} días "
                        f"{'por movimiento' if modo == 'movimiento' else 'en grabación continua'}"
                        + (f" (≈ {otro:.0f} por movimiento)" if modo != "movimiento" else "")
                        + ": ofrecer disco mayor o grabación por movimiento")

    # ---- materiales
    metros_tot = Decimal(str(metros)) if metros is not None else D(n_cam * kit.get("cable_m_por_camara", 25))
    mats = kit.get("materiales", {})
    cantidades = {}
    for k, f in mats.get("por_camara", {}).items():
        cantidades[k] = cantidades.get(k, Decimal(0)) + D(f) * n_cam
    for k, f in mats.get("por_metro", {}).items():
        cantidades[k] = cantidades.get(k, Decimal(0)) + D(f) * metros_tot
    for k, f in mats.get("fijos", {}).items():
        cantidades[k] = cantidades.get(k, Decimal(0)) + D(f)
    if no_poe:
        cantidades["fuente_12v"] = cantidades.get("fuente_12v", Decimal(0)) + no_poe
    for k, cant in cantidades.items():
        if cant <= 0:
            continue
        m = selector.elegir_material(cat, cfg, k, ciudad, D(math.ceil(cant)))
        if m is None:
            q.notas.append(f"Se omitió '{cfg.materiales[k].descripcion}' ({math.ceil(cant)} u): sin stock en {ciudad}")
            continue
        q.lineas.append(linea_material(cfg, m, D(math.ceil(cant))))

    # ---- mano de obra
    for k, v in kit.get("mano_obra", {}).items():
        t = cfg.mano_obra[k]
        cant = D(n_cam) if v == "por_camara" else metros_tot if v == "por_metro" else D(v)
        if k == "config_switch" and (poe_en_nvr or analog):
            continue
        if cant > 0:
            q.lineas.append(Linea("mano_obra", t.descripcion, cant, t.unidad, t.precio))

    # ---- viáticos
    v = cfg.viaticos
    monto = v.por_ciudad.get(ciudad, Decimal(0)) + v.por_km * D(km)
    if monto > 0:
        q.lineas.append(Linea("viaticos", v.descripcion + (f" ({km:g} km)" if km else ""), D(1), "glb", money(monto)))

    if analog:
        q.notas.append("Analógico: cámaras alimentadas con fuente 12 V por punto; video por UTP con balun. "
                       "Verificar si el balun DigiCorp se vende por unidad o por par.")
    q.notas.append(f"Cálculo de almacenamiento (estimación):\n{calc.texto()}")
    return q
