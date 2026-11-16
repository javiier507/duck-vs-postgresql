# AGENTS.md

Guía para agentes y referencia técnica. El recorrido básico (requisitos, inicio rápido, consultas, cierre y glosario) está en [README.md](README.md) y aquí no se repite.

## 1. Instrucciones para agentes

- **«Carga los datos»:** sigue el [inicio rápido](README.md#3-inicio-rápido) hasta `estado`. Reutiliza las fuentes válidas, verifica ambos motores y entrega perfil, conteos, rutas y datos de conexión.
- **«Mide» o «compara»:** además ejecuta `medir`, conserva todas las muestras y explica los resultados por consulta. Una medición con resultados distintos entre motores no es una comparación válida.
- Valida siempre con `verificar` o `medir`, aunque el desarrollador ya haya explorado los datos.
- Al terminar, deja PostgreSQL activo y cierra tus conexiones DuckDB para que el desarrollador pueda explorar. No ejecutes `cerrar` ni `destruir-datos` hasta que te lo pidan.
- Ejecuta los comandos de uno en uno desde la carpeta del ensayo: `.ensayo.lock` rechaza operaciones simultáneas.
- Las rutas que imprimen los scripts empiezan por `/work/`, la carpeta del ensayo dentro del contenedor. Infórmalas como `./resultados/...`.
- Sin terminal interactiva, pasa el SQL a PostgreSQL por la entrada estándar: `echo 'SELECT COUNT(*) FROM items;' | ./ensayo.sh psql`.
- Si la variable `AI_AGENT` está definida, el CLI de DuckDB instalado (2.0) cambia a un formato de salida para agentes; añade `-no-agent` para obtener la salida normal.
- Duraciones de referencia con `ventas-2m`: unos 10 s por carga, 20 s `verificar`, 30 s `planes` y 2 min `medir`. Usa límites de tiempo de varios minutos.

## 2. Datos generados

Reglas de `scripts/generador.py`, que se repiten exactamente con la misma semilla y versión del generador:

- Clientes registrados en 2022; pedidos entre 2023 y 2025, con aproximadamente el 30 % concentrado en noviembre y diciembre.
- Distribución sesgada hacia los IDs bajos: pocos clientes y productos acumulan muchos pedidos.
- Aproximadamente el 5 % de los pedidos está cancelado; los completados se envían entre uno y cinco días después.
- Entre uno y cinco detalles por pedido, y entre una y cinco unidades por detalle.
- Aproximadamente el 20 % de los detalles tiene un 10 % de descuento, redondeado hacia abajo al centavo.
- El precio depende de la categoría y queda registrado en el momento de la compra.
- Ingreso = `quantity * unit_price_cents - discount_cents`, en centavos enteros. Los reportes excluyen los pedidos cancelados.

No se modelan impuestos, fletes, inflación ni devoluciones. La mezcla aritmética tiene correlaciones artificiales y no pretende parecerse estadísticamente a una tienda real.

Ambos cargadores usan tipos explícitos y crean los mismos índices después de importar: únicos por `id` y secundarios en `orders(customer_id, ordered_at)`, `items(order_id)` e `items(product_id)`. No hay claves foráneas ni restricciones NOT NULL; la integridad la comprueba `verificar`. Tener los mismos índices no garantiza los mismos planes de ejecución. La tabla `lab_metadata` guarda el hash del manifiesto cargado y no contiene datos del negocio.

### Importar fuentes de otra ubicación (opcional)

```bash
./ensayo.sh importar --desde /ruta/absoluta/al/dataset --perfil ventas-2m
```

La carpeta de origen debe contener `manifest.json` y los ocho archivos que declara; se verifican su tamaño y hash antes y después de copiar. Solo se copian las fuentes (ni bases, ni temporales, ni resultados), y la copia no depende de que el origen siga existiendo. Las fuentes están excluidas de git mediante `.gitignore`: tras clonar el proyecto, ejecuta `generar` o impórtalas.

## 3. Metodología e interpretación

`./ensayo.sh planes` exporta los planes de ejecución (`EXPLAIN ANALYZE`) de las seis consultas en los tres modos a `resultados/<perfil>/planes/`.

### Qué verifica

`verificar` termina con error si falla alguna comprobación; `medir` y `planes` la ejecutan antes de empezar.

- Los hashes de los ocho archivos coinciden con el manifiesto.
- Los conteos y los IDs únicos coinciden en los tres modos.
- No hay referencias a clientes, productos o pedidos inexistentes.
- Las fechas, cantidades e importes son válidos, y cada pedido tiene entre uno y cinco detalles.
- Las consultas de `consultas/` devuelven resultados idénticos en los tres modos, normalizando fechas y números.

No se comparan todas las celdas de todas las tablas. Si añades transformaciones, amplía la validación.

### Qué mide

- **Tiempo de pared de `execute` + `fetchall`:** incluye planificación, ejecución, transferencia y conversión de los resultados; excluye la conexión, la carga y los índices. PostgreSQL suma el viaje entre cliente y servidor, mientras que DuckDB se ejecuta dentro del mismo proceso. En consultas de milisegundos esa diferencia puede dominar.
- **Orden:** dos rondas de calentamiento y luego las medidas. Los pares consulta/modo se ordenan al azar con una semilla fija y se ejecutan de uno en uno. El hash de cada resultado se comprueba fuera del tiempo medido.
- **Caché caliente:** la validación ya leyó los datos y no se vacían las cachés del sistema. Ni la primera muestra ni reiniciar un contenedor garantizan caché fría.
- **Recursos:** 2 CPU y 2 GiB por contenedor.
  - DuckDB: 2 hilos y `memory_limit=1GB`.
  - PostgreSQL: `shared_buffers=256MB`, `work_mem=32MB`, hasta un trabajador paralelo por consulta y JIT desactivado.

  Estos ajustes no reservan la misma RAM por consulta: PostgreSQL asigna memoria por operación y `memory_limit` no limita toda la memoria del proceso DuckDB.
- **Cargas:** confirmación por sentencia, índices después de importar, ANALYZE y CHECKPOINT. Sus tiempos se guardan aparte en `carga_<motor>_<fecha>.json` y no pretenden ser la carga óptima de cada motor.
- **`--etiqueta`:** sigue las mismas reglas que un nombre de perfil.

### Interpretar

- Calcula la razón por consulta como indica el README y no la promedies para declarar un ganador universal. Pondera qué consultas necesita la aplicación, su frecuencia y variabilidad, el coste de preparación y el almacenamiento.
- No mezcles los tiempos de `EXPLAIN ANALYZE`, que instrumenta la consulta, con los de `medir`. En los planes de PostgreSQL (con buffers y ajustes, y `TIMING OFF` para reducir sobrecarga), observa si los recorridos son por índice o secuenciales, las cardinalidades, el paralelismo y los archivos temporales.
- La evidencia de cada perfil queda en `resultados/<perfil>/`: `validation.json` (última validación), `mediciones/` y `planes/`.
- Para obtener resultados comparables:
  - Mantén estables el equipo, la alimentación, el disco y los procesos activos.
  - Registra CPU, RAM, sistema operativo, arquitectura y límites de Docker (`docker compose config`).
  - `docker stats` muestra el consumo en vivo, pero el ensayo no registra el pico de RAM por consulta.
- En macOS/Docker Desktop, DuckDB lee un archivo montado desde el equipo y PostgreSQL un volumen dentro de la VM. Indica esa diferencia o usa Linux nativo. Para reconstrucciones inmutables, fija las imágenes por digest, porque las etiquetas Docker pueden actualizarse.

## 4. Referencia de comandos, carpetas y conexiones

```text
ensayo-duckdb-postgresql/
  README.md                 Punto de entrada del ensayo
  AGENTS.md                 Guía para agentes y referencia técnica
  TODO.md                   Mejoras pendientes
  ensayo.sh                 Comandos comunes, con ayuda y control de operación simultánea
  docker-compose.yml        PostgreSQL y ejecutor auxiliar aislados
  Dockerfile                Python y dependencias fijadas
  requirements.txt
  scripts/                  Generación, carga por motor, verificación, consultas, mediciones y limpieza
  tests/                    Pruebas aisladas de tiempos y presentación, sin bases ni Docker
  consultas/                SELECT editables usados por los tres modos
  datos/<perfil>/           CSV, Parquet y manifiesto persistentes
  duckdb/<perfil>/          DuckDB cargado y temporales descartables
  resultados/<perfil>/      Cargas, validaciones, mediciones y planes persistentes
```

`./ensayo.sh ayuda` lista todos los comandos y opciones. Los tests unitarios no necesitan Docker: `python3 -B -m unittest discover -s tests -v`.

### Uso directo de los scripts

Cada script de `scripts/` acepta `--help` y se ejecuta en el contenedor auxiliar, que no inicia PostgreSQL por sí mismo:

```bash
docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" herramientas scripts/cargar_duckdb.py --perfil ventas-2m
```

- `ensayo.sh` usa el directorio `.ensayo.lock` para impedir dos operaciones simultáneas; las conexiones externas no quedan cubiertas por ese bloqueo.
- No edites fuentes ni consultas mientras se ejecuta `verificar` o `medir`.
- El proyecto Docker se llama `duckdb-postgresql-ensayo` y PostgreSQL escucha en el puerto `55433`. Para cambiar el puerto, exporta `PG_PORT` antes de `iniciar`.
- Para ensayos simultáneos, usa otra copia de la carpeta con otros `COMPOSE_PROJECT_NAME` y `PG_PORT`, y no compartas `duckdb/`.

### Datos de conexión

| Campo | PostgreSQL | DuckDB |
| --- | --- | --- |
| Host / puerto | `127.0.0.1` / `55433` | No aplica: se abre como archivo |
| Base de datos | `bench` | Ruta absoluta a `duckdb/ventas-2m/analytics.duckdb` |
| Usuario / contraseña | `bench` / `bench_local` | No aplica |
| Esquema | `retail_bench` | `main` |

- PostgreSQL solo acepta conexiones desde el propio equipo y sin SSL.
- Para usar consultas sin prefijo de esquema, ejecuta `SET search_path=retail_bench,public;`. `./ensayo.sh psql` ya lo hace.
- En `psql`, `\timing on` muestra la duración de cada llamada. Son tiempos exploratorios, no comparables con los de `medir`.
- `duckdb -readonly duckdb/ventas-2m/analytics.duckdb < consultas/01_month_category.sql` ejecuta un archivo SQL. El CLI instalado puede ser de otra versión que la usada en las mediciones (1.4.3, dentro de Docker): ábrelo siempre con `-readonly`, o usa `./ensayo.sh consultar --motor duckdb` para trabajar en el mismo entorno.
- Cierra las sesiones DuckDB antes de cargar, medir o cerrar, porque el archivo queda bloqueado. Cierra también las exploraciones pesadas de PostgreSQL antes de medir.

## 5. Prueba pequeña y otros conjuntos de datos

Cualquier perfil sigue el recorrido del README añadiendo `--perfil` a cada comando. Por ejemplo, `smoke` comprueba una instalación en segundos; no sirve para sacar conclusiones de rendimiento:

```bash
./ensayo.sh generar --perfil smoke --pedidos 1000
./ensayo.sh iniciar
./ensayo.sh cargar-postgres --perfil smoke --reemplazar
./ensayo.sh cargar-duckdb --perfil smoke
./ensayo.sh verificar --perfil smoke
./ensayo.sh medir --perfil smoke --repeticiones 3 --etiqueta smoke
```

Para otro tamaño u otra distribución, cambia los parámetros de `generar`, por ejemplo `--perfil ventas-100k --pedidos 100000 --semilla 7`.

- El tamaño y la distribución los fijan `--pedidos` y `--semilla`, no el nombre del perfil. Clientes (100.000) y productos (10.000) son siempre los mismos.
- PostgreSQL guarda un solo perfil cargado, así que cambiar de perfil requiere `cargar-postgres --reemplazar`. DuckDB tiene un archivo por perfil.
- Para que `generar` reutilice un perfil existente, repite sus `--pedidos` y `--semilla`; con otros valores se detiene.
- Para comprobar que una regeneración es idéntica, compara los hashes de archivo de `manifest.json`, no el manifiesto completo: este incluye el tiempo de generación.
- Con 10 o 100 millones de pedidos no hay garantía de que el ensayo quepa en los límites predeterminados; vigila los recursos antes de ampliar.

## 6. Problemas comunes

| Problema | Acción |
| --- | --- |
| Docker no responde | Inicia Engine/Desktop y revisa los permisos del usuario |
| Falta DuckDB | Instala el CLI; `preparar` no modifica tu instalación |
| Puerto ocupado | Exporta otro `PG_PORT` antes de `iniciar` y actualiza tu cliente |
| Falta cargar o perfil incompatible | Inicia PostgreSQL y carga ambos motores con el mismo perfil; usa `--reemplazar` solo para sustituir una carga existente |
| Hash incorrecto | Investiga el archivo modificado; recupera las fuentes originales o destrúyelas y regenéralas explícitamente |
| Carga interrumpida | No se reconoce como completa; repítela con `--reemplazar` |
| Archivo DuckDB bloqueado | Cierra el CLI y cualquier conexión externa antes de cargar, medir o cerrar |
| `.ensayo.lock` tras un cierre forzado | Comprueba que no quede ningún comando activo y ejecuta `rmdir .ensayo.lock` |
| Falta memoria o salida 137 | El contenedor pudo terminar por falta de memoria (OOM); comprueba también el espacio temporal. Ajusta los recursos de ambos motores y usa una nueva etiqueta |
| Una consulta supera 10 minutos | El límite de tiempo de PostgreSQL hace fallar la serie. Revisa el plan, o cambia el límite y documenta la variante |
| DuckDB aparece vacío en un cliente | Comprueba que abres `duckdb/<perfil>/analytics.duckdb` y no otro archivo creado por error |
| `--csv` se rechaza | El archivo ya existe; elige otro nombre dentro de `resultados/` |
| Error de argumentos al pegar comandos con comentarios `#` en Zsh | Zsh interactivo no trata `#` como comentario por defecto; pega los comandos sin comentarios o activa `setopt interactivecomments` |

## 7. Resultados de referencia

Medición del 2026-11-15 con `ventas-2m` (`medir --repeticiones 7`). Sirve para saber qué orden de magnitud esperar, no como umbral de aceptación: los tiempos dependen del equipo.

**Entorno:** Linux x86_64 (Fedora, kernel 7.3), AMD Ryzen 7 7735U con 16 hilos y 14 GiB de RAM, Docker 29.9.3. Dentro de los contenedores: Python 3.12, DuckDB 1.4.3, PostgreSQL 17.6 y Psycopg 3.2.10, con los límites del [apartado 3](#qué-mide).

| Consulta | PostgreSQL (s) | DuckDB (s) | Parquet (s) | Razón PostgreSQL/DuckDB |
| --- | ---: | ---: | ---: | ---: |
| 01_month_category | 1,964 | 0,264 | 0,356 | 7,4 |
| 02_top_products | 1,523 | 0,234 | 0,323 | 6,5 |
| 03_top_customers | 1,859 | 0,279 | 0,342 | 6,7 |
| 04_month_change | 1,501 | 0,216 | 0,276 | 6,9 |
| 05_customer_history | 0,00056 | 0,0038 | 0,026 | 0,15 |
| 06_order_lookup | 0,00050 | 0,0015 | 0,0061 | 0,33 |

**Tamaños:** tablas e índices de PostgreSQL, 934 MiB (sin WAL ni catálogos); archivo DuckDB, 395 MiB; los cuatro Parquet, 42 MiB, sin índices.

**Reproducibilidad:** tras `cerrar` y reconstruir ambos motores desde las mismas fuentes, los resultados de las consultas fueron idénticos (mismo `validation.json`), las medianas variaron menos de un 4 % (salvo 05 sobre Parquet: +3 ms) y las razones se mantuvieron.

**Probado:** todos los comandos de `ensayo.sh`, el recorrido del README, la reutilización de fuentes y cargas, el rechazo de sobrescrituras y de parámetros distintos, `psql`, la lectura del archivo DuckDB desde el CLI 2.0 con `-readonly`, y los tests unitarios.

**No probado:** Windows/WSL, macOS e interfaces gráficas solo están documentados. El ensayo no mide concurrencia, escrituras, picos de RAM ni caché fría.

## 8. Fuentes técnicas

- [TODO.md](TODO.md): mejoras pendientes.
- Fuentes: [COPY PostgreSQL](https://www.postgresql.org/docs/17/sql-copy.html), [EXPLAIN](https://www.postgresql.org/docs/17/sql-explain.html), [configuración DuckDB 1.4](https://duckdb.org/docs/1.4/configuration/overview), [COPY Psycopg](https://www.psycopg.org/psycopg3/docs/basic/copy.html), [ciclo de volúmenes Docker](https://docs.docker.com/reference/cli/docker/compose/down/). Para una carga de trabajo estándar está [TPC-H](https://duckdb.org/docs/stable/core_extensions/tpch); este ensayo no es un resultado oficial TPC.
