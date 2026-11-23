"""Arma el flujo de n8n «MIRABILENET · 20 Personal» a partir de los nodos de los flujos 10
(webhook firmado) y 15 (modelo Gemini y llamada a la API), para que use las mismas
credenciales por id.

Uso:
  env\\Scripts\\python.exe documentacion\\herramientas\\generar_flujo_20_personal.py <carpeta de flujos exportados> <salida.json> [url base de Odoo]

La url base de Odoo por defecto es http://host.docker.internal:8069 (n8n local en Docker).
"""
import copy
import json
import os
import sys

FLOW_ID = "Prsnl20MrblNtWA"


def load(folder, flow_id):
    with open(os.path.join(folder, flow_id + ".json"), encoding="utf-8") as f:
        return json.load(f)


def node(flow, prefix):
    for n in flow["nodes"]:
        if n["name"].startswith(prefix):
            return copy.deepcopy(n)
    raise KeyError(prefix)


def main(folder, out, odoo="http://host.docker.internal:8069"):
    entrada = load(folder, "e4NcNjnvbsgbNNah")
    soporte = load(folder, "Kge2vCbS05k6Tpd5")

    webhook = node(entrada, "Recibir evento")
    webhook.update(name="Recibir mensaje del personal", position=[0, 0],
                   id="p20-webhook", webhookId="p20-mirabilenet-personal")
    webhook["parameters"]["path"] = "mirabilenet-personal"

    hash_node = node(entrada, "Hash del cuerpo")
    hash_node.update(name="Hash del cuerpo recibido", position=[220, 0], id="p20-hash")
    check = node(entrada, "¿El cuerpo coincide")
    check.update(name="¿El cuerpo coincide con la firma?", position=[440, 0], id="p20-if")
    accept = node(entrada, "Aceptar evento")
    accept.update(name="Aceptar mensaje", position=[660, -120], id="p20-ok")
    reject = node(entrada, "Rechazar cuerpo")
    reject.update(name="Rechazar cuerpo alterado", position=[660, 120], id="p20-reject")

    model = node(soporte, "Modelo Gemini")
    model.update(name="Modelo Gemini", position=[880, 160], id="p20-model")
    # El del flujo 15 toma el modelo de su disparador; aquí va fijo.
    model["parameters"]["modelName"] = "models/gemini-flash-lite-latest"

    prompt = (
        "=Eres el asistente de operaciones de MIRABILENET (internet por fibra). Un técnico o "
        "alguien del personal escribió por WhatsApp. Decide qué quiso decir: algo sobre sus "
        "averías, o que le cotices equipos de cámaras o redes para un cliente.\n\n"
        "Persona: {{ $('Recibir mensaje del personal').item.json.body.persona.nombre }} "
        "(rol {{ $('Recibir mensaje del personal').item.json.body.persona.rol }})\n"
        "Mensaje: {{ $('Recibir mensaje del personal').item.json.body.texto }}\n"
        "Averías abiertas (la primera es la más reciente): "
        "{{ JSON.stringify($('Recibir mensaje del personal').item.json.body.averias_abiertas) }}\n\n"
        "Kits que se pueden cotizar (usa su código): "
        "{{ JSON.stringify($('Recibir mensaje del personal').item.json.body.kits || []) }}\n"
        "Ciudades: "
        "{{ JSON.stringify($('Recibir mensaje del personal').item.json.body.ciudades || []) }}\n\n"
        "Responde SOLO un JSON, sin texto alrededor, con estas claves:\n"
        "{\"accion\": \"arreglado\" | \"no_resuelto\" | \"en_camino\" | \"nota\" | \"cotizar\" | "
        "\"ninguna\", \"averia_id\": número o null, \"nota\": texto corto o \"\", "
        "\"kit\": código de un kit de la lista o \"\", \"pedido\": lo que pidió cotizar con sus "
        "palabras o \"\", \"ciudad\": una ciudad de la lista o \"\", \"cliente_nombre\": nombre "
        "del cliente o \"\", \"cliente_telefono\": teléfono del cliente o \"\", \"con_factura\": "
        "true, false o null, \"respuesta\": texto breve y amable en español para la persona}\n"
        "Reglas: «no_resuelto» necesita la nota del motivo. Si no menciona cuál avería, usa la "
        "primera. Si pide cotizar (cotiza, cotización, presupuesto, precio de cámaras o de un "
        "kit), accion=\"cotizar\": elige el kit de la lista que mejor calce o, si ninguno "
        "calza, deja kit vacío y copia el pedido en «pedido»; no inventes precios ni productos, "
        "y deja «respuesta» vacía porque el sistema contesta con la cotización. Si no habla de "
        "una avería ni de cotizar, accion=\"ninguna\" y responde qué puede hacer.")
    chain = {
        "parameters": {"promptType": "define", "text": prompt, "batching": {}},
        "type": "@n8n/n8n-nodes-langchain.chainLlm", "typeVersion": 1.7,
        "position": [880, -120], "id": "p20-chain", "name": "Interpretar el mensaje",
    }
    parse = {
        "parameters": {"jsCode": (
            "const raw = ($input.first().json.text || '').trim();\n"
            "const m = raw.match(/\\{[\\s\\S]*\\}/);\n"
            "let d = {};\n"
            "try { d = m ? JSON.parse(m[0]) : {}; } catch (e) { d = {}; }\n"
            "const ok = ['arreglado', 'no_resuelto', 'en_camino', 'nota', 'cotizar', 'ninguna'];\n"
            "const txt = (v, n) => (typeof v === 'string' ? v.slice(0, n) : '');\n"
            "const body = $('Recibir mensaje del personal').first().json.body;\n"
            "return [{ json: {\n"
            "  mensaje_id: body.mensaje_id,\n"
            "  accion: ok.includes(d.accion) ? d.accion : 'ninguna',\n"
            "  averia_id: Number.isInteger(d.averia_id) ? d.averia_id : null,\n"
            "  nota: typeof d.nota === 'string' ? d.nota.slice(0, 1000) : '',\n"
            "  kit: txt(d.kit, 60), pedido: txt(d.pedido, 600), ciudad: txt(d.ciudad, 60),\n"
            "  cliente_nombre: txt(d.cliente_nombre, 120),\n"
            "  cliente_telefono: txt(String(d.cliente_telefono || ''), 30),\n"
            "  con_factura: typeof d.con_factura === 'boolean' ? d.con_factura : null,\n"
            "  respuesta: d.accion === 'cotizar' ? '' : txt(d.respuesta, 900)\n"
            "} }];")},
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1100, -120],
        "id": "p20-parse", "name": "Ordenar la decisión",
    }
    send = node(soporte, "Avisar a Django que se agot")
    send.update(name="Avisar a Odoo", position=[1320, -120], id="p20-send")
    send["parameters"]["url"] = odoo + "/api/v1/messaging/n8n/personal/resultado"
    send["parameters"]["sendBody"] = True
    send["parameters"]["specifyBody"] = "json"
    send["parameters"]["jsonBody"] = "={{ JSON.stringify($json) }}"
    send["parameters"].pop("bodyParameters", None)
    send["parameters"].pop("contentType", None)

    flow = {
        "id": FLOW_ID,
        "name": "MIRABILENET · 20 Personal: respuestas de técnicos",
        "active": True,
        "nodes": [webhook, hash_node, check, accept, reject, model, chain, parse, send],
        "connections": {
            webhook["name"]: {"main": [[{"node": hash_node["name"], "type": "main", "index": 0}]]},
            hash_node["name"]: {"main": [[{"node": check["name"], "type": "main", "index": 0}]]},
            check["name"]: {"main": [
                [{"node": accept["name"], "type": "main", "index": 0}],
                [{"node": reject["name"], "type": "main", "index": 0}]]},
            accept["name"]: {"main": [[{"node": chain["name"], "type": "main", "index": 0}]]},
            model["name"]: {"ai_languageModel": [[{"node": chain["name"],
                                                   "type": "ai_languageModel", "index": 0}]]},
            chain["name"]: {"main": [[{"node": parse["name"], "type": "main", "index": 0}]]},
            parse["name"]: {"main": [[{"node": send["name"], "type": "main", "index": 0}]]},
        },
        "settings": copy.deepcopy(entrada.get("settings") or {"executionOrder": "v1"}),
        "pinData": {},
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(flow, f, ensure_ascii=False, indent=2)
    print("Flujo escrito en", out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
