"""Catálogo de errores interno (sección 10.2 de la especificación)."""

TOKEN = "MS-SIAT-001"
CUIS = "MS-SIAT-002"
CUFD = "MS-SIAT-003"
XSD = "MS-SIAT-004"
TIMEOUT = "MS-SIAT-005"
REJECTED = "MS-SIAT-006"
CONTINGENCY = "MS-SIAT-007"
AUTH = "MS-AUTH-001"
TENANT = "MS-TENANT-001"

# código -> (descripción, acción para la interfaz)
ERROR_CATALOG = {
    TOKEN: ("Token ausente o vencido",
            "Pida al administrador que reconfigure el token delegado."),
    CUIS: ("CUIS no vigente", "Renueve el CUIS del punto de venta."),
    CUFD: ("CUFD no vigente", "Renueve el CUFD y vuelva a intentar."),
    XSD: ("El XML no cumple el XSD", "Corrija el dato indicado antes de enviar."),
    TIMEOUT: ("Sin respuesta del SIN",
              "No vuelva a emitir: use «Consultar y reintentar» sobre el mismo documento."),
    REJECTED: ("Rechazo funcional del SIN",
               "Revise los códigos devueltos y corrija manualmente."),
    CONTINGENCY: ("Contingencia activa",
                  "El documento se emite fuera de línea y se envía por paquete."),
    AUTH: ("Permiso insuficiente", "Solicite el permiso a un administrador."),
    TENANT: ("Empresa suspendida o no asociada",
             "Las operaciones fiscales están bloqueadas para esta empresa."),
}


class SiatError(Exception):
    """Error del subsistema SIAT con código del catálogo interno."""

    def __init__(self, code, message=None, details=None):
        self.code = code
        self.message = message or ERROR_CATALOG.get(code, ("Error SIAT", ""))[0]
        self.details = details or []
        super().__init__("[%s] %s" % (code, self.message))

    @property
    def action(self):
        return ERROR_CATALOG.get(self.code, ("", ""))[1]


class SiatCommunicationError(SiatError):
    """Falla de comunicación (timeout, conexión, 5xx). NO es un rechazo del SIN:
    el resultado de la operación es desconocido."""

    def __init__(self, message=None, details=None):
        super().__init__(TIMEOUT, message, details)


class SiatXsdError(SiatError):
    def __init__(self, details):
        super().__init__(XSD, details=details)
