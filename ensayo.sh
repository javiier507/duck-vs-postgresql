#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-duckdb-postgresql-ensayo}"
command_name="${1:-ayuda}"
if [[ $# -gt 0 ]]; then shift; fi
help() {
  cat <<'HELP'
Uso: ./ensayo.sh COMANDO [opciones]
  preparar                 Comprobar Docker y DuckDB; construir herramientas.
  generar                  [--perfil ventas-2m] [--pedidos 2000000] [--semilla 42]
  importar                 --desde /ruta/dataset [--perfil ventas-2m]
  iniciar                  Iniciar PostgreSQL; no cargar ni generar.
  cargar-postgres           [--perfil ventas-2m] [--reemplazar]
  cargar-duckdb             [--perfil ventas-2m] [--reemplazar]
  verificar                [--perfil ventas-2m]
  consultar                Ejecutar un SQL y mostrar tiempo en segundos:
                           --motor duckdb|postgresql|parquet --archivo consulta.sql
                           [--perfil ventas-2m] [--csv resultados/reporte.csv]
  medir                    [--perfil ventas-2m] [--repeticiones 7] [--etiqueta baseline]
  planes                   [--perfil ventas-2m]
  estado                   [--perfil ventas-2m]
  psql                     Abrir sesion PostgreSQL en retail_bench.
  cerrar                   Eliminar contenedores/volumen del ensayo y TODAS sus bases DuckDB.
  destruir-datos           [--perfil ventas-2m] --confirmar (requiere cerrar primero).
  ayuda                    Mostrar esta ayuda.
Fuentes y resultados persisten al cerrar. Ninguna carga genera fuentes automaticamente.
HELP
}
case "$command_name" in ayuda|--help|-h) help; exit 0 ;; esac
case "$command_name" in
  preparar|generar|importar|iniciar|cargar-postgres|cargar-duckdb|verificar|consultar|medir|planes|estado|psql|cerrar|destruir-datos) ;;
  *) help >&2; exit 2 ;;
esac
command -v docker >/dev/null || { echo 'Falta Docker.' >&2; exit 1; }
docker compose version >/dev/null
# Una operacion por vez. Las conexiones graficas deben cerrarse antes de cargar/medir/limpiar.
if ! mkdir .ensayo.lock 2>/dev/null; then
  echo 'Hay otra operacion activa (.ensayo.lock). Si hubo un cierre forzado, verifica que no haya procesos antes de retirar ese directorio vacio.' >&2
  exit 1
fi
trap 'rmdir .ensayo.lock' EXIT
run_python() {
  docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" herramientas "$@"
}
case "$command_name" in
  preparar)
    command -v duckdb >/dev/null || { echo 'Falta instalar DuckDB CLI; consulta README.md.' >&2; exit 1; }
    docker info >/dev/null
    duckdb --version
    docker compose build herramientas
    ;;
  iniciar) docker compose up -d --wait postgres ;;
  generar) run_python scripts/generar_datos.py "$@" ;;
  importar)
    if [[ "${1:-}" != --desde || -z "${2:-}" ]]; then
      echo 'Uso: ./ensayo.sh importar --desde /ruta/dataset [--perfil ventas-2m]' >&2; exit 2
    fi
    import_dir="$(cd -- "$2" && pwd)"
    shift 2
    docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -v "$import_dir:/entrada:ro" herramientas scripts/importar_datos.py --desde /entrada "$@"
    ;;
  cargar-postgres) run_python scripts/cargar_postgresql.py "$@" ;;
  cargar-duckdb) run_python scripts/cargar_duckdb.py "$@" ;;
  verificar) run_python scripts/verificar_datos.py "$@" ;;
  consultar) run_python scripts/consultar.py "$@" ;;
  medir) run_python scripts/medir_consultas.py "$@" ;;
  planes) run_python scripts/explicar_consultas.py "$@" ;;
  estado)
    docker compose ps -a
    run_python scripts/estado.py "$@"
    ;;
  psql)
    if [[ -t 0 && -t 1 ]]; then
      docker compose exec -e PGOPTIONS='-c search_path=retail_bench,public' postgres psql -X -U bench -d bench "$@"
    else
      docker compose exec -T -e PGOPTIONS='-c search_path=retail_bench,public' postgres psql -X -U bench -d bench "$@"
    fi
    ;;
  cerrar)
    if [[ $# -ne 0 ]]; then echo 'cerrar no recibe opciones; afecta solo a este proyecto Compose y duckdb/.' >&2; exit 2; fi
    run_python scripts/limpiar.py duckdb
    docker compose down --volumes --remove-orphans
    ;;
  destruir-datos)
    if [[ -n "$(docker compose ps -aq)" ]] || [[ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME")" ]] || [[ -n "$(find duckdb -mindepth 1 ! -name .gitkeep -print -quit)" ]]; then
      echo 'Ejecuta ./ensayo.sh cerrar antes de destruir fuentes.' >&2; exit 1
    fi
    run_python scripts/limpiar.py datos "$@"
    ;;
esac
