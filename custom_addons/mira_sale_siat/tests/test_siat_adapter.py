import datetime
from decimal import Decimal

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

from ..siat import constants, errors, packaging, xml_builder, xsd_validator
from ..siat.amounts import dec, fmt, money
from ..siat.cuf import build_cuf, mod11
from ..siat.gateway import RealSiatGateway, SiatContext
from ..siat.soap_client import SiatSoapClient, redact
from ..siat.vault import Vault, fingerprint

CUIS_RESPONSE = b"""<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ns2:cuisResponse xmlns:ns2="https://siat.impuestos.gob.bo/">
      <RespuestaCuis>
        <codigo>ABC12345</codigo>
        <fechaVigencia>2027-01-01T00:00:00.000-04:00</fechaVigencia>
        <mensajesList><codigo>980</codigo><descripcion>EXISTE UN CUIS VIGENTE</descripcion></mensajesList>
        <transaccion>false</transaccion>
      </RespuestaCuis>
    </ns2:cuisResponse>
  </soap:Body>
</soap:Envelope>"""


class _Response:
    def __init__(self, content, status_code=200):
        self.content = content
        self.text = content.decode("utf-8")
        self.status_code = status_code


class _Session:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.response


def _document():
    return {
        "sector_code": 1, "issuer_nit": "1003579028", "issuer_name": "Empresa Demo",
        "municipality": "La Paz", "phone": None, "number": 1, "cuf": "ABC", "cufd": "XYZ",
        "branch_code": 0, "address": "Av. Siempre Viva 1", "pos_code": 0,
        "emission_iso": "2026-10-06T16:03:48.675", "customer_name": "CLIENTE DEMO",
        "customer_doc_type": 1, "customer_doc_number": "1234567", "customer_code": "C1",
        "payment_method_code": 1, "amount_total": Decimal("200.00"),
        "amount_subject_to_vat": Decimal("200.00"), "currency_code": 1, "exchange_rate": 1,
        "amount_total_currency": Decimal("200.00"), "legend": "Ley 453", "user": "cajero",
        "lines": [{
            "activity_code": "620100", "siat_product_code": "83141", "product_code": "PLAN-50",
            "description": "Servicio mensual", "quantity": Decimal("1"), "unit_code": 58,
            "unit_price": Decimal("200"), "discount": Decimal("0"), "subtotal": Decimal("200"),
        }],
    }


@tagged("post_install", "-at_install", "mira_siat")
class TestSiatAdapter(TransactionCase):
    """Pruebas unitarias y de contrato del SIAT Adapter (sin ORM ni red)."""

    def _xsd(self):
        with file_open("mira_sale_siat/data/xsd/facturaComputarizadaCompraVenta.xsd", "rb") as fh:
            return fh.read()

    # ---- CUF --------------------------------------------------------------
    def test_mod11(self):
        # Suma ponderada 2..9 desde la derecha, módulo 11; 10 se representa "1".
        self.assertEqual(mod11("0"), "0")
        self.assertEqual(mod11("1"), "2")
        self.assertEqual(mod11("5"), "1")  # 5*2 = 10 -> "1"
        self.assertEqual(mod11("12"), "7")  # 2*2 + 1*3 = 7

    def test_cuf_structure(self):
        when = datetime.datetime(2019, 1, 13, 16, 37, 21, 231000)
        cuf = build_cuf("123456789", when, 0, 1, 1, 1, 1, 1, 0, "CTRL")
        self.assertTrue(cuf.endswith("CTRL"))
        base = "0000123456789" "20190113163721231" "0000" "1" "1" "1" "01" "0000000001" "0000"
        self.assertEqual(len(base), 53)
        self.assertEqual(cuf[:-4], "%X" % int(base + mod11(base)))
        # Determinista, y sensible a cada componente.
        self.assertEqual(cuf, build_cuf("123456789", when, 0, 1, 1, 1, 1, 1, 0, "CTRL"))
        self.assertNotEqual(cuf, build_cuf("123456789", when, 0, 1, 1, 1, 1, 2, 0, "CTRL"))
        self.assertNotEqual(cuf, build_cuf("123456789", when, 0, 1, 2, 1, 1, 1, 0, "CTRL"))

    def test_cuf_rejects_bad_input(self):
        when = datetime.datetime(2026, 1, 1)
        with self.assertRaises(ValueError):
            build_cuf("12A", when, 0, 2, 1, 1, 1, 1, 0, "X")
        with self.assertRaises(ValueError):
            build_cuf("1" * 14, when, 0, 2, 1, 1, 1, 1, 0, "X")
        with self.assertRaises(ValueError):
            build_cuf("123", when, 0, 2, 1, 1, 1, 1, 0, "")

    # ---- dinero -----------------------------------------------------------
    def test_decimal_money(self):
        self.assertEqual(dec(0.1) + dec(0.2), Decimal("0.3"))
        self.assertEqual(money("2.345"), Decimal("2.35"))
        self.assertEqual(money("2.344"), Decimal("2.34"))
        self.assertEqual(fmt(200), "200.00")

    # ---- XML / XSD --------------------------------------------------------
    def test_xml_valid_against_official_xsd(self):
        xml = xml_builder.build_xml(_document(), constants.MODALITY_COMPUTERIZED)
        self.assertIn(b"<facturaComputarizadaCompraVenta", xml)
        self.assertIn(b'<telefono xsi:nil="true"/>', xml)
        self.assertIn(b"<montoTotal>200.00</montoTotal>", xml)
        self.assertTrue(xsd_validator.validate(xml, self._xsd()))

    def test_xsd_blocks_invalid_document(self):
        document = _document()
        document["amount_total"] = Decimal("0")
        xml = xml_builder.build_xml(document, constants.MODALITY_COMPUTERIZED)
        with self.assertRaises(errors.SiatXsdError) as ctx:
            xsd_validator.validate(xml, self._xsd())
        self.assertEqual(ctx.exception.code, errors.XSD)
        self.assertTrue(any("montoTotal" in d for d in ctx.exception.details))

    def test_unknown_sector(self):
        document = _document()
        document["sector_code"] = 999
        with self.assertRaises(ValueError):
            xml_builder.build_xml(document, constants.MODALITY_COMPUTERIZED)

    # ---- empaquetado ------------------------------------------------------
    def test_packaging_deterministic(self):
        data = b"<a/>"
        self.assertEqual(packaging.gzip_bytes(data), packaging.gzip_bytes(data))
        self.assertEqual(packaging.tar_gz([("a.xml", data)]), packaging.tar_gz([("a.xml", data)]))
        self.assertEqual([len(c) for c in packaging.chunked(list(range(5)), 2)], [2, 2, 1])
        with self.assertRaises(ValueError):
            packaging.chunked([1], 0)

    # ---- bóveda -----------------------------------------------------------
    def test_vault(self):
        vault = Vault("clave-maestra")
        secret = vault.encrypt("TOKEN-SECRETO")
        self.assertNotIn("TOKEN-SECRETO", secret)
        self.assertEqual(vault.decrypt(secret), "TOKEN-SECRETO")
        with self.assertRaises(errors.SiatError):
            Vault("otra-clave").decrypt(secret)
        with self.assertRaises(errors.SiatError):
            Vault("")
        self.assertEqual(len(fingerprint("TOKEN-SECRETO")), 12)

    # ---- cliente SOAP -----------------------------------------------------
    def _context(self):
        return SiatContext(nit="1003579028", system_code="SYS", environment=2, modality=2,
                           branch_code=0, pos_code=1)

    def test_soap_cuis_call(self):
        exchanges = []
        session = _Session(_Response(CUIS_RESPONSE))
        client = SiatSoapClient("https://siat.example/v2/", "TOKEN-SECRETO",
                                on_exchange=exchanges.append, session=session)
        data = RealSiatGateway(client).request_cuis(self._context())
        self.assertEqual(data["code"], "ABC12345")
        self.assertEqual(data["valid_until"].year, 2027)
        call = session.calls[0]
        self.assertEqual(call["url"], "https://siat.example/v2/FacturacionCodigos")
        self.assertEqual(call["headers"]["apikey"], "TokenApi TOKEN-SECRETO")
        self.assertIn(b"<SolicitudCuis>", call["data"])
        self.assertIn(b"<nit>1003579028</nit>", call["data"])
        # La evidencia nunca contiene el token.
        self.assertEqual(len(exchanges), 1)
        self.assertNotIn("TOKEN-SECRETO", str(exchanges[0]))
        self.assertTrue(exchanges[0]["success"])

    def test_soap_timeout_is_communication_error(self):
        import requests
        exchanges = []
        client = SiatSoapClient("https://siat.example/v2", "T", on_exchange=exchanges.append,
                                session=_Session(exc=requests.exceptions.ReadTimeout()))
        with self.assertRaises(errors.SiatCommunicationError) as ctx:
            RealSiatGateway(client).request_cuis(self._context())
        self.assertEqual(ctx.exception.code, errors.TIMEOUT)
        self.assertFalse(exchanges[0]["success"])

    def test_soap_unauthorized_is_token_error(self):
        client = SiatSoapClient("https://siat.example/v2", "T",
                                session=_Session(_Response(b"denied", 401)))
        with self.assertRaises(errors.SiatError) as ctx:
            RealSiatGateway(client).request_cuis(self._context())
        self.assertEqual(ctx.exception.code, errors.TOKEN)

    def _reply(self, operation, inner, body):
        xml = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<ns2:%sResponse xmlns:ns2="https://siat.impuestos.gob.bo/"><%s>%s</%s>'
            "</ns2:%sResponse></soap:Body></soap:Envelope>"
        ) % (operation, inner, body, inner, operation)
        return _Session(_Response(xml.encode()))

    def _tags(self, data, wrapper):
        from lxml import etree
        node = etree.fromstring(data).find(".//" + wrapper)
        return [child.tag for child in node]

    def test_request_elements_follow_wsdl_sequence(self):
        """Los elementos viajan en el orden de la secuencia del WSDL."""
        session = self._reply(
            "recepcionFactura", "RespuestaServicioFacturacion",
            "<codigoEstado>908</codigoEstado><codigoRecepcion>R1</codigoRecepcion>"
            "<transaccion>true</transaccion>")
        gateway = RealSiatGateway(SiatSoapClient("https://siat.example/v2", "T", session=session))
        result = gateway.send_invoice(
            self._context(), "CUIS", "CUFD", constants.SECTOR_TELECOM, 1, 1, b"gz", "hash",
            "2026-01-01T00:00:00.000")
        self.assertTrue(result.ok)
        self.assertEqual(result.reception_code, "R1")
        call = session.calls[0]
        self.assertTrue(call["url"].endswith("/ServicioFacturacionTelecomunicaciones"))
        self.assertEqual(self._tags(call["data"], "SolicitudServicioRecepcionFactura"), [
            "codigoAmbiente", "codigoDocumentoSector", "codigoEmision", "codigoModalidad",
            "codigoPuntoVenta", "codigoSistema", "codigoSucursal", "cufd", "cuis", "nit",
            "tipoFacturaDocumento", "archivo", "fechaEnvio", "hashArchivo"])

    def test_adjustment_documents_use_their_own_operations(self):
        session = self._reply(
            "recepcionDocumentoAjuste", "RespuestaServicioFacturacion",
            "<codigoEstado>908</codigoEstado><transaccion>true</transaccion>")
        gateway = RealSiatGateway(SiatSoapClient("https://siat.example/v2", "T", session=session))
        gateway.send_invoice(
            self._context(), "CUIS", "CUFD", constants.SECTOR_CREDIT_DEBIT_NOTE, 1, 3,
            b"gz", "hash", "2026-01-01T00:00:00.000")
        call = session.calls[0]
        self.assertTrue(call["url"].endswith("/ServicioFacturacionDocumentoAjuste"))
        self.assertIn(b"recepcionDocumentoAjuste", call["data"])
        self.assertIn(b"<SolicitudServicioRecepcionDocumentoAjuste>", call["data"])

    def test_verify_nit_request_and_result(self):
        session = self._reply(
            "verificarNit", "RespuestaVerificarNit",
            "<mensajesList><codigo>986</codigo><descripcion>NIT ACTIVO</descripcion>"
            "</mensajesList><transaccion>true</transaccion>")
        gateway = RealSiatGateway(SiatSoapClient("https://siat.example/v2", "T", session=session))
        self.assertTrue(gateway.verify_nit(self._context(), "CUIS", "1020304050").ok)
        self.assertEqual(self._tags(session.calls[0]["data"], "SolicitudVerificarNit"), [
            "codigoAmbiente", "codigoModalidad", "codigoSistema", "codigoSucursal", "cuis",
            "nit", "nitParaVerificacion"])
        inactive = self._reply(
            "verificarNit", "RespuestaVerificarNit",
            "<mensajesList><codigo>994</codigo><descripcion>NIT INEXISTENTE</descripcion>"
            "</mensajesList><transaccion>false</transaccion>")
        gateway = RealSiatGateway(SiatSoapClient("https://siat.example/v2", "T", session=inactive))
        self.assertFalse(gateway.verify_nit(self._context(), "CUIS", "1").ok)

    def test_register_point_of_sale_request(self):
        session = self._reply(
            "registroPuntoVenta", "RespuestaRegistroPuntoVenta",
            "<codigoPuntoVenta>3</codigoPuntoVenta><transaccion>true</transaccion>")
        gateway = RealSiatGateway(SiatSoapClient("https://siat.example/v2", "T", session=session))
        self.assertEqual(gateway.register_pos(self._context(), "CUIS", 5, "Caja 2", "Caja 2"), 3)
        self.assertEqual(self._tags(session.calls[0]["data"], "SolicitudRegistroPuntoVenta"), [
            "codigoAmbiente", "codigoModalidad", "codigoSistema", "codigoSucursal",
            "codigoTipoPuntoVenta", "cuis", "descripcion", "nit", "nombrePuntoVenta"])
        rejected = self._reply(
            "registroPuntoVenta", "RespuestaRegistroPuntoVenta", "<transaccion>false</transaccion>")
        gateway = RealSiatGateway(SiatSoapClient("https://siat.example/v2", "T", session=rejected))
        with self.assertRaises(errors.SiatError):
            gateway.register_pos(self._context(), "CUIS", 5, "Caja 2", "Caja 2")

    def test_note_and_telecom_xml_against_official_xsd(self):
        telecom = dict(_document(), sector_code=constants.SECTOR_TELECOM, joint_nit=None)
        xml = xml_builder.build_xml(telecom, constants.MODALITY_COMPUTERIZED)
        with file_open("mira_sale_siat/data/xsd/facturaComputarizadaTelecomunicacion.xsd", "rb") as fh:
            self.assertTrue(xsd_validator.validate(xml, fh.read()))
        base = _document()
        line = base["lines"][0]
        note = dict(
            base, sector_code=constants.SECTOR_CREDIT_DEBIT_NOTE, original_number=1,
            original_cuf="ABC", original_emission_iso="2026-10-01T10:00:00.000",
            amount_original=Decimal("200"), amount_returned=Decimal("200"),
            amount_effective=Decimal("26"),
            lines=[dict(line, transaction_code=1), dict(line, transaction_code=2)])
        xml = xml_builder.build_xml(note, constants.MODALITY_COMPUTERIZED)
        with file_open("mira_sale_siat/data/xsd/notaComputarizadaCreditoDebito.xsd", "rb") as fh:
            self.assertTrue(xsd_validator.validate(xml, fh.read()))

    def test_redaction(self):
        text = redact("<cuis>ABCDEFGH</cuis><cufd>12345678</cufd><archivo>QUJD</archivo>")
        self.assertNotIn("ABCDEFGH", text)
        self.assertNotIn("12345678", text)
        self.assertNotIn("QUJD", text)
        self.assertIn("***EFGH", text)
