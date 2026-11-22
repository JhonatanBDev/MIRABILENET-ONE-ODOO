"""SiatSoapClient: cliente SOAP con timeouts, TLS y parseo uniforme de errores.

Es la única pieza que conoce sobres SOAP y namespaces. El token delegado viaja
solo en la cabecera HTTP y nunca se registra.
"""

import re
import time

import requests
from lxml import etree

from . import constants, errors

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"

# Valores que no deben quedar en claro en la evidencia técnica.
_REDACT = re.compile(r"<(cuis|cufd|cufdEvento)>([^<]*)</\1>")
_ARCHIVO = re.compile(r"<archivo>[^<]*</archivo>")


def redact(xml_text):
    """Enmascara CUIS/CUFD y reemplaza el archivo binario por un marcador."""
    def _mask(match):
        value = match.group(2)
        return "<%s>***%s</%s>" % (match.group(1), value[-4:], match.group(1))
    xml_text = _REDACT.sub(_mask, xml_text or "")
    return _ARCHIVO.sub("<archivo>[omitido]</archivo>", xml_text)


def _to_python(node):
    children = list(node)
    if not children:
        return (node.text or "").strip()
    data = {}
    for child in children:
        tag = etree.QName(child).localname
        value = _to_python(child)
        if tag in data:
            if not isinstance(data[tag], list):
                data[tag] = [data[tag]]
            data[tag].append(value)
        else:
            data[tag] = value
    return data


def as_list(value):
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


class SiatSoapClient:
    def __init__(self, base_url, token, connect_timeout=5.0, read_timeout=30.0,
                 on_exchange=None, session=None):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = (connect_timeout, read_timeout)
        self.on_exchange = on_exchange
        self.session = session or requests.Session()

    def _envelope(self, operation, wrapper, params):
        env = etree.Element("{%s}Envelope" % SOAP_ENV, nsmap={"soapenv": SOAP_ENV})
        etree.SubElement(env, "{%s}Header" % SOAP_ENV)
        body = etree.SubElement(env, "{%s}Body" % SOAP_ENV)
        op = etree.SubElement(
            body, "{%s}%s" % (constants.SOAP_NAMESPACE, operation),
            nsmap={"siat": constants.SOAP_NAMESPACE})
        parent = etree.SubElement(op, wrapper) if wrapper else op
        for key, value in params.items():
            if value is None:
                continue
            etree.SubElement(parent, key).text = str(value)
        return etree.tostring(env, xml_declaration=True, encoding="UTF-8")

    def call(self, service, operation, wrapper, params):
        """Invoca una operación y devuelve el contenido de la respuesta como dict."""
        url = "%s/%s" % (self.base_url, service)
        request_xml = self._envelope(operation, wrapper, params)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "",
            "apikey": "TokenApi %s" % self._token,
        }
        started = time.monotonic()
        response_text = ""
        error = None
        try:
            try:
                resp = self.session.post(
                    url, data=request_xml, headers=headers, timeout=self.timeout)
            except requests.exceptions.RequestException as exc:
                raise errors.SiatCommunicationError(
                    "Sin respuesta del SIN (%s)." % type(exc).__name__)
            response_text = resp.text
            if resp.status_code in (401, 403):
                raise errors.SiatError(
                    errors.TOKEN, "El SIN rechazó el token delegado (HTTP %s)."
                    % resp.status_code)
            if resp.status_code >= 500 and "Fault" not in response_text:
                raise errors.SiatCommunicationError(
                    "El servicio del SIN respondió HTTP %s." % resp.status_code)
            return self._parse(resp.content)
        except errors.SiatError as exc:
            error = exc
            raise
        finally:
            if self.on_exchange:
                self.on_exchange({
                    "service": service,
                    "operation": operation,
                    "request_xml": redact(request_xml.decode("utf-8")),
                    "response_xml": redact(response_text),
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "success": error is None,
                    "error_code": error.code if error else False,
                })

    def _parse(self, content):
        try:
            root = etree.fromstring(content)
        except etree.XMLSyntaxError:
            raise errors.SiatCommunicationError("Respuesta del SIN ilegible.")
        body = root.find("{%s}Body" % SOAP_ENV)
        if body is None or not len(body):
            raise errors.SiatCommunicationError("Respuesta SOAP sin cuerpo.")
        first = body[0]
        if etree.QName(first).localname == "Fault":
            fault = _to_python(first)
            text = fault.get("faultstring") if isinstance(fault, dict) else str(fault)
            raise errors.SiatError(errors.REJECTED, "Fault SOAP del SIN: %s" % text)
        data = _to_python(first)
        if isinstance(data, dict) and len(data) == 1:
            inner = next(iter(data.values()))
            if isinstance(inner, dict):
                return inner
        return data if isinstance(data, dict) else {}
