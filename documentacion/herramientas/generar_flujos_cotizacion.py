"""Agrega a los flujos de n8n «17 Ventas» y «15 Soporte» las herramientas del cotizador de
cámaras y redes: consultar kits, buscar equipos y enviar la cotización. Copia un nodo de
herramienta que ya existe, así usan la misma credencial («MIRABILENET API») por id.

Es idempotente: si el flujo ya tiene las herramientas, las reemplaza.

Uso:
  env\\Scripts\\python.exe documentacion\\herramientas\\generar_flujos_cotizacion.py <carpeta de flujos exportados> <carpeta de salida> [url base de Odoo]
"""
import copy
import json
import os
import sys

FLOWS = {"Vnt17PrspctMrblN": "17", "Kge2vCbS05k6Tpd5": "15"}
MARK = "Cámaras de seguridad y redes"

RULE = (
    "{n}. " + MARK + ": además de internet, la empresa vende e instala cámaras de seguridad "
    "(CCTV) y equipos de red. Si la persona pregunta por cámaras, vigilancia, alarmas, DVR o "
    "NVR, o equipos de red, o si viene al caso, cuéntaselo en una línea. Para ofrecer, consulta "
    "primero la herramienta de kits (o la de equipos, si pide un equipo suelto) y habla solo de "
    "lo que devuelva. Para cotizar necesitas: cuántas cámaras o qué kit, su ciudad y su nombre; "
    "pregunta lo que falte, de a una cosa. Con eso usa la herramienta de enviar cotización: el "
    "sistema arma la cotización y le manda el PDF por este chat. Si responde «enviada» en "
    "verdadero, dile que ya le llegó el PDF con el total y hasta cuándo vale, tal como vienen. "
    "Si responde «requiere_asesor», dile que un asesor la revisa y se la envía; no des ningún "
    "monto. Nunca calcules ni estimes un precio tú: los precios solo salen de las herramientas. "
    "No prometas fecha de instalación ni descuentos."
)


def tool(base, node_id, name, position, description, path, odoo, method="GET", body=None,
         query=None):
    node = copy.deepcopy(base)
    node.update(id=node_id, name=name, position=position)
    params = {
        "toolDescription": description,
        "method": method,
        "url": "=%s/api/v1/messaging/n8n/conversations/"
               "{{ $('Al ser llamado').first().json.conversacion_id }}/%s" % (odoo, path),
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "options": {"timeout": 20000},
    }
    if query:
        params["sendQuery"] = True
        params["queryParameters"] = {"parameters": [
            {"name": k, "value": "={{ $fromAI('%s', '%s', 'string') }}" % (k, d)}
            for k, d in query]}
    if body:
        params["sendBody"] = True
        params["specifyBody"] = "keypair"
        params["bodyParameters"] = {"parameters": [
            {"name": k, "value": v if v.startswith("=") else
             "={{ $fromAI('%s', '%s', 'string') }}" % (k, v)} for k, v in body]}
        # Un 4xx (falta el nombre, kit desconocido…) vuelve al agente como dato, no como falla.
        params["options"]["response"] = {"response": {"neverError": True}}
    node["parameters"] = params
    return node


def patch(flow, number, odoo):
    base = next(n for n in flow["nodes"] if n["type"].endswith("httpRequestTool"))
    agent = next(n for n in flow["nodes"] if n["type"].endswith(".agent"))
    prefix = "c%s00000-0000-4000-8000-0000000000" % number
    x0 = max(n["position"][0] for n in flow["nodes"] if n["type"].endswith("httpRequestTool"))
    y = 460
    new = [
        tool(base, prefix + "71", "Consultar kits de cámaras", [x0 + 160, y],
             "Devuelve los kits de cámaras de seguridad que se pueden cotizar (código, nombre, "
             "cantidad de cámaras, tecnología, gama y días de grabación) y las ciudades donde se "
             "cotiza. No trae precios: el precio sale al enviar la cotización. Úsala antes de "
             "ofrecer cámaras. No recibe parámetros.", "kits", odoo),
        tool(base, prefix + "72", "Buscar equipos", [x0 + 320, y],
             "Busca equipos sueltos de cámaras y redes (cámaras, grabadores, discos, switches, "
             "routers) y devuelve nombre, marca, precio de venta, precio con factura y si hay en "
             "la ciudad. Úsala solo si la persona pide un equipo en particular.", "products",
             odoo, query=[("buscar", "Palabras del equipo que busca, por ejemplo: camara domo"),
                          ("ciudad", "Ciudad de la persona; vacío si no la dijo")]),
        tool(base, prefix + "73", "Enviar cotización", [x0 + 480, y],
             "Arma la cotización con los precios del sistema y le envía el PDF a la persona por "
             "este chat. Úsala solo cuando ya sepas qué quiere (un kit de la lista, o su pedido "
             "con cantidad de cámaras), su ciudad y su nombre. Responde «enviada»: si es "
             "verdadero trae numero, total, moneda y valida_hasta; si es falso con codigo "
             "«requiere_asesor», un asesor la revisará y no hay que decir montos. Cualquier otro "
             "codigo es un dato que falta o un error: léele el detalle.", "quotation", odoo,
             method="POST", body=[
                 ("kit", "Código de un kit de la lista de kits; vacío si no calza ninguno"),
                 ("pedido", "Lo que pidió la persona con sus palabras: cuántas cámaras, para "
                            "dónde, cuántos días de grabación"),
                 ("ciudad", "Ciudad de la persona, de la lista de ciudades"),
                 ("nombre", "Nombre y apellido tal como los escribió la persona"),
                 ("mensaje_id", "={{ $('Al ser llamado').first().json.mensaje_id || "
                                "$execution.id }}")]),
    ]
    names = {n["name"] for n in new}
    flow["nodes"] = [n for n in flow["nodes"] if n["name"] not in names] + new
    for node in new:
        flow["connections"][node["name"]] = {"ai_tool": [[
            {"node": agent["name"], "type": "ai_tool", "index": 0}]]}

    # La regla nueva va al final de las reglas, antes del estilo que pide la empresa.
    options = agent["parameters"]["options"]
    text = options["systemMessage"]
    cut = text.index("\n\nEstilo que pide la empresa")
    rules = text[:cut]
    if MARK in rules:
        rules = rules[:rules.rindex("\n", 0, rules.index(MARK))]
    last = max(int(line.split(".", 1)[0]) for line in rules.split("\n")
               if line.split(".", 1)[0].isdigit())
    options["systemMessage"] = rules + "\n" + RULE.format(n=last + 1) + text[cut:]
    # Cotizar lleva más pasos: consultar kits, preguntar y enviar.
    options["maxIterations"] = max(int(options.get("maxIterations") or 0), 8)
    return flow


def main(folder, out, odoo="http://host.docker.internal:8069"):
    os.makedirs(out, exist_ok=True)
    for flow_id, number in FLOWS.items():
        with open(os.path.join(folder, flow_id + ".json"), encoding="utf-8") as f:
            flow = json.load(f)
        flow = patch(flow, number, odoo)
        with open(os.path.join(out, flow_id + ".json"), "w", encoding="utf-8") as f:
            json.dump(flow, f, ensure_ascii=False, indent=2)
        print("Flujo %s escrito con %d nodos" % (flow["name"], len(flow["nodes"])))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
