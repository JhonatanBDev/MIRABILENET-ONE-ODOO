"""Contenido inicial del sitio público.

Copiado del sistema anterior (seed_web y cargar_documentos_legales). Son textos genéricos: no traen datos de
contacto, cifras, fechas, cupos ni precios.
"""
SERVICIOS = [
    {
        "slug": "internet-hogar",
        "nombre": "Internet para el hogar",
        "icono": "hogar",
        "resumen": "Conexion estable para navegar, estudiar, trabajar y ver streaming en casa.",
        "descripcion": (
            "Instalamos el servicio en su domicilio con equipo propio y lo dejamos "
            "funcionando el mismo dia de la visita.\n"
            "El router queda en comodato y el soporte lo atiende personal local, "
            "sin centros de llamadas externos."
        ),
        "beneficios": (
            "Instalacion y configuracion incluidas\n"
            "Router en comodato\n"
            "Soporte tecnico local\n"
            "Sin limite de descarga"
        ),
        "destacado": True,
        "orden": 1,
    },
    {
        "slug": "internet-empresas",
        "nombre": "Internet para empresas",
        "icono": "empresa",
        "resumen": "Ancho de banda dimensionado a su operacion, con atencion prioritaria.",
        "descripcion": (
            "Evaluamos cuantos equipos y usuarios se conectan y que aplicaciones "
            "necesitan prioridad, y dimensionamos el enlace en consecuencia.\n"
            "Incluye seguimiento del enlace y atencion prioritaria ante incidencias."
        ),
        "beneficios": (
            "Ancho de banda dimensionado a medida\n"
            "IP fija disponible\n"
            "Atencion prioritaria\n"
            "Informe de disponibilidad del enlace"
        ),
        "destacado": True,
        "orden": 2,
    },
    {
        "slug": "videovigilancia",
        "nombre": "Videovigilancia administrada",
        "icono": "camara",
        "resumen": "Camaras IP con acceso remoto seguro, sin exponer nada a internet.",
        "descripcion": (
            "Instalamos camaras y grabadores en una red separada y el acceso remoto "
            "viaja siempre por una conexion privada cifrada.\n"
            "Ninguna camara ni grabador queda publicado en internet, y cada usuario "
            "ve unicamente las camaras que se le autorizan."
        ),
        "beneficios": (
            "Camaras en red separada\n"
            "Acceso remoto por conexion cifrada\n"
            "Permisos por sede y por camara\n"
            "Registro de quien accede al video"
        ),
        "destacado": True,
        "orden": 3,
    },
    {
        "slug": "conectividad-comunidades",
        "nombre": "Conectividad para comunidades",
        "icono": "comunidad",
        "resumen": "Llevamos internet a zonas donde los operadores grandes no llegan.",
        "descripcion": (
            "Trabajamos con juntas vecinales y organizaciones comunitarias para "
            "evaluar la factibilidad tecnica y definir un esquema viable.\n"
            "Priorizamos las zonas segun la cantidad de solicitudes recibidas."
        ),
        "beneficios": (
            "Estudio de factibilidad en la zona\n"
            "Instalacion progresiva por sectores\n"
            "Coordinacion con la organizacion local"
        ),
        "destacado": True,
        "orden": 4,
    },
    {
        "slug": "enlaces-mineria",
        "nombre": "Enlaces para mineria e industria",
        "icono": "mina",
        "resumen": "Conectividad en operaciones alejadas, con equipamiento adecuado al entorno.",
        "descripcion": (
            "Diseñamos el enlace segun la distancia, el terreno y las condiciones "
            "del lugar, con proteccion electrica y montaje apropiados.\n"
            "Se puede combinar con videovigilancia y control de accesos."
        ),
        "beneficios": (
            "Estudio de trayecto y linea de vista\n"
            "Proteccion electrica y puesta a tierra\n"
            "Mantenimiento programado"
        ),
        "orden": 5,
    },
    {
        "slug": "soporte-mantenimiento",
        "nombre": "Soporte y mantenimiento",
        "icono": "soporte",
        "resumen": "Atencion tecnica, mantenimiento preventivo y revision de instalaciones.",
        "descripcion": (
            "Atendemos incidencias del servicio y realizamos mantenimiento "
            "preventivo de cableado, equipos y camaras.\n"
            "Cada visita queda registrada con lo que se hizo y el material utilizado."
        ),
        "beneficios": (
            "Atencion por WhatsApp, telefono o correo\n"
            "Mantenimiento preventivo programado\n"
            "Registro de cada visita tecnica"
        ),
        "orden": 6,
    },
]

PREGUNTAS = [
    ("instalacion", "Cuanto tarda la instalacion?",
     "Primero hacemos una visita de factibilidad para verificar que haya senal o "
     "linea de vista en su domicilio. Si es factible, coordinamos la instalacion "
     "segun la agenda tecnica de la zona."),
    ("instalacion", "La instalacion tiene costo?",
     "La visita de factibilidad no tiene costo. La instalacion se cotiza segun la "
     "distancia, el material y el equipo necesario; el presupuesto se entrega "
     "antes de iniciar el trabajo."),
    ("instalacion", "El router es mio?",
     "El router se entrega en comodato mientras dure el servicio y se devuelve al "
     "dar de baja. Si prefiere usar equipo propio, evaluamos la compatibilidad."),
    ("servicio", "La velocidad contratada es garantizada?",
     "La velocidad del plan es la maxima disponible y se comparte entre todos los "
     "equipos conectados en el domicilio. El rendimiento tambien depende de la "
     "cantidad de dispositivos y de la calidad de la red interna."),
    ("servicio", "Puedo cambiar de plan?",
     "Si. El cambio de plan se solicita al equipo comercial y se aplica en el "
     "siguiente periodo de cobro."),
    ("servicio", "Que pasa si me mudo?",
     "Se evalua la factibilidad en la nueva direccion. Si hay cobertura, se "
     "coordina el traslado del servicio; puede tener un costo segun el trabajo "
     "necesario."),
    ("pagos", "Como puedo pagar?",
     "Se puede pagar en oficina, por transferencia bancaria o por QR. Cada pago "
     "recibe un recibo numerado emitido por el sistema."),
    ("pagos", "El recibo es una factura?",
     "El recibo que emite el sistema es un comprobante interno de pago y no "
     "constituye una factura fiscal. Si necesita factura, indiquelo al momento "
     "de contratar para gestionarla por el canal correspondiente."),
    ("pagos", "Que pasa si me atraso en el pago?",
     "Hay un periodo de gracia despues de la fecha de vencimiento. Superado ese "
     "plazo el servicio puede suspenderse, y se reactiva una vez registrado y "
     "aprobado el pago."),
    ("camaras", "Puedo ver mis camaras desde el celular?",
     "Si. El acceso se hace desde el portal con su usuario, y solo ve las camaras "
     "que se le autorizaron. Las credenciales de las camaras nunca se entregan ni "
     "se exponen."),
    ("camaras", "Las grabaciones quedan en la nube?",
     "Por defecto la grabacion queda en el equipo instalado en su domicilio o "
     "empresa. El almacenamiento en la nube se ofrece como servicio adicional."),
    ("soporte", "Como reporto una falla?",
     "Puede escribirnos por WhatsApp, llamar o abrir un ticket desde el portal de "
     "clientes. Cada reporte queda registrado con su seguimiento."),
]


VENTAJAS = [
    {
        "icono": "herramienta",
        "titulo": "Instalacion profesional",
        "detalle": "Equipos propios y tecnicos capacitados.",
        "orden": 1,
    },
    {
        "icono": "soporte",
        "titulo": "Soporte local",
        "detalle": "Atencion rapida, personalizada y cerca suyo.",
        "orden": 2,
    },
    {
        "icono": "antena",
        "titulo": "Cobertura en expansion",
        "detalle": "Llegamos a mas comunidades y zonas rurales cada dia.",
        "orden": 3,
    },
]

AVISO = """MIRABILENET recopila los datos personales que usted proporciona en los formularios de este sitio con una unica finalidad: responder su consulta y, si corresponde, elaborar una propuesta de servicio.

Datos que recopilamos: nombre, telefono, correo electronico, localidad y el mensaje que usted escriba. Ademas se registran la direccion IP y el navegador desde el que se envio el formulario, como medida de seguridad frente a envios automatizados.

Uso de los datos: los datos se utilizan para contactarle, evaluar la factibilidad tecnica en su domicilio y dar seguimiento comercial. No se venden, ceden ni comparten con terceros con fines publicitarios.

Conservacion: los datos se conservan mientras dure la relacion comercial o hasta que usted solicite su eliminacion.

Sus derechos: puede solicitar el acceso, la correccion o la eliminacion de sus datos escribiendo a nuestro correo de contacto. Atenderemos la solicitud en un plazo razonable.

Videovigilancia: cuando MIRABILENET instala camaras para un cliente, el responsable del tratamiento de las imagenes es el propio cliente. MIRABILENET provee la infraestructura y el acceso, y registra quien visualiza o descarga el video con fines de auditoria.

Cambios: este aviso puede actualizarse. La version vigente es siempre la publicada en esta pagina."""

PRIVACIDAD = """\
# Quienes somos
MIRABILENET presta servicios de internet y videovigilancia. Este aviso explica
que datos suyos tratamos, para que, y que puede pedirnos sobre ellos.
Los datos de contacto para cualquier asunto de este aviso estan al pie del sitio.

# Que datos tratamos
Distinguimos tres situaciones, porque en cada una tratamos cosas distintas.
- Si solo navega el sitio: no le pedimos ningun dato. Ver la politica de cookies.
- Si nos escribe por el formulario: nombre, telefono, correo si lo deja,
  localidad y el mensaje que escriba. Tambien guardamos la direccion IP desde la
  que se envio y la fecha, para poder frenar el envio automatizado.
- Si contrata el servicio: ademas de lo anterior, documento de identidad,
  direccion de instalacion, datos del equipo instalado, los pagos que realiza y
  los registros tecnicos de su conexion.

# Videovigilancia
Cuando instalamos camaras, las imagenes son suyas: quedan en su equipo o en el
almacenamiento que usted contrate. Nuestro personal accede a ellas unicamente
para instalar o reparar, a su pedido, y no las conservamos ni las cedemos.

# Para que los usamos
- Responder su consulta y prepararle una propuesta.
- Prestar y mantener el servicio contratado.
- Cobrar y llevar la contabilidad que la ley nos exige.
- Avisarle de cortes, mantenimientos y vencimientos.
No usamos sus datos para publicidad de terceros ni los vendemos.

# Con quien los compartimos
Con nadie, salvo dos casos: cuando una autoridad competente lo requiera por la
via legal, y con los proveedores que necesitamos para operar (por ejemplo, quien
aloja nuestros servidores), que solo pueden tratarlos siguiendo nuestras
instrucciones.

# Cuanto los conservamos
Las consultas del formulario que no derivan en contrato se eliminan al ano.
Los datos de clientes se conservan mientras dure la relacion y despues el tiempo
que exijan las obligaciones contables y tributarias.

# Que puede pedirnos
Puede pedirnos acceder a sus datos, corregirlos si estan mal, o que los
eliminemos cuando ya no sean necesarios. Escriba a la direccion del pie del
sitio y le respondemos. Si no queda conforme, puede acudir a la autoridad
competente.

# Como los protegemos
El sitio y el panel viajan cifrados. Los datos sensibles se guardan cifrados en
la base. El acceso del personal esta limitado por su funcion y queda registrado.

# Cambios
Si cambiamos este aviso publicaremos la version nueva aqui, con su fecha. La
fecha de la version vigente aparece al final de esta pagina.
"""

COOKIES = """\
# Que es una cookie
Es un archivo pequeno que un sitio guarda en su navegador para reconocerlo entre
una pagina y la siguiente.

# Que usamos nosotros
Este sitio usa **una sola cookie**, y es imprescindible para que el formulario
de contacto funcione con seguridad. No usamos cookies de publicidad, ni de
analitica, ni de redes sociales.

# Por que no le pedimos que acepte
Las cookies estrictamente necesarias no requieren su consentimiento: sin ellas
el sitio no puede hacer lo que usted le pidio. Como no ponemos ninguna otra, no
tendria sentido mostrarle un boton de aceptar o rechazar que en realidad no
cambiaria nada. Preferimos decirle cuales son.

# Sin recursos de terceros
Las tipografias, los iconos y las imagenes se sirven desde nuestro propio
dominio. Al abrir el sitio su navegador no contacta con Google, Facebook ni
ningun otro servicio, asi que ninguno de ellos puede ponerle una cookie desde
aqui.

# Si entra al panel
Quien administra la plataforma recibe ademas las cookies de sesion
necesarias para mantenerlo identificado. Se detallan en la tabla de abajo.

# Como borrarlas
Cualquier navegador permite ver y borrar las cookies de un sitio desde sus
ajustes de privacidad. Si borra la nuestra, el formulario de contacto pedira
recargar la pagina antes de enviarse.
"""

TERMINOS = """\
# Objeto
Estas condiciones regulan el uso de este sitio web. La prestacion del servicio
de internet o de videovigilancia se rige por el contrato que se firma aparte.

# Uso del sitio
El sitio es informativo. Puede consultarlo libremente y escribirnos por el
formulario. No esta permitido usarlo para enviar contenido ilicito, intentar
acceder a partes restringidas, ni automatizar envios masivos del formulario.

# Informacion publicada
Cuidamos que los planes, precios y coberturas publicados esten al dia, pero
pueden cambiar. La informacion del sitio es orientativa: la oferta en firme es
la que le entregamos por escrito tras evaluar la factibilidad en su domicilio.

# Cobertura y factibilidad
Que una localidad aparezca en la pagina de cobertura no garantiza que su
domicilio concreto sea factible. La factibilidad se confirma con una visita.

# Propiedad
La marca, el logotipo y los contenidos de este sitio son de MIRABILENET. Las
marcas de los fabricantes de equipos que mencionamos pertenecen a sus titulares.

# Enlaces
Si enlazamos a un sitio ajeno, no respondemos por su contenido.

# Ley aplicable
Estas condiciones se rigen por la legislacion del Estado Plurinacional de
Bolivia.
"""

DOCUMENTOS = [
    ("privacidad", "Aviso de privacidad",
     "Que datos suyos tratamos, para que, y que puede pedirnos sobre ellos.",
     PRIVACIDAD),
    ("cookies", "Politica de cookies",
     "Este sitio usa una sola cookie y no carga nada de terceros.",
     COOKIES),
    ("terminos", "Condiciones de uso",
     "Las reglas de uso de este sitio. El servicio se rige por su contrato.",
     TERMINOS),
]
