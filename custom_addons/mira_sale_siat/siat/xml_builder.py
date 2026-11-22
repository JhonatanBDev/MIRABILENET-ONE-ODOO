"""XmlBuilder: serialización por documento sector.

Cada sector registra su constructor con `@register_sector`. El orden de los
elementos sigue exactamente la secuencia del XSD oficial (data/xsd/).

El constructor recibe el "contrato interno de emisión" ya resuelto (dict con
cadenas y Decimal), nunca registros del ORM.
"""

from lxml import etree

from . import constants
from .amounts import fmt

XSI = "http://www.w3.org/2001/XMLSchema-instance"

_BUILDERS = {}

# sector -> nombre del elemento raíz por modalidad
_ROOTS = {
    constants.SECTOR_COMPRA_VENTA: {
        constants.MODALITY_COMPUTERIZED: "facturaComputarizadaCompraVenta",
        constants.MODALITY_ELECTRONIC: "facturaElectronicaCompraVenta",
    },
    constants.SECTOR_TELECOM: {
        constants.MODALITY_COMPUTERIZED: "facturaComputarizadaTelecomunicacion",
        constants.MODALITY_ELECTRONIC: "facturaElectronicaTelecomunicacion",
    },
    constants.SECTOR_CREDIT_DEBIT_NOTE: {
        constants.MODALITY_COMPUTERIZED: "notaFiscalComputarizadaCreditoDebito",
        constants.MODALITY_ELECTRONIC: "notaFiscalElectronicaCreditoDebito",
    },
}

# El XSD de cada raíz se publica con este nombre de archivo.
_SCHEMA_FILES = {
    "notaFiscalComputarizadaCreditoDebito": "notaComputarizadaCreditoDebito.xsd",
    "notaFiscalElectronicaCreditoDebito": "notaElectronicaCreditoDebito.xsd",
}


def register_sector(sector_code):
    def decorator(func):
        _BUILDERS[sector_code] = func
        return func
    return decorator


def build_xml(document, modality):
    """Devuelve el XML (bytes, UTF-8) del documento fiscal."""
    sector = document["sector_code"]
    if sector not in _BUILDERS:
        raise ValueError("Documento sector %s no habilitado en este sistema." % sector)
    if modality not in _ROOTS[sector]:
        raise ValueError("Modalidad desconocida: %r" % modality)
    root = _root(_ROOTS[sector][modality])
    _BUILDERS[sector](root, document)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _add(parent, tag, value):
    """Agrega un elemento; None se serializa como xsi:nil="true"."""
    node = etree.SubElement(parent, tag)
    if value is None or value == "":
        node.set("{%s}nil" % XSI, "true")
    else:
        node.text = str(value)
    return node


def _root(name):
    root = etree.Element(name, nsmap={"xsi": XSI})
    root.set("{%s}noNamespaceSchemaLocation" % XSI,
             _SCHEMA_FILES.get(name, name + ".xsd"))
    return root


def _money_or_nil(value):
    return None if value is None else fmt(value)


def _issuer(cab, doc, with_joint_nit=False):
    _add(cab, "nitEmisor", doc["issuer_nit"])
    _add(cab, "razonSocialEmisor", doc["issuer_name"])
    _add(cab, "municipio", doc["municipality"])
    _add(cab, "telefono", doc.get("phone"))
    if with_joint_nit:
        _add(cab, "nitConjunto", doc.get("joint_nit"))


def _place_and_customer(cab, doc):
    _add(cab, "cuf", doc["cuf"])
    _add(cab, "cufd", doc["cufd"])
    _add(cab, "codigoSucursal", doc["branch_code"])
    _add(cab, "direccion", doc["address"])
    _add(cab, "codigoPuntoVenta", doc["pos_code"])
    _add(cab, "fechaEmision", doc["emission_iso"])
    _add(cab, "nombreRazonSocial", doc["customer_name"])
    _add(cab, "codigoTipoDocumentoIdentidad", doc["customer_doc_type"])
    _add(cab, "numeroDocumento", doc["customer_doc_number"])
    _add(cab, "complemento", doc.get("customer_complement"))
    _add(cab, "codigoCliente", doc["customer_code"])


def _line(det, line):
    _add(det, "actividadEconomica", line["activity_code"])
    _add(det, "codigoProductoSin", line["siat_product_code"])
    _add(det, "codigoProducto", line["product_code"])
    _add(det, "descripcion", line["description"])
    _add(det, "cantidad", fmt(line["quantity"]))
    _add(det, "unidadMedida", line["unit_code"])
    _add(det, "precioUnitario", fmt(line["unit_price"]))
    _add(det, "montoDescuento", _money_or_nil(line.get("discount")))
    _add(det, "subTotal", fmt(line["subtotal"]))


def _invoice(root, doc, sector, with_joint_nit=False):
    """Estructura común a Compra y Venta y a Telecomunicaciones."""
    cab = etree.SubElement(root, "cabecera")
    _issuer(cab, doc, with_joint_nit)
    _add(cab, "numeroFactura", doc["number"])
    _place_and_customer(cab, doc)
    _add(cab, "codigoMetodoPago", doc["payment_method_code"])
    _add(cab, "numeroTarjeta", doc.get("card_number"))
    _add(cab, "montoTotal", fmt(doc["amount_total"]))
    _add(cab, "montoTotalSujetoIva", fmt(doc["amount_subject_to_vat"]))
    _add(cab, "codigoMoneda", doc["currency_code"])
    _add(cab, "tipoCambio", fmt(doc["exchange_rate"]))
    _add(cab, "montoTotalMoneda", fmt(doc["amount_total_currency"]))
    _add(cab, "montoGiftCard", _money_or_nil(doc.get("gift_card_amount")))
    _add(cab, "descuentoAdicional", _money_or_nil(doc.get("additional_discount")))
    _add(cab, "codigoExcepcion", doc.get("exception_code"))
    _add(cab, "cafc", doc.get("cafc"))
    _add(cab, "leyenda", doc["legend"])
    _add(cab, "usuario", doc["user"])
    _add(cab, "codigoDocumentoSector", sector)
    for line in doc["lines"]:
        det = etree.SubElement(root, "detalle")
        _line(det, line)
        _add(det, "numeroSerie", line.get("serial_number"))
        _add(det, "numeroImei", line.get("imei"))


@register_sector(constants.SECTOR_COMPRA_VENTA)
def _build_compra_venta(root, doc):
    _invoice(root, doc, constants.SECTOR_COMPRA_VENTA)


@register_sector(constants.SECTOR_TELECOM)
def _build_telecom(root, doc):
    _invoice(root, doc, constants.SECTOR_TELECOM, with_joint_nit=True)


@register_sector(constants.SECTOR_CREDIT_DEBIT_NOTE)
def _build_credit_debit_note(root, doc):
    """Nota de Crédito-Débito: referencia a la factura original y dos grupos
    de detalle (1 = ítems de la factura original, 2 = ítems devueltos)."""
    cab = etree.SubElement(root, "cabecera")
    _issuer(cab, doc)
    _add(cab, "numeroNotaCreditoDebito", doc["number"])
    _place_and_customer(cab, doc)
    _add(cab, "numeroFactura", doc["original_number"])
    _add(cab, "numeroAutorizacionCuf", doc["original_cuf"])
    _add(cab, "fechaEmisionFactura", doc["original_emission_iso"])
    _add(cab, "montoTotalOriginal", fmt(doc["amount_original"]))
    _add(cab, "montoTotalDevuelto", fmt(doc["amount_returned"]))
    _add(cab, "montoDescuentoCreditoDebito", _money_or_nil(doc.get("amount_discount")))
    _add(cab, "montoEfectivoCreditoDebito", fmt(doc["amount_effective"]))
    _add(cab, "codigoExcepcion", doc.get("exception_code"))
    _add(cab, "leyenda", doc["legend"])
    _add(cab, "usuario", doc["user"])
    _add(cab, "codigoDocumentoSector", constants.SECTOR_CREDIT_DEBIT_NOTE)
    for line in doc["lines"]:
        det = etree.SubElement(root, "detalle")
        _line(det, line)
        _add(det, "codigoDetalleTransaccion", line["transaction_code"])
