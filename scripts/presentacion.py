"""Cronometraje y presentación sin dependencias de los motores SQL."""
import csv
import time


def ejecutar_consulta(connection, query):
    """Medir execute + fetchall una vez; excluir metadatos y presentación."""
    started = time.perf_counter_ns()
    cursor = connection.execute(query)
    rows = cursor.fetchall()
    seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    columns = [column[0] for column in cursor.description]
    return columns, rows, seconds


def mostrar_tabla(columns, rows, limit=None):
    visible = rows if limit is None else rows[:limit]
    cells = [["NULL" if value is None else str(value) for value in row] for row in visible]
    widths = [max([len(column)] + [len(row[i]) for row in cells]) for i, column in enumerate(columns)]
    print(" | ".join(column.ljust(width) for column, width in zip(columns, widths)))
    print("-+-".join("-" * width for width in widths))
    for row in cells:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))
    if limit is not None and len(rows) > limit:
        print(f'Mostrando {limit} de {len(rows)} filas; usa --csv para exportar todas.')


def exportar_csv(target, columns, rows):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


def mostrar_resumen(summary, queries):
    """Convertir solo la presentación; los CSV conservan sus columnas en ms."""
    lookup = {(row['query'], row['mode']): row['median_ms'] for row in summary}
    modes = ['postgresql', 'duckdb_tables', 'duckdb_parquet']
    rows = [[query] + [f"{lookup[query, mode] / 1000:.6f}" for mode in modes] for query in queries]
    print('Medianas en segundos (s):')
    mostrar_tabla(['Consulta', 'PostgreSQL (s)', 'DuckDB (s)', 'Parquet (s)'], rows)
