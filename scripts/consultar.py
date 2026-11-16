"""Ejecutar un SELECT, mostrar su tiempo en segundos y, opcionalmente, exportar CSV."""
from pathlib import Path
from contextlib import closing
from comun import ROOT, dataset, db, pg, require_loaded, parser
from presentacion import ejecutar_consulta, exportar_csv, mostrar_tabla
import duckdb


def main(argv=None):
    p = parser(__doc__)
    p.add_argument('--motor', choices=['duckdb', 'postgresql', 'parquet'], required=True)
    p.add_argument('--archivo', type=Path, required=True, help='Archivo con un SELECT o WITH...SELECT.')
    p.add_argument('--csv', type=Path, help='Guardar todas las filas en un CSV nuevo dentro de resultados/.')
    a = p.parse_args(argv)
    query = a.archivo.read_text()
    statements = duckdb.extract_statements(query)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        p.error('El archivo debe contener exactamente un SELECT o WITH...SELECT.')
    target = a.csv.resolve() if a.csv else None
    if target:
        if not target.is_relative_to((ROOT / 'resultados').resolve()):
            p.error('--csv debe estar dentro de resultados/.')
        if target.exists():
            p.error('El CSV ya existe; elige otro nombre para conservarlo.')
    root = dataset(a.perfil)
    if a.motor == 'postgresql':
        c = pg()
    else:
        c = db(root, 'parquet' if a.motor == 'parquet' else 'tables')
    with closing(c):
        if a.motor != 'parquet':
            require_loaded(c, root, 'postgresql' if a.motor == 'postgresql' else 'duckdb')
        if a.motor == 'postgresql':
            c.execute('SET default_transaction_read_only=on')
        columns, rows, seconds = ejecutar_consulta(c, query)
        if target:
            exportar_csv(target, columns, rows)
            print(f'{len(rows)} filas exportadas a {target}')
        else:
            mostrar_tabla(columns, rows, limit=40)
        print(f'Tiempo: {seconds:.6f} s | Filas: {len(rows)}')


if __name__ == '__main__':
    main()
