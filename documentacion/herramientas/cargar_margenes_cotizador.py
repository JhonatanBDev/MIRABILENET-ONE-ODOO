"""Carga en una base los recargos REALES (márgenes) y los parámetros de precio del Cotizador
DigiCorp, desde referencia/config/pricing.yaml (que no va al repositorio).

Este archivo no tiene ningún margen: solo los lee del YAML. Uso, desde la carpeta odoo:
  env\\Scripts\\python.exe odoo-bin shell -c odoo.conf -d <base> --no-http < documentacion\\herramientas\\cargar_margenes_cotizador.py
"""
import os

import yaml

PATH = os.path.join("referencia", "config", "pricing.yaml")
PARAM = "mirabilenet_cotizador."

with open(PATH, encoding="utf-8") as f:
    pricing = yaml.safe_load(f)

env = env(user=env.ref("base.user_root"))  # noqa: F821 (env lo pone odoo-bin shell)
Param = env["ir.config_parameter"]
recargo = pricing.get("recargo", {})
params = {
    "recargo_defecto": recargo.get("defecto"),
    "recargo_maximo": recargo.get("maximo"),
    "recargo_maximo_bajo": recargo.get("maximo_bajo_costo"),
    "iva": pricing.get("impuestos", {}).get("iva"),
    "it": pricing.get("impuestos", {}).get("it"),
    "modo_impuestos": pricing.get("impuestos", {}).get("modo"),
    "facturar_por_defecto": "1" if pricing.get("impuestos", {}).get(
        "facturar_por_defecto", True) else "0",
    "vigencia_dias": pricing.get("vigencia_dias"),
    "redondeo_multiplo": pricing.get("redondeo", {}).get("multiplo"),
    "redondeo_umbral_bajo": pricing.get("redondeo", {}).get("umbral_bajo"),
    "redondeo_multiplo_bajo": pricing.get("redondeo", {}).get("multiplo_bajo"),
    "redondeo_total": pricing.get("redondeo", {}).get("total_multiplo"),
    "precio_max_horas": pricing.get("precio_max_horas"),
    "marcas_preferidas": ", ".join(pricing.get("marcas_preferidas") or []),
    "bonus_marca_preferida": pricing.get("bonus_marca_preferida"),
    "tipo_cambio_manual": pricing.get("tipo_cambio", {}).get("manual_valor"),
    "viaticos_por_km": pricing.get("viaticos", {}).get("por_km"),
}
for key, value in params.items():
    if value not in (None, ""):
        Param.set_param(PARAM + key, str(value))

Markup = env["mirabilenet.cot.markup"].with_context(active_test=False)
Markup.search([]).unlink()
for category, value in (recargo.get("por_categoria") or {}).items():
    Markup.create({"kind": "categoria", "category": category, "markup": float(value) * 100})
for step in recargo.get("por_costo") or []:
    Markup.create({"kind": "costo", "below": float(step["hasta"]),
                   "markup": float(step["recargo"]) * 100})
env.cr.commit()
print("RESULTADO recargos cargados:", Markup.search_count([]), "| parámetros:",
      sum(1 for v in params.values() if v not in (None, "")))
