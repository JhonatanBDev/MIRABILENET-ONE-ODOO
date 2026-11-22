# Claves maestras

Este archivo **no contiene las claves**. Explica qué son y cómo cuidarlas.

## Qué son

Dos contraseñas largas y aleatorias que viven en el servidor, fuera de la base de datos. Odoo
las usa para cifrar lo delicado antes de guardarlo. No las entrega el SIN ni nadie: son propias.

| Variable de entorno | Qué cifra | Módulo |
|---|---|---|
| `MIRA_SIAT_MASTER_KEY` | Token del SIN, CUIS y CUFD | `mira_sale_siat` |
| `MIRABILENET_MASTER_KEY` | Contraseñas de los routers y de las cuentas PPPoE | `mirabilenet_isp` |

Para qué sirven: si alguien se lleva una copia de la base de datos, sin la clave no puede leer
esos secretos.

## Tres reglas

1. **Se definen una vez y no se cambian.** Lo cifrado con una clave solo se abre con esa misma.
2. **Si se pierden, lo cifrado no se recupera.** Habría que volver a cargar el token del SIN y
   las contraseñas de los routers y de las cuentas PPPoE.
3. **No van en Git ni en la base de datos.** Se guardan en un gestor de contraseñas o en papel,
   en un lugar seguro.

## En este equipo (desarrollo)

Se crearon el 20/11/2026 en la computadora anterior y **se regeneraron el 21/11/2026** en la
computadora nueva (64 caracteres aleatorios cada una, variables de entorno del usuario de
Windows). Las de la computadora anterior quedaron descartadas; las bases no tenían ningún
secreto cifrado, así que no se perdió nada. Odoo las encuentra
solo en cada arranque; no hay que escribirlas.

Verlas para respaldarlas (PowerShell, en una terminal abierta después de crearlas):

```powershell
echo $env:MIRA_SIAT_MASTER_KEY
echo $env:MIRABILENET_MASTER_KEY
```

También están en: Configuración de Windows > «Editar las variables de entorno de esta cuenta».

Comprobar que existen sin mostrarlas:

```powershell
$env:MIRA_SIAT_MASTER_KEY.Length
$env:MIRABILENET_MASTER_KEY.Length
```

Una terminal que ya estaba abierta antes de crearlas no las ve: hay que abrir una nueva antes
de lanzar Odoo.

## En el VPS (producción)

El VPS tendrá **sus propias claves**, distintas de las de este equipo. Se definen en la fase 10,
en el archivo de entorno de Docker (fuera de Git) o como secretos del servidor.

Importante al migrar datos: los secretos cifrados en este equipo no se pueden leer en el VPS con
otra clave. El token del SIN y las contraseñas de los routers se cargan de nuevo en el VPS, o se
usa allí la misma clave con la que se cifraron.

## Si aparece un error

- «Falta la clave maestra…»: la variable no está definida en la sesión que lanzó Odoo. Abrir
  una terminal nueva o definirla.
- «El secreto no se puede descifrar…»: Odoo arrancó con una clave distinta de la que cifró ese
  dato.
