"""Constantes del protocolo SIAT.

Solo viven aquí los valores que pertenecen al protocolo (ambiente, modalidad,
tipo de emisión, estados de respuesta). Los catálogos que el SIN puede cambiar
(actividades, productos, unidades, métodos de pago, motivos, eventos...) NO se
codifican: se sincronizan y se guardan por contribuyente.

Los códigos de estado deben contrastarse con `sincronizarListaMensajesServicios`
antes de cada homologación.
"""

MODALITY_ELECTRONIC = 1
MODALITY_COMPUTERIZED = 2

EMISSION_ONLINE = 1
EMISSION_OFFLINE = 2

INVOICE_TYPE_TAX_CREDIT = 1  # tipoFacturaDocumento: con derecho a crédito fiscal
INVOICE_TYPE_ADJUSTMENT = 3  # tipoFacturaDocumento: documento de ajuste (notas)

# codigoDocumentoSector: valor fijo ("fixed") en el XSD oficial de cada documento.
SECTOR_COMPRA_VENTA = 1
SECTOR_TELECOM = 22
SECTOR_CREDIT_DEBIT_NOTE = 24

INVOICE_SECTORS = (SECTOR_COMPRA_VENTA, SECTOR_TELECOM)
ADJUSTMENT_SECTORS = (SECTOR_CREDIT_DEBIT_NOTE,)

SECTOR_INVOICE_TYPE = {
    SECTOR_COMPRA_VENTA: INVOICE_TYPE_TAX_CREDIT,
    SECTOR_TELECOM: INVOICE_TYPE_TAX_CREDIT,
    SECTOR_CREDIT_DEBIT_NOTE: INVOICE_TYPE_ADJUSTMENT,
}

# Alícuota del IVA para el crédito/débito fiscal de una nota de ajuste.
VAT_RATE = "0.13"

# NIT reservados (casos especiales de la normativa de facturación).
NIT_FOREIGNER = "99001"
NIT_TAX_CONTROL = "99002"
NIT_MINOR_SALES = "99003"
RESERVED_NITS = {
    NIT_FOREIGNER: None,  # usa la razón social del propio cliente extranjero
    NIT_TAX_CONTROL: "CONTROL TRIBUTARIO",
    NIT_MINOR_SALES: "VENTAS MENORES DEL DIA",
}

# Código de respuesta de verificarNit cuando el NIT está activo.
NIT_ACTIVE_CODE = "986"

# Tipo de documento de identidad "NIT" en el XSD de Compra y Venta (1..5).
DOC_TYPE_NIT = 5
DOC_TYPE_CI = 1
# Tipos de documento que el SIN exige estrictamente numéricos.
NUMERIC_DOC_TYPES = (DOC_TYPE_CI, DOC_TYPE_NIT)

# codigoEstado de las respuestas de los servicios de facturación.
ST_PENDING = 901
ST_REJECTED = 902
ST_OBSERVED = 904
ST_CANCEL_CONFIRMED = 905
ST_REVERSAL_CONFIRMED = 907
ST_VALIDATED = 908
ST_VALID = 690
ST_CANCELLED = 691

ACCEPTED_STATES = (ST_VALIDATED, ST_VALID)

# Servicio SOAP que atiende cada documento sector. Extensible: un sector nuevo
# se habilita registrando aquí su servicio y su constructor de XML.
SERVICE_CODES = "FacturacionCodigos"
SERVICE_SYNC = "FacturacionSincronizacion"
SERVICE_OPERATIONS = "FacturacionOperaciones"
SECTOR_SERVICES = {
    SECTOR_COMPRA_VENTA: "ServicioFacturacionCompraVenta",
    SECTOR_TELECOM: "ServicioFacturacionTelecomunicaciones",
    SECTOR_CREDIT_DEBIT_NOTE: "ServicioFacturacionDocumentoAjuste",
}

# acción -> (operación SOAP, elemento de la solicitud). Nombres tomados de los
# WSDL de PILOTO guardados en data/wsdl/.
INVOICE_OPERATIONS = {
    "send": ("recepcionFactura", "SolicitudServicioRecepcionFactura"),
    "status": ("verificacionEstadoFactura", "SolicitudServicioVerificacionEstadoFactura"),
    "cancel": ("anulacionFactura", "SolicitudServicioAnulacionFactura"),
    "revert": ("reversionAnulacionFactura", "SolicitudServicioReversionAnulacionFactura"),
}
ADJUSTMENT_OPERATIONS = {
    "send": ("recepcionDocumentoAjuste", "SolicitudServicioRecepcionDocumentoAjuste"),
    "status": ("verificacionEstadoDocumentoAjuste",
               "SolicitudServicioVerificacionEstadoDocumentoAjuste"),
    "cancel": ("anulacionDocumentoAjuste", "SolicitudServicioAnulacionDocumentoAjuste"),
    "revert": ("reversionAnulacionDocumentoAjuste",
               "SolicitudServicioReversionAnulacionDocumentoAjuste"),
}

SOAP_NAMESPACE = "https://siat.impuestos.gob.bo/"

# tipo de catálogo -> (operación SOAP, etiqueta de la lista en la respuesta)
CATALOG_OPERATIONS = {
    "actividades": ("sincronizarActividades", "listaActividades"),
    "actividades_documento_sector": (
        "sincronizarListaActividadesDocumentoSector", "listaActividadesDocumentoSector"),
    "leyendas": ("sincronizarListaLeyendasFactura", "listaLeyendas"),
    "mensajes_servicios": ("sincronizarListaMensajesServicios", "listaCodigos"),
    "productos_servicios": ("sincronizarListaProductosServicios", "listaCodigos"),
    "eventos_significativos": ("sincronizarParametricaEventosSignificativos", "listaCodigos"),
    "motivo_anulacion": ("sincronizarParametricaMotivoAnulacion", "listaCodigos"),
    "pais_origen": ("sincronizarParametricaPaisOrigen", "listaCodigos"),
    "tipo_documento_identidad": (
        "sincronizarParametricaTipoDocumentoIdentidad", "listaCodigos"),
    "tipo_documento_sector": ("sincronizarParametricaTipoDocumentoSector", "listaCodigos"),
    "tipo_emision": ("sincronizarParametricaTipoEmision", "listaCodigos"),
    "tipo_metodo_pago": ("sincronizarParametricaTipoMetodoPago", "listaCodigos"),
    "tipo_moneda": ("sincronizarParametricaTipoMoneda", "listaCodigos"),
    "tipo_punto_venta": ("sincronizarParametricaTipoPuntoVenta", "listaCodigos"),
    "tipos_factura": ("sincronizarParametricaTiposFactura", "listaCodigos"),
    "unidad_medida": ("sincronizarParametricaUnidadMedida", "listaCodigos"),
}
