"""XsdValidator: validación local contra el XSD oficial antes de enviar."""

from lxml import etree

from . import errors


def validate(xml_bytes, xsd_bytes):
    """Lanza SiatXsdError con el detalle (línea y regla) si el XML no cumple."""
    try:
        schema = etree.XMLSchema(etree.fromstring(xsd_bytes))
    except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise errors.SiatXsdError(["El XSD cargado no es válido: %s" % exc])
    try:
        doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise errors.SiatXsdError(["XML mal formado: %s" % exc])
    if not schema.validate(doc):
        raise errors.SiatXsdError(
            ["Línea %s: %s" % (e.line, e.message) for e in schema.error_log])
    return True
