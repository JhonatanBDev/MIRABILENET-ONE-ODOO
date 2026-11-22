"""Contenido inicial de AeroLab.

Copiado del sistema anterior (seed_aerolab). Son textos genéricos: no traen datos de
contacto, cifras, fechas, cupos ni precios.
"""
CURSOS = [
    {
        "slug": "pilotaje-basico-drones",
        "nombre": "Pilotaje basico de drones",
        "nivel": "basico",
        "aplicacion": "pilotaje",
        "resumen": "Primer vuelo seguro: control manual, normativa y mantenimiento del equipo.",
        "descripcion": (
            "Curso de entrada para quien nunca volo o volo solo por su cuenta. "
            "Se practica en campo abierto con acompanamiento del instructor y "
            "equipo de la escuela.\n"
            "Al terminar el participante puede planificar y ejecutar un vuelo "
            "sencillo cumpliendo las reglas de seguridad."
        ),
        "dirigido_a": "Personas sin experiencia previa en pilotaje.",
        "temario": (
            "Partes del drone, baterias y cuidados del equipo\n"
            "Normativa boliviana y espacio aereo\n"
            "Chequeo previo al vuelo y evaluacion del sitio\n"
            "Despegue, control manual y aterrizaje\n"
            "Modos de vuelo asistido y retorno automatico\n"
            "Practica de vuelo supervisada"
        ),
        "requisitos": (
            "Ninguna experiencia previa\n"
            "Documento de identidad vigente\n"
            "Ropa de campo para la practica"
        ),
        "incluye": (
            "Drone y baterias de la escuela para la practica\n"
            "Material de estudio digital\n"
            "Certificado de participacion"
        ),
        "equipo": "Drones multirrotor de la escuela.",
        "orden": 1,
        "destacado": True,
    },
    {
        "slug": "fotogrametria-y-mapeo",
        "nombre": "Fotogrametria y mapeo con drone",
        "nivel": "intermedio",
        "aplicacion": "fotogrametria",
        "resumen": "Planificar vuelos de mapeo y procesar ortomosaicos y modelos de elevacion.",
        "descripcion": (
            "Del plan de vuelo al entregable: como cubrir un area con "
            "solapamiento suficiente y que hacer despues con las imagenes.\n"
            "Se trabaja sobre un area real y cada participante procesa su "
            "propio levantamiento."
        ),
        "dirigido_a": "Topografos, ingenieros, arquitectos y tecnicos de campo.",
        "temario": (
            "Principios de fotogrametria aerea\n"
            "Planificacion de vuelo: altura, solapamiento y GSD\n"
            "Puntos de control en terreno\n"
            "Procesamiento: ortomosaico, nube de puntos y modelo de elevacion\n"
            "Control de calidad y precision del resultado\n"
            "Exportacion de entregables"
        ),
        "requisitos": (
            "Pilotaje basico o experiencia equivalente\n"
            "Computadora portatil propia"
        ),
        "incluye": (
            "Drone para el levantamiento de practica\n"
            "Datos de ejemplo para procesar\n"
            "Certificado de participacion"
        ),
        "orden": 2,
    },
    {
        "slug": "inspeccion-industrial-y-minera",
        "nombre": "Inspeccion industrial y minera con drone",
        "nivel": "avanzado",
        "aplicacion": "inspeccion",
        "resumen": "Levantamiento de estructuras, tajos y lineas con protocolo de seguridad.",
        "descripcion": (
            "Enfocado a operaciones donde el vuelo reemplaza trabajo en altura o "
            "en zona de riesgo: torres, naves, taludes y frentes de mina.\n"
            "Incluye el armado del protocolo de vuelo y del informe tecnico que "
            "recibe el cliente."
        ),
        "dirigido_a": "Personal tecnico de mineria, industria y servicios de mantenimiento.",
        "temario": (
            "Analisis de riesgo del sitio y permisos\n"
            "Planificacion de vuelos de inspeccion\n"
            "Captura sistematica de evidencia\n"
            "Vuelo en entorno confinado y con interferencia\n"
            "Elaboracion del informe tecnico\n"
            "Practica en escenario real"
        ),
        "requisitos": (
            "Pilotaje basico acreditado\n"
            "Equipo de proteccion personal para la practica"
        ),
        "incluye": (
            "Drone y sensores de la escuela\n"
            "Plantillas de protocolo e informe\n"
            "Certificado de participacion"
        ),
        "orden": 3,
    },
    {
        "slug": "agricultura-de-precision",
        "nombre": "Agricultura de precision con drone",
        "nivel": "intermedio",
        "aplicacion": "agricola",
        "resumen": "Monitoreo de cultivos, indices de vegetacion y mapas de manejo.",
        "descripcion": (
            "Como usar el drone para ver el estado del cultivo antes de que se "
            "note a simple vista y convertir esas imagenes en decisiones de "
            "riego y fertilizacion."
        ),
        "dirigido_a": "Productores, agronomos y tecnicos agricolas.",
        "temario": (
            "Camaras y sensores para agricultura\n"
            "Vuelo de monitoreo sobre parcela\n"
            "Indices de vegetacion e interpretacion\n"
            "Mapas de manejo por zonas\n"
            "Seguimiento a lo largo de la campana"
        ),
        "requisitos": "Pilotaje basico o experiencia equivalente",
        "incluye": (
            "Drone para la practica\n"
            "Material de estudio digital\n"
            "Certificado de participacion"
        ),
        "orden": 4,
    },
]
