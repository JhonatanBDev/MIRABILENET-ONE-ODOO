"""SiatGateway: la interfaz interna que usa el resto del sistema.

El dominio pide operaciones fiscales a través de esta interfaz y nunca conoce
SOAP, WSDL ni namespaces. Hay dos implementaciones:

- RealSiatGateway: habla con el SIAT (PILOTO o PRODUCCIÓN).
- FakeSiatGateway: simulador determinista para desarrollo y pruebas.
"""

import base64
import datetime
import gzip
import io
import tarfile
from dataclasses import dataclass, field

from lxml import etree

from . import constants, errors
from .soap_client import as_list


@dataclass(frozen=True)
class SiatContext:
    """Identidad fiscal de una operación: siempre aislada por NIT/sucursal/punto."""
    nit: str
    system_code: str
    environment: int
    modality: int
    branch_code: int
    pos_code: int


@dataclass
class SiatResult:
    ok: bool
    status_code: int = 0
    status_description: str = ""
    reception_code: str = ""
    messages: list = field(default_factory=list)

    def messages_text(self):
        return "\n".join(
            "%s: %s" % (m.get("code", ""), m.get("description", "")) for m in self.messages)


def _parse_dt(text):
    return datetime.datetime.fromisoformat(text) if text else None


def _sorted(params):
    """Los tipos del WSDL declaran sus elementos en orden alfabetico."""
    return dict(sorted(params.items()))


def _is_true(value):
    return str(value).strip().lower() == "true"


def _result(data):
    messages = [
        {"code": m.get("codigo", ""), "description": m.get("descripcion", "")}
        for m in as_list(data.get("mensajesList")) if isinstance(m, dict)
    ]
    code = data.get("codigoEstado")
    return SiatResult(
        ok=_is_true(data.get("transaccion")),
        status_code=int(code) if str(code or "").isdigit() else 0,
        status_description=data.get("codigoDescripcion") or "",
        reception_code=data.get("codigoRecepcion") or "",
        messages=messages,
    )


class SiatGateway:
    """Contrato. Todas las fechas de entrada son cadenas ISO en hora fiscal."""

    def check_communication(self, ctx):
        raise NotImplementedError

    def request_cuis(self, ctx):
        raise NotImplementedError

    def request_cufd(self, ctx, cuis):
        raise NotImplementedError

    def sync_catalog(self, ctx, cuis, catalog_type):
        raise NotImplementedError

    def verify_nit(self, ctx, cuis, nit):
        raise NotImplementedError

    def register_pos(self, ctx, cuis, type_code, name, description):
        raise NotImplementedError

    def close_pos(self, ctx, cuis, pos_code):
        raise NotImplementedError

    def send_invoice(self, ctx, cuis, cufd, sector, emission_type, invoice_type,
                     file_gz, file_hash, sent_at):
        raise NotImplementedError

    def check_invoice_status(self, ctx, cuis, cufd, sector, emission_type,
                             invoice_type, cuf):
        raise NotImplementedError

    def cancel_invoice(self, ctx, cuis, cufd, sector, emission_type, invoice_type,
                       cuf, reason_code):
        raise NotImplementedError

    def revert_cancellation(self, ctx, cuis, cufd, sector, emission_type,
                            invoice_type, cuf):
        raise NotImplementedError

    def register_event(self, ctx, cuis, cufd, event_cufd, reason_code, description,
                       start_at, end_at):
        raise NotImplementedError

    def send_package(self, ctx, cuis, cufd, sector, invoice_type, file_gz, file_hash,
                     sent_at, event_code, count, cafc=None):
        raise NotImplementedError

    def validate_package(self, ctx, cuis, cufd, sector, invoice_type, reception_code):
        raise NotImplementedError


class RealSiatGateway(SiatGateway):
    def __init__(self, client):
        self.client = client

    @staticmethod
    def _base(ctx):
        return {
            "codigoAmbiente": ctx.environment,
            "codigoPuntoVenta": ctx.pos_code,
            "codigoSistema": ctx.system_code,
            "codigoSucursal": ctx.branch_code,
            "nit": ctx.nit,
        }

    def _invoice_base(self, ctx, cuis, cufd, sector, emission_type, invoice_type):
        params = self._base(ctx)
        params.update({
            "codigoDocumentoSector": sector,
            "codigoEmision": emission_type,
            "codigoModalidad": ctx.modality,
            "cufd": cufd,
            "cuis": cuis,
            "tipoFacturaDocumento": invoice_type,
        })
        # Los campos propios de cada operación se agregan después, en el
        # mismo orden de la secuencia del WSDL.
        return _sorted(params)

    @staticmethod
    def _op(sector, action):
        table = (constants.ADJUSTMENT_OPERATIONS if sector in constants.ADJUSTMENT_SECTORS
                 else constants.INVOICE_OPERATIONS)
        return table[action]

    @staticmethod
    def _service(sector):
        if sector not in constants.SECTOR_SERVICES:
            raise ValueError("Documento sector %s sin servicio configurado." % sector)
        return constants.SECTOR_SERVICES[sector]

    def check_communication(self, ctx):
        data = self.client.call(
            constants.SERVICE_CODES, "verificarComunicacion", None, {})
        return _is_true(data.get("transaccion"))

    def request_cuis(self, ctx):
        params = _sorted(dict(self._base(ctx), codigoModalidad=ctx.modality))
        data = self.client.call(constants.SERVICE_CODES, "cuis", "SolicitudCuis", params)
        if not data.get("codigo"):
            raise errors.SiatError(
                errors.CUIS, "El SIN no entregó CUIS.", _result(data).messages)
        return {"code": data["codigo"], "valid_until": _parse_dt(data.get("fechaVigencia"))}

    def request_cufd(self, ctx, cuis):
        params = _sorted(dict(self._base(ctx), codigoModalidad=ctx.modality, cuis=cuis))
        data = self.client.call(constants.SERVICE_CODES, "cufd", "SolicitudCufd", params)
        if not data.get("codigo") or not data.get("codigoControl"):
            raise errors.SiatError(
                errors.CUFD, "El SIN no entregó CUFD.", _result(data).messages)
        return {
            "code": data["codigo"],
            "control_code": data["codigoControl"],
            "address": data.get("direccion") or "",
            "valid_until": _parse_dt(data.get("fechaVigencia")),
        }

    def sync_catalog(self, ctx, cuis, catalog_type):
        operation, list_tag = constants.CATALOG_OPERATIONS[catalog_type]
        params = _sorted(dict(self._base(ctx), cuis=cuis))
        data = self.client.call(
            constants.SERVICE_SYNC, operation, "SolicitudSincronizacion", params)
        if not _is_true(data.get("transaccion")):
            raise errors.SiatError(
                errors.REJECTED, "El SIN no entregó el catálogo %s." % catalog_type,
                _result(data).messages)
        return [row for row in as_list(data.get(list_tag)) if isinstance(row, dict)]

    def verify_nit(self, ctx, cuis, nit):
        params = {
            "codigoAmbiente": ctx.environment,
            "codigoModalidad": ctx.modality,
            "codigoSistema": ctx.system_code,
            "codigoSucursal": ctx.branch_code,
            "cuis": cuis,
            "nit": ctx.nit,
            "nitParaVerificacion": nit,
        }
        result = _result(self.client.call(
            constants.SERVICE_CODES, "verificarNit", "SolicitudVerificarNit", params))
        result.ok = result.ok and any(
            str(m.get("code")) == constants.NIT_ACTIVE_CODE for m in result.messages)
        return result

    def register_pos(self, ctx, cuis, type_code, name, description):
        params = {
            "codigoAmbiente": ctx.environment,
            "codigoModalidad": ctx.modality,
            "codigoSistema": ctx.system_code,
            "codigoSucursal": ctx.branch_code,
            "codigoTipoPuntoVenta": type_code,
            "cuis": cuis,
            "descripcion": description,
            "nit": ctx.nit,
            "nombrePuntoVenta": name,
        }
        data = self.client.call(
            constants.SERVICE_OPERATIONS, "registroPuntoVenta",
            "SolicitudRegistroPuntoVenta", params)
        code = str(data.get("codigoPuntoVenta") or "")
        if not _is_true(data.get("transaccion")) or not code.isdigit() or int(code) <= 0:
            raise errors.SiatError(
                errors.REJECTED, "El SIN no registró el punto de venta.",
                _result(data).messages)
        return int(code)

    def close_pos(self, ctx, cuis, pos_code):
        params = {
            "codigoAmbiente": ctx.environment,
            "codigoPuntoVenta": pos_code,
            "codigoSistema": ctx.system_code,
            "codigoSucursal": ctx.branch_code,
            "cuis": cuis,
            "nit": ctx.nit,
        }
        return _result(self.client.call(
            constants.SERVICE_OPERATIONS, "cierrePuntoVenta",
            "SolicitudCierrePuntoVenta", params))

    def send_invoice(self, ctx, cuis, cufd, sector, emission_type, invoice_type,
                     file_gz, file_hash, sent_at):
        params = self._invoice_base(ctx, cuis, cufd, sector, emission_type, invoice_type)
        params.update({
            "archivo": base64.b64encode(file_gz).decode("ascii"),
            "fechaEnvio": sent_at,
            "hashArchivo": file_hash,
        })
        operation, wrapper = self._op(sector, "send")
        return _result(self.client.call(self._service(sector), operation, wrapper, params))

    def check_invoice_status(self, ctx, cuis, cufd, sector, emission_type,
                             invoice_type, cuf):
        params = self._invoice_base(ctx, cuis, cufd, sector, emission_type, invoice_type)
        params["cuf"] = cuf
        operation, wrapper = self._op(sector, "status")
        return _result(self.client.call(self._service(sector), operation, wrapper, params))

    def cancel_invoice(self, ctx, cuis, cufd, sector, emission_type, invoice_type,
                       cuf, reason_code):
        params = self._invoice_base(ctx, cuis, cufd, sector, emission_type, invoice_type)
        params.update({"codigoMotivo": reason_code, "cuf": cuf})
        operation, wrapper = self._op(sector, "cancel")
        return _result(self.client.call(self._service(sector), operation, wrapper, params))

    def revert_cancellation(self, ctx, cuis, cufd, sector, emission_type,
                            invoice_type, cuf):
        params = self._invoice_base(ctx, cuis, cufd, sector, emission_type, invoice_type)
        params["cuf"] = cuf
        operation, wrapper = self._op(sector, "revert")
        return _result(self.client.call(self._service(sector), operation, wrapper, params))

    def register_event(self, ctx, cuis, cufd, event_cufd, reason_code, description,
                       start_at, end_at):
        params = self._base(ctx)
        params.update({
            "codigoMotivoEvento": reason_code,
            "cufd": cufd,
            "cufdEvento": event_cufd,
            "cuis": cuis,
            "descripcion": description,
            "fechaHoraFinEvento": end_at,
            "fechaHoraInicioEvento": start_at,
        })
        params = _sorted(params)
        data = self.client.call(
            constants.SERVICE_OPERATIONS, "registroEventoSignificativo",
            "SolicitudEventoSignificativo", params)
        result = _result(data)
        result.reception_code = str(data.get("codigoRecepcionEventoSignificativo") or "")
        return result

    def send_package(self, ctx, cuis, cufd, sector, invoice_type, file_gz, file_hash,
                     sent_at, event_code, count, cafc=None):
        params = self._invoice_base(
            ctx, cuis, cufd, sector, constants.EMISSION_OFFLINE, invoice_type)
        params.update({
            "archivo": base64.b64encode(file_gz).decode("ascii"),
            "fechaEnvio": sent_at,
            "hashArchivo": file_hash,
            "cafc": cafc,
            "cantidadFacturas": count,
            "codigoEvento": event_code,
        })
        return _result(self.client.call(
            self._service(sector), "recepcionPaqueteFactura",
            "SolicitudServicioRecepcionPaquete", params))

    def validate_package(self, ctx, cuis, cufd, sector, invoice_type, reception_code):
        params = self._invoice_base(
            ctx, cuis, cufd, sector, constants.EMISSION_OFFLINE, invoice_type)
        params["codigoRecepcion"] = reception_code
        return _result(self.client.call(
            self._service(sector), "validacionRecepcionPaqueteFactura",
            "SolicitudServicioValidacionRecepcionPaquete", params))


# --------------------------------------------------------------------------
# Simulador
# --------------------------------------------------------------------------

# Catálogos de juguete para desarrollo. NO son valores oficiales del SIN.
_FAKE_CATALOGS = {
    "actividades": [
        {"codigoCaeb": "620100", "descripcion": "ACTIVIDAD SIMULADA", "tipoActividad": "P"}],
    "actividades_documento_sector": [
        {"codigoActividad": "620100", "codigoDocumentoSector": "1",
         "tipoDocumentoSector": "FCV"},
        {"codigoActividad": "620100", "codigoDocumentoSector": "22",
         "tipoDocumentoSector": "FTC"},
        {"codigoActividad": "620100", "codigoDocumentoSector": "24",
         "tipoDocumentoSector": "NCD"}],
    "leyendas": [
        {"codigoActividad": "620100",
         "descripcionLeyenda": "Ley N° 453: leyenda simulada para desarrollo."}],
    "mensajes_servicios": [{"codigoClasificador": "908", "descripcion": "VALIDADA"}],
    "productos_servicios": [
        {"codigoActividad": "620100", "codigoProducto": "83141",
         "descripcionProducto": "SERVICIO SIMULADO"}],
    "eventos_significativos": [
        {"codigoClasificador": "1", "descripcion": "CORTE DE INTERNET (SIMULADO)"},
        {"codigoClasificador": "2", "descripcion": "SIN INACCESIBLE (SIMULADO)"}],
    "motivo_anulacion": [
        {"codigoClasificador": "1", "descripcion": "FACTURA MAL EMITIDA (SIMULADO)"}],
    "pais_origen": [{"codigoClasificador": "22", "descripcion": "BOLIVIA"}],
    "tipo_documento_identidad": [
        {"codigoClasificador": "1", "descripcion": "CI - CEDULA DE IDENTIDAD"},
        {"codigoClasificador": "3", "descripcion": "PAS - PASAPORTE"},
        {"codigoClasificador": "5", "descripcion": "NIT"}],
    "tipo_documento_sector": [
        {"codigoClasificador": "1", "descripcion": "FACTURA COMPRA-VENTA"}],
    "tipo_emision": [
        {"codigoClasificador": "1", "descripcion": "EN LINEA"},
        {"codigoClasificador": "2", "descripcion": "FUERA DE LINEA"}],
    "tipo_metodo_pago": [
        {"codigoClasificador": "1", "descripcion": "EFECTIVO"},
        {"codigoClasificador": "2", "descripcion": "TARJETA"},
        {"codigoClasificador": "6", "descripcion": "PAGO POSTERIOR"},
        {"codigoClasificador": "7", "descripcion": "TRANSFERENCIA BANCARIA"},
        {"codigoClasificador": "10", "descripcion": "EFECTIVO - TARJETA"},
        {"codigoClasificador": "27", "descripcion": "GIFT-CARD"},
        {"codigoClasificador": "35", "descripcion": "EFECTIVO – GIFT"},
        {"codigoClasificador": "90", "descripcion": "COMBINACION DESCONOCIDA / RARA"}],
    "tipo_moneda": [
        {"codigoClasificador": "1", "descripcion": "BOLIVIANO"},
        {"codigoClasificador": "2", "descripcion": "DOLAR"}],
    "tipo_punto_venta": [{"codigoClasificador": "5", "descripcion": "PUNTO DE VENTA CAJEROS"}],
    "tipos_factura": [
        {"codigoClasificador": "1", "descripcion": "FACTURA CON DERECHO A CREDITO FISCAL"}],
    "unidad_medida": [
        {"codigoClasificador": "58", "descripcion": "UNIDAD (SERVICIOS)"}],
}


class FakeSiatGateway(SiatGateway):
    """SIAT simulado. Mantiene estado en memoria por NIT para poder probar
    idempotencia, anulación, reversión y paquetes sin conexión.

    `failures` permite inyectar fallas en orden de llegada:
      - "timeout":      el SIN no responde y NO recibió la operación.
      - "lost_reply":   el SIN SÍ procesó la operación pero la respuesta se perdió.
      - "reject":       rechazo funcional.
    """

    _state = {}
    failures = []
    inactive_nits = set()

    def __init__(self, on_exchange=None):
        self.on_exchange = on_exchange

    @classmethod
    def reset(cls):
        cls._state = {}
        cls.failures = []
        cls.inactive_nits = set()

    def _nit(self, ctx):
        return self._state.setdefault(
            ctx.nit, {"invoices": {}, "packages": {}, "counter": 0})

    def _next_failure(self, operation):
        failure = self.failures.pop(0) if self.failures else None
        if self.on_exchange:
            self.on_exchange({
                "service": "FakeSiat", "operation": operation,
                "request_xml": "", "response_xml": failure or "ok",
                "duration_ms": 0, "success": failure in (None, "reject"),
                "error_code": errors.TIMEOUT if failure in ("timeout", "lost_reply") else False,
            })
        if failure == "timeout":
            raise errors.SiatCommunicationError("Timeout simulado.")
        return failure

    @staticmethod
    def _rejected():
        return SiatResult(
            ok=False, status_code=constants.ST_REJECTED, status_description="RECHAZADA",
            messages=[{"code": "999", "description": "Rechazo simulado."}])

    def check_communication(self, ctx):
        self._next_failure("verificarComunicacion")
        return True

    def request_cuis(self, ctx):
        self._next_failure("cuis")
        return {
            "code": "FAKECUIS%s%s" % (ctx.branch_code, ctx.pos_code),
            "valid_until": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=365),
        }

    def request_cufd(self, ctx, cuis):
        self._next_failure("cufd")
        store = self._nit(ctx)
        store["counter"] += 1
        return {
            "code": "FAKECUFD%s-%s-%s" % (ctx.branch_code, ctx.pos_code, store["counter"]),
            "control_code": "A19E23EF34124CD",
            "address": "DIRECCION SIMULADA",
            "valid_until": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=24),
        }

    def sync_catalog(self, ctx, cuis, catalog_type):
        self._next_failure("sync:%s" % catalog_type)
        return [dict(row) for row in _FAKE_CATALOGS.get(catalog_type, [])]

    def verify_nit(self, ctx, cuis, nit):
        self._next_failure("verificarNit")
        if str(nit) in self.inactive_nits:
            return SiatResult(ok=False, messages=[
                {"code": "994", "description": "NIT INEXISTENTE (simulado)"}])
        return SiatResult(ok=True, messages=[
            {"code": constants.NIT_ACTIVE_CODE, "description": "NIT ACTIVO (simulado)"}])

    def register_pos(self, ctx, cuis, type_code, name, description):
        failure = self._next_failure("registroPuntoVenta")
        if failure == "reject":
            raise errors.SiatError(errors.REJECTED, "Registro rechazado (simulado).")
        store = self._nit(ctx)
        store["pos"] = store.get("pos", 0) + 1
        return store["pos"]

    def close_pos(self, ctx, cuis, pos_code):
        self._next_failure("cierrePuntoVenta")
        return SiatResult(ok=True)

    def send_invoice(self, ctx, cuis, cufd, sector, emission_type, invoice_type,
                     file_gz, file_hash, sent_at):
        failure = self._next_failure("recepcionFactura")
        if failure == "reject":
            return self._rejected()
        store = self._nit(ctx)
        store["counter"] += 1
        cuf = etree.fromstring(gzip.decompress(file_gz)).findtext("cabecera/cuf")
        store["invoices"][cuf] = "valid"
        if failure == "lost_reply":
            raise errors.SiatCommunicationError("Respuesta perdida (simulado).")
        return SiatResult(
            ok=True, status_code=constants.ST_VALIDATED, status_description="VALIDADA",
            reception_code="FAKE-REC-%s" % store["counter"])

    def check_invoice_status(self, ctx, cuis, cufd, sector, emission_type,
                             invoice_type, cuf):
        self._next_failure("verificacionEstadoFactura")
        status = self._nit(ctx)["invoices"].get(cuf)
        if status == "valid":
            return SiatResult(ok=True, status_code=constants.ST_VALID,
                              status_description="VALIDA", reception_code="FAKE-REC-Q")
        if status == "cancelled":
            return SiatResult(ok=True, status_code=constants.ST_CANCELLED,
                              status_description="ANULADA")
        return SiatResult(ok=False, status_code=constants.ST_REJECTED,
                          status_description="NO ENCONTRADA",
                          messages=[{"code": "998", "description": "CUF inexistente."}])

    def cancel_invoice(self, ctx, cuis, cufd, sector, emission_type, invoice_type,
                       cuf, reason_code):
        failure = self._next_failure("anulacionFactura")
        if failure == "reject":
            return self._rejected()
        self._nit(ctx)["invoices"][cuf] = "cancelled"
        return SiatResult(ok=True, status_code=constants.ST_CANCEL_CONFIRMED,
                          status_description="ANULACION CONFIRMADA")

    def revert_cancellation(self, ctx, cuis, cufd, sector, emission_type,
                            invoice_type, cuf):
        failure = self._next_failure("reversionAnulacionFactura")
        if failure == "reject":
            return self._rejected()
        self._nit(ctx)["invoices"][cuf] = "valid"
        return SiatResult(ok=True, status_code=constants.ST_REVERSAL_CONFIRMED,
                          status_description="REVERSION DE ANULACION CONFIRMADA")

    def register_event(self, ctx, cuis, cufd, event_cufd, reason_code, description,
                       start_at, end_at):
        failure = self._next_failure("registroEventoSignificativo")
        if failure == "reject":
            return self._rejected()
        store = self._nit(ctx)
        store["counter"] += 1
        return SiatResult(ok=True, reception_code="FAKE-EVT-%s" % store["counter"])

    def send_package(self, ctx, cuis, cufd, sector, invoice_type, file_gz, file_hash,
                     sent_at, event_code, count, cafc=None):
        failure = self._next_failure("recepcionPaqueteFactura")
        if failure == "reject":
            return self._rejected()
        store = self._nit(ctx)
        store["counter"] += 1
        code = "FAKE-PKG-%s" % store["counter"]
        store["packages"][code] = count
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(file_gz))) as tar:
            for member in tar.getmembers():
                xml = tar.extractfile(member).read()
                store["invoices"][etree.fromstring(xml).findtext("cabecera/cuf")] = "valid"
        return SiatResult(ok=True, status_code=constants.ST_PENDING,
                          status_description="PENDIENTE", reception_code=code)

    def validate_package(self, ctx, cuis, cufd, sector, invoice_type, reception_code):
        failure = self._next_failure("validacionRecepcionPaqueteFactura")
        if failure == "reject":
            return SiatResult(
                ok=False, status_code=constants.ST_OBSERVED, status_description="OBSERVADA",
                reception_code=reception_code,
                messages=[{"code": "997", "description": "Paquete observado (simulado)."}])
        if reception_code not in self._nit(ctx)["packages"]:
            return self._rejected()
        return SiatResult(ok=True, status_code=constants.ST_VALIDATED,
                          status_description="VALIDADA", reception_code=reception_code)
