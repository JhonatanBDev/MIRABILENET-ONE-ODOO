## Puesta en marcha

1. Variable de entorno `MIRABILENET_MASTER_KEY=<valor largo y aleatorio>` en el servidor, fuera
   de Git y de la base. Si se pierde, las contraseñas guardadas no se recuperan.
2. Parámetros del sistema (Ajustes > Técnico > Parámetros):

   | Parámetro | Qué es |
   |---|---|
   | `mirabilenet.platform_base_url` | Dirección a la que el router informa su enrolamiento. Debe ser la **IP**, no el dominio: el router valida el certificado contra la CA propia |
   | `mirabilenet.platform_ca_cn` | Nombre (CN) de esa CA |
   | `mirabilenet.platform_ca_pem_path` | Ruta del archivo de la CA en el servidor |
   | `mirabilenet.wg_endpoint_host` | Nombre o IP pública del concentrador WireGuard |
   | `mirabilenet.wg_config_dir` | Carpeta compartida con el servicio que aplica los peers; debe contener `hub_public.key` |
   | `mirabilenet.wg_mgmt_network`, `wg_listen_port`, `wg_worker_ip`, `enrollment_ttl_minutes`, `camera_supernet` | Ya traen su valor por defecto |
   | `mirabilenet.router_gateway` | `real` (por defecto) o `fake` para probar sin equipos |

3. El router informa su enrolamiento en `POST /api/v1/network/router-enrollment/complete`, la
   misma ruta del sistema anterior.
