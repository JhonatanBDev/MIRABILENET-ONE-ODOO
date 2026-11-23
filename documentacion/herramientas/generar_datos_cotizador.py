"""Convierte los kits, materiales, mano de obra y viáticos del Cotizador DigiCorp
(referencia/config/*.yaml) en datos XML para mirabilenet_cotizador.

NO toca los recargos (márgenes de ganancia): esos no van al repositorio. Para cargar los
reales en una base, use cargar_margenes_cotizador.py.

Uso (con PyYAML instalado en el entorno):
  env\\Scripts\\python.exe documentacion\\herramientas\\generar_datos_cotizador.py
"""
import os
from xml.sax.saxutils import escape

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG = os.path.join(ROOT, "referencia", "config")
OUT = os.path.join(ROOT, "custom_addons", "mirabilenet_cotizador", "data")


def field(name, value, kind=None):
    if kind == "eval":
        return '        <field name="%s" eval="%s"/>\n' % (name, escape(value, {'"': "&quot;"}))
    return '        <field name="%s">%s</field>\n' % (name, escape(str(value)))


def main():
    with open(os.path.join(CONFIG, "pricing.yaml"), encoding="utf-8") as f:
        pricing = yaml.safe_load(f)
    with open(os.path.join(CONFIG, "kits.yaml"), encoding="utf-8") as f:
        kits = yaml.safe_load(f)
    out = ['<?xml version="1.0" encoding="utf-8"?>\n',
           "<!-- Generado con documentacion/herramientas/generar_datos_cotizador.py desde\n"
           "     referencia/config. Las tarifas de mano de obra y los viáticos son de ejemplo:\n"
           "     cámbielos en MIRABILENET > Cotizaciones > Configuración. -->\n",
           '<odoo noupdate="1">\n']
    for code, t in pricing.get("mano_obra", {}).items():
        out.append('    <record id="tariff_%s" model="mirabilenet.cot.tariff">\n' % code)
        out += [field("code", code), field("name", t["descripcion"]),
                field("price", t["precio"]), field("unit", t["unidad"])]
        out.append("    </record>\n")
    viaticos = pricing.get("viaticos", {})
    for i, (city, amount) in enumerate(viaticos.get("por_ciudad", {}).items()):
        xmlid = "city_" + city.lower().replace(" ", "_")
        out.append('    <record id="%s" model="mirabilenet.cot.city">\n' % xmlid)
        out += [field("name", city), field("viatico", amount), field("sequence", i * 10),
                field("is_base", "True" if city == viaticos.get("ciudad_base") else "False",
                      "eval")]
        out.append("    </record>\n")
    for code, m in pricing.get("materiales", {}).items():
        out.append('    <record id="material_%s" model="mirabilenet.cot.material">\n' % code)
        out += [field("code", code), field("name", m["descripcion"]),
                field("unit", m.get("unidad", "u")),
                field("purchase_unit", m.get("unidad_compra", 1)),
                field("price_ref", m["precio_ref"]),
                field("optional", "True" if m.get("opcional") else "False", "eval")]
        buscar = m.get("buscar") or {}
        if buscar:
            out += [field("category", buscar["categoria"]),
                    field("words", ", ".join(buscar.get("palabras") or []))]
            if buscar.get("excluir"):
                out.append(field("exclude", buscar["excluir"]))
        if m.get("sku"):
            out.append(field("sku", m["sku"]))
        out.append("    </record>\n")
    for i, (code, kit) in enumerate(kits.items()):
        definition = {k: v for k, v in kit.items() if k != "nombre"}
        out.append('    <record id="kit_%s" model="mirabilenet.cot.kit">\n' % code)
        out += [field("code", code), field("name", kit["nombre"]), field("sequence", i * 10),
                field("definition", repr(definition), "eval")]
        out.append("    </record>\n")
    out.append("</odoo>\n")
    path = os.path.join(OUT, "mirabilenet_cotizador_data.xml")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(out))
    print("Datos escritos en", path)


if __name__ == "__main__":
    main()
