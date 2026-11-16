# Ensayo práctico: DuckDB frente a PostgreSQL

## Índice

1. [Contexto y objetivos](#1-contexto-y-objetivos)
2. [Requisitos](#2-requisitos)
3. [Inicio rápido](#3-inicio-rápido)
4. [Probar las consultas y medir sus tiempos](#4-probar-las-consultas-y-medir-sus-tiempos)
5. [Cerrar, reconstruir o eliminar datos](#5-cerrar-reconstruir-o-eliminar-datos)
6. [Glosario](#6-glosario)
7. [Más información](#7-más-información)

## 1. Contexto y objetivos

Una tienda necesita reportes de ventas mensuales, productos populares y clientes con mayor gasto. También consulta pedidos individuales e historiales de clientes. Este ensayo permite probar esas tareas en primera persona con las mismas filas en PostgreSQL y DuckDB.

**Objetivo:** comparar seis consultas sobre 2 millones de pedidos y aproximadamente 6 millones de detalles de venta, además de clientes y productos.

**Los scripts preparan el terreno; tú ejecutas las consultas y evalúas los resultados.** Puedes seguir este README sin intervención de un agente.

### Qué se compara

PostgreSQL es un servidor orientado a filas, adecuado para aplicaciones y transacciones concurrentes. DuckDB es un motor embebido, que se ejecuta dentro del proceso de quien lo utiliza, orientado a analítica y almacenamiento por columnas. Ambos ejecutan SQL.

| Modo | Almacenamiento consultado |
| --- | --- |
| `postgresql` | Tablas internas e índices en un volumen Docker |
| `duckdb` en consultas / `duckdb_tables` en mediciones | Tablas internas e índices en `duckdb/<perfil>/analytics.duckdb` |
| `parquet` en consultas / `duckdb_parquet` en mediciones | Archivos Parquet de `datos/<perfil>/`, sin importación |

La comparación principal usa las tablas internas. Parquet es un flujo adicional con una preparación distinta. Se ejecuta una consulta por vez, sin usuarios simultáneos. Este ensayo no evalúa escrituras, replicación, disponibilidad ni una aplicación transaccional completa.

### Datos de prueba

| Tabla | Filas del perfil `ventas-2m` | Contenido |
| --- | ---: | --- |
| `customers` | 100.000 | Nombre, región y fecha de registro |
| `products` | 10.000 | Nombre, categoría y precio base |
| `orders` | 2.000.000 | Cliente, fecha, estado y envío |
| `items` | 5.999.982 con semilla 42 | Detalles: producto, cantidad, precio aplicado y descuento |

Relaciones: `customers → orders → items ← products`. Los importes se almacenan como enteros en centavos y los reportes excluyen los pedidos cancelados. Cómo se generan los datos se detalla en [AGENTS.md](AGENTS.md#2-datos-generados).

## 2. Requisitos

- Docker Engine/Desktop con Compose v2 y motor de contenedores Linux. Docker ejecutará PostgreSQL y las herramientas auxiliares en contenedores, procesos aislados con sus dependencias.
- DuckDB CLI, el programa de terminal para abrir archivos DuckDB. Comprueba `duckdb --version`; [instalación oficial](https://duckdb.org/docs/installation/).
- Terminal Bash o Zsh. En Windows, usa WSL2 con integración Docker y guarda el ensayo en el sistema de archivos Linux, no en `/mnt/c`.
- Para los 2 millones de pedidos del conjunto principal, aproximadamente 8 GB de RAM disponibles y 15 GB libres como reserva inicial. Los tamaños finales dependen del volumen de datos, las versiones y los índices.

No necesitas instalar Python, pip, PostgreSQL ni un cliente PostgreSQL en tu equipo. Las herramientas Python se ejecutan en un contenedor. Internet se necesita durante la construcción/descarga inicial; los datos se generan localmente mediante SQL.

**Abre una terminal en `ensayo-duckdb-postgresql/`, junto a este README y `ensayo.sh`.** Todos los comandos se ejecutan desde ahí.

## 3. Inicio rápido

Copia y ejecuta, en orden:

```bash
./ensayo.sh preparar
./ensayo.sh generar
./ensayo.sh iniciar
./ensayo.sh cargar-postgres
./ensayo.sh cargar-duckdb
./ensayo.sh verificar
./ensayo.sh estado
```

| Comando | Qué hace |
| --- | --- |
| `preparar` | Comprueba Docker y DuckDB y construye la imagen del contenedor auxiliar. Necesario la primera vez o tras modificar sus dependencias |
| `generar` | Crea `datos/ventas-2m/` con 2 millones de pedidos y semilla 42. Si las fuentes ya existen, solo verifica sus hashes y las reutiliza; ante archivos alterados o parámetros distintos se detiene sin reemplazarlos. Si tienes fuentes compatibles en otra carpeta, puedes [importarlas](AGENTS.md#importar-fuentes-de-otra-ubicación-opcional) en su lugar |
| `iniciar` | Levanta PostgreSQL y espera a que esté disponible |
| `cargar-postgres` / `cargar-duckdb` | Importan los CSV y construyen índices. Si ya existe una carga completa del mismo conjunto, la reutilizan |
| `verificar` | Comprueba archivos, relaciones y resultados equivalentes en los tres modos |
| `estado` | Muestra los conteos y qué motores tienen el conjunto cargado |

Ahora PostgreSQL queda funcionando y DuckDB disponible como archivo. Prueba una consulta en cada motor:

```bash
./ensayo.sh consultar --motor postgresql --archivo consultas/01_month_category.sql
./ensayo.sh consultar --motor duckdb --archivo consultas/01_month_category.sql
```

Opcionalmente, compara tiempos de forma repetida:

```bash
./ensayo.sh medir
```

Al terminar, cierra los clientes que tengan abierto el archivo DuckDB y ejecuta:

```bash
./ensayo.sh cerrar
```

`cerrar` elimina las bases cargadas y conserva las fuentes, reportes y mediciones. **La próxima sesión comienza en `iniciar`**, sin generar de nuevo.

Referencia en el equipo de prueba, con la imagen ya construida: generar 2 millones de pedidos tarda unos 5 s, las dos cargas unos 20 s, `verificar` unos 20 s y `medir` casi 2 minutos.

## 4. Probar las consultas y medir sus tiempos

Requiere ambos motores cargados y verificados ([inicio rápido](#3-inicio-rápido)). Los comandos usan el perfil predeterminado `ventas-2m`; para otro conjunto, añade `--perfil nombre` a cada ejecución.

### Las seis consultas

Los archivos de [consultas/](consultas/) se ejecutan sin cambios en los tres modos:

| Archivo | Qué evalúa |
| --- | --- |
| [01_month_category.sql](consultas/01_month_category.sql) | Ventas mensuales por categoría: joins y agrupación |
| [02_top_products.sql](consultas/02_top_products.sql) | Los veinte productos con más ingresos |
| [03_top_customers.sql](consultas/03_top_customers.sql) | Los veinte clientes con mayor gasto |
| [04_month_change.sql](consultas/04_month_change.sql) | Variación mensual mediante una función de ventana |
| [05_customer_history.sql](consultas/05_customer_history.sql) | Últimos pedidos de un cliente: búsqueda selectiva |
| [06_order_lookup.sql](consultas/06_order_lookup.sql) | Detalles del pedido 42: búsqueda por ID |

### Probar una consulta y ver su tiempo

```bash
./ensayo.sh consultar --motor postgresql --archivo consultas/01_month_category.sql
./ensayo.sh consultar --motor duckdb --archivo consultas/01_month_category.sql
./ensayo.sh consultar --motor parquet --archivo consultas/01_month_category.sql
```

`--motor` elige dónde ejecutar y `--archivo` señala el SQL. Sustituye el archivo por cualquiera de los otros cinco para probarlo del mismo modo. Cada llamada muestra el resultado y termina con:

```text
Tiempo: <segundos> s | Filas: <cantidad>
```

El tiempo tiene seis decimales e incluye ejecutar el SQL y obtener **todas sus filas**; excluye abrir la conexión, imprimir y exportar. La pantalla muestra hasta 40 filas, pero se obtienen todas para medir el mismo trabajo en los tres modos. Para explorar tablas grandes con SQL propio, utiliza `LIMIT`.

Es una observación individual: el tiempo puede variar entre llamadas y no aplica un calentamiento previo. Para comparar medianas bajo un procedimiento repetible, utiliza `medir`.

### Ejecutar las seis una por una

Este bucle muestra el archivo y el motor antes de cada ejecución. Ejecuta 18 llamadas secuenciales, cada una con su resultado y duración:

```bash
for archivo in consultas/*.sql; do
  for motor in postgresql duckdb parquet; do
    printf '\nConsulta: %s | Motor: %s\n' "$archivo" "$motor"
    ./ensayo.sh consultar --motor "$motor" --archivo "$archivo" || break 2
  done
done
```

### Repetir y comparar medianas

```bash
./ensayo.sh medir --repeticiones 7 --etiqueta comparacion
```

El comando verifica la integridad y la igualdad de resultados, ejecuta dos rondas de calentamiento y siete medidas por consulta y modo, y muestra una tabla de **medianas en segundos** con columnas PostgreSQL, DuckDB y Parquet. `--repeticiones` cuenta solo las rondas medidas (mínimo tres; por defecto siete); `--etiqueta` identifica la ejecución, sin cambiar los datos (por defecto `baseline`).

Al terminar indica la carpeta creada en `resultados/ventas-2m/mediciones/<fecha>_comparacion/`:

| Archivo | Para qué sirve |
| --- | --- |
| `summary.csv` | Mediana, mínimo y máximo por consulta y modo; columnas `median_ms`, `min_ms` y `max_ms` en **milisegundos** |
| `raw.csv` | Cada tiempo individual en la columna `ms`, con su ronda y fase |
| `environment.json` | Versiones, configuración y SQL exacto utilizado |
| `sizes.json` | Tamaños de las bases y los archivos Parquet |

La consola convierte los tiempos a segundos; los CSV conservan milisegundos por compatibilidad. Para convertirlos, divide entre 1.000. Con seis consultas y tres modos obtendrás 18 filas de resumen y 162 muestras: 36 de calentamiento y 126 medidas.

Una ejecución individual de `consultar` y una mediana de `medir` no son equivalentes: esta última incluye validación, calentamiento y repeticiones.

Para comparar, calcula por consulta `razón = mediana_postgresql_ms / mediana_duckdb_tables_ms`. Un valor mayor que uno indica menor tiempo en DuckDB; menor que uno, en PostgreSQL. Compara Parquet por separado. La metodología completa y cómo interpretar las diferencias están en [AGENTS.md](AGENTS.md#3-metodología-e-interpretación).

### Exportar el resultado de una consulta

Para guardar todas las filas de la primera consulta, con sus encabezados:

```bash
./ensayo.sh consultar --motor duckdb --archivo consultas/01_month_category.sql --csv resultados/consulta01_duckdb.csv
```

También muestra el tiempo en segundos, excluyendo la escritura del CSV. El destino debe estar dentro de `resultados/` y **no puede existir previamente**: para repetir la exportación, usa otro nombre. Puedes exportar cualquier otro SQL de la tabla y utilizar los otros motores. Los ingresos de estas consultas se expresan en centavos.

### Rutas que muestran los comandos

Los scripts se ejecutan dentro de un contenedor donde la carpeta del ensayo está montada en `/work`. Por eso `medir`, `planes` y las exportaciones muestran rutas como `/work/resultados/...`: en tu equipo corresponden a `./resultados/...`.

### Explorar con SQL propio

```bash
./ensayo.sh psql
duckdb -readonly duckdb/ventas-2m/analytics.duckdb
```

`./ensayo.sh psql` abre PostgreSQL con el esquema ya seleccionado (`\q` para salir). El CLI de DuckDB abre la base sin modificarla (`.quit` para salir); cierra esa sesión antes de cargar, medir o cerrar. Los datos de conexión para clientes externos y más detalles están en [AGENTS.md](AGENTS.md#datos-de-conexión).

## 5. Cerrar, reconstruir o eliminar datos

### Cerrar la sesión y liberar las bases

```bash
./ensayo.sh cerrar
```

Este comando elimina **los contenedores y el volumen PostgreSQL de este proyecto**, además de todos los archivos DuckDB y temporales de `duckdb/`, de todos los perfiles. Conserva `datos/` y `resultados/`. No ejecuta `docker system prune` ni limpia otros proyectos.

Los datos cargados son descartables **mediante este comando**. Ejecutar directamente `docker compose stop` conserva contenedores y volumen; `docker compose down` tampoco elimina volúmenes por defecto. No se usa RAM como disco ni se promete borrado automático al detener Docker Desktop. Para completar la limpieza después de un apagado, ejecuta `cerrar`.

### Reconstruir sin regenerar

```bash
./ensayo.sh iniciar
./ensayo.sh cargar-postgres
./ensayo.sh cargar-duckdb
./ensayo.sh verificar
```

Es el mismo procedimiento cada vez: ambos motores se alimentan de las fuentes existentes. No requiere agentes ni llamadas a modelos. **Iniciar y cargar no generan archivos fuente automáticamente.**

PostgreSQL mantiene un solo perfil cargado por proyecto Compose. Para cambiarlo durante una sesión o reconstruir una base existente, usa su cargador con `--reemplazar`: esta opción autoriza sustituir la carga, no los archivos fuente. DuckDB puede tener un archivo por perfil. El reemplazo afecta al esquema dedicado PostgreSQL o a las cuatro tablas del archivo DuckDB del perfil. No apuntes los scripts a una base de aplicación.

### Eliminar las fuentes explícitamente

```bash
./ensayo.sh cerrar
./ensayo.sh destruir-datos --perfil ventas-2m --confirmar
```

`--perfil ventas-2m` selecciona las fuentes que se borran y `--confirmar` hace explícita esa intención; sin esta opción el comando se rechaza. Solo borra `datos/ventas-2m/`; exige cerrar primero y conserva mediciones/reportes. Para recuperar las fuentes después tendrás que importarlas o generarlas de nuevo. Los resultados ocupan disco hasta que tú decidas borrarlos desde el explorador o la terminal.

| Operación | Fuentes | Bases cargadas | Resultados |
| --- | --- | --- | --- |
| `generar` con perfil idéntico existente | Verifica/reutiliza | No cambia | No cambia |
| `cargar-*` con carga idéntica | No cambia | Reutiliza | Conserva |
| `cargar-* --reemplazar` | No cambia | Sustituye el motor seleccionado | Añade evidencia de carga |
| `cerrar` | Conserva | Elimina las de este ensayo | Conserva |
| `destruir-datos --confirmar` | Elimina el perfil solicitado | Deben estar cerradas | Conserva |

Las imágenes Docker construidas/descargadas, que contienen los programas y sus dependencias, también ocupan disco y se conservan para repetir sin descargarlas. Mientras la sesión está abierta, las bases y el registro de cambios de PostgreSQL (WAL) sí ocupan espacio adicional; al cerrarla, sus copias se eliminan. Las fuentes, reportes e imágenes son el almacenamiento persistente esperado.

## 6. Glosario

### Términos

| Término | Significado |
| --- | --- |
| **Archivos fuente** | Datos de prueba en CSV (texto tabular) y Parquet (formato comprimido por columnas): cuatro de cada uno. Ambos motores cargan los mismos CSV; DuckDB también puede leer directamente los Parquet. Se conservan y reutilizan para reconstruir las bases cuantas veces necesites |
| **Manifiesto** | `manifest.json`: parámetros, conteos y hashes SHA-256 de los archivos fuente, para detectar cambios |
| **Cargar** | Importar los archivos fuente a una base consultable y construir sus índices |
| **Índice** | Estructura que ayuda a localizar filas sin recorrer toda la tabla |
| **Esquema** | Agrupa tablas dentro de una base: `retail_bench` en PostgreSQL y `main` en DuckDB |
| **Perfil** (`--perfil`) | Nombre elegido por ti para organizar un conjunto de datos, su carga y sus resultados; no hay un catálogo cerrado y el nombre no determina su tamaño. Por defecto `ventas-2m` (2 millones de pedidos, semilla 42). Admite de 1 a 64 caracteres: A–Z, a–z, números, `-` o `_`, comenzando por letra o número (por ejemplo `ventas-100k`, `prueba_local`). Para otro conjunto, repite `--perfil nombre` en cargas, consultas y mediciones: omitirlo vuelve a seleccionar `ventas-2m` |
| **`--pedidos`** | Filas de `orders` que genera `generar`. Por defecto `2000000`; enteros entre `100` y `100000000`, sin abreviaturas como `2m`. No es el total de filas: se añaden 100.000 clientes, 10.000 productos y entre uno y cinco detalles por pedido. Los límites admitidos no garantizan que cualquier tamaño quepa en tu equipo |
| **`--semilla`** | Distribución de clientes, productos, fechas y descuentos en `generar`. Por defecto `42`; enteros entre `0` y `1000000`. Con los mismos parámetros y versión del generador se repiten exactamente los mismos datos; cambiarla produce otra distribución con el mismo número de pedidos |
| **Modo / motor** | Dónde se ejecuta una consulta: `postgresql`, `duckdb` (tablas internas) o `parquet` (DuckDB sobre los Parquet) |
| **Benchmark** | Prueba repetida de rendimiento; aquí, el comando `medir` |
| **Calentamiento** | Rondas que se ejecutan antes de medir y se excluyen del resumen |
| **Mediana** | Valor central de las rondas medidas; menos sensible a valores extremos que la media |
| **Tiempo de pared** | Tiempo transcurrido que percibe el cliente: desde enviar la consulta hasta obtener todas sus filas |
| **Caché caliente** | Los datos ya se leyeron antes y pueden estar en memoria, lo que acelera las lecturas siguientes. Las mediciones del ensayo son con caché caliente |

### Archivos y carpetas

| Ubicación | Contenido | Al ejecutar `cerrar` |
| --- | --- | --- |
| `datos/<perfil>/` | CSV, Parquet y `manifest.json` | Se conserva |
| `duckdb/<perfil>/analytics.duckdb` | Base DuckDB creada por `cargar-duckdb` | Se elimina |
| Volumen Docker `pgdata` | Base PostgreSQL cargada por `cargar-postgres`; Docker administra estos archivos fuera de `duckdb/` | Se elimina |
| `resultados/<perfil>/` | Reportes, verificaciones y mediciones | Se conserva |

En las rutas, `<perfil>` se sustituye por `ventas-2m` o por el nombre que elijas.

## 7. Más información

- [AGENTS.md](AGENTS.md): instrucciones para agentes, detalle de la generación de datos, metodología e interpretación, referencia de comandos y conexiones, prueba pequeña y otros conjuntos de datos, problemas comunes y resultados de referencia.
- `./ensayo.sh ayuda` muestra todos los comandos y opciones.
