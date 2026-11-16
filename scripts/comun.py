"""Esquema, entradas verificadas y conexiones compartidas del ensayo."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import statistics
import time
from decimal import Decimal

import duckdb
import psycopg
from presentacion import ejecutar_consulta, mostrar_resumen

ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    'customers': 'id BIGINT, name VARCHAR, region VARCHAR, registered_at DATE',
    'products': 'id BIGINT, name VARCHAR, category VARCHAR, base_price_cents BIGINT',
    'orders': 'id BIGINT, customer_id BIGINT, ordered_at DATE, status VARCHAR, shipped_at DATE',
    'items': 'id BIGINT, order_id BIGINT, product_id BIGINT, quantity INTEGER, unit_price_cents BIGINT, discount_cents BIGINT',
}
KEYS = [f'CREATE UNIQUE INDEX {t}_pk ON {t}(id)' for t in TABLES]
INDEXES = [
    'CREATE INDEX orders_customer_date ON orders(customer_id, ordered_at)',
    'CREATE INDEX items_order ON items(order_id)',
    'CREATE INDEX items_product ON items(product_id)',
]
QUERIES = {p.stem: p.read_text() for p in sorted((ROOT / 'consultas').glob('*.sql'))}
if not QUERIES:
    raise RuntimeError('Faltan los archivos SQL de consultas/.')
for name, query in QUERIES.items():
    statements = duckdb.extract_statements(query)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise RuntimeError(f'{name}: se requiere un SELECT o WITH...SELECT.')


def safe_name(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', value):
        raise argparse.ArgumentTypeError('Usa 1 a 64 letras, numeros, guiones o guiones bajos.')
    return value


def parser(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument('--perfil', type=safe_name, default='ventas-2m')
    return p


def dataset(profile):
    safe_name(profile)
    target = ROOT / 'datos' / profile
    if target.is_symlink() or target.resolve().parent != (ROOT / 'datos').resolve():
        raise RuntimeError('El perfil debe ser un directorio local dentro de datos/.')
    return target


def base(root):
    path = ROOT / 'duckdb' / root.name
    if path.is_symlink():
        raise RuntimeError('No se permiten enlaces simbolicos en duckdb/.')
    path.mkdir(parents=True, exist_ok=True)
    return path


def result_dir(root):
    path = ROOT / 'resultados' / root.name
    path.mkdir(parents=True, exist_ok=True)
    return path


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def manifest(root):
    m = json.loads((root / 'manifest.json').read_text())
    expected = {f'{t}.{ext}' for t in TABLES for ext in ['csv', 'parquet']}
    if m.get('generator') != 1 or set(m.get('files', {})) != expected:
        raise RuntimeError('Manifiesto incompatible o incompleto.')
    if set(m.get('counts', {})) != set(TABLES):
        raise RuntimeError('Faltan conteos en el manifiesto.')
    if m['counts']['orders'] != m['orders']:
        raise RuntimeError('Perfil con conteo de pedidos inconsistente.')
    for name, info in m['files'].items():
        path = root / name
        if path.is_symlink() or path.stat().st_size != info['bytes'] or digest(path) != info['sha256']:
            raise RuntimeError(f'Archivo modificado: {name}; no se reparara automaticamente.')
    return m


def normal(rows):
    def cell(v):
        if v is None:
            return None
        if isinstance(v, (Decimal, int)):
            return str(v)
        if isinstance(v, (dt.date, dt.datetime)):
            return v.isoformat()
        return str(v)
    return [[cell(v) for v in row] for row in rows]


def result_hash(rows):
    return hashlib.sha256(json.dumps(normal(rows), separators=(',', ':')).encode()).hexdigest()


def db(root, mode='tables', writable=False):
    path = ROOT / 'duckdb' / root.name / 'analytics.duckdb'
    if mode == 'tables' and not writable and not path.is_file():
        raise RuntimeError('Falta cargar DuckDB: ejecuta ./ensayo.sh cargar-duckdb.')
    base(root)
    c = duckdb.connect(str(path), read_only=not writable) if mode == 'tables' else duckdb.connect(':memory:')
    c.execute('SET threads=2')
    c.execute("SET memory_limit='1GB'")
    c.execute(f'SET temp_directory={literal(base(root) / ("tmp_" + mode))}')
    if mode == 'parquet':
        for t in TABLES:
            c.execute(f'CREATE VIEW {t} AS SELECT * FROM read_parquet({literal(root / (t + ".parquet"))})')
    return c


def pg():
    c = psycopg.connect(os.environ.get('PG_DSN', 'postgresql://bench:bench_local@127.0.0.1:55433/bench'),
                        autocommit=True, prepare_threshold=None, connect_timeout=3)
    c.execute('SET search_path=retail_bench,public')
    c.execute("SET timezone='UTC'")
    c.execute("SET statement_timeout='10min'")
    return c


def stamp(c, engine):
    if engine == 'postgresql':
        exists = c.execute("SELECT to_regclass('retail_bench.lab_metadata')").fetchone()[0]
    else:
        exists = c.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='lab_metadata' AND table_schema='main'").fetchone()[0]
    if not exists:
        return None
    row = c.execute('SELECT manifest_sha256 FROM lab_metadata').fetchone()
    return row[0] if row else None


def require_loaded(c, root, engine):
    if stamp(c, engine) != digest(root / 'manifest.json'):
        raise RuntimeError(f'{engine}: falta cargar este perfil o la carga quedo incompleta.')


def load_engine(root, engine, replace=False):
    m = manifest(root)
    c = db(root, writable=True) if engine == 'duckdb' else pg()
    try:
        current = stamp(c, engine)
        if current == digest(root / 'manifest.json') and not replace:
            for t in TABLES:
                if c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] != m['counts'][t]:
                    raise RuntimeError('Carga alterada; verifica o usa --reemplazar explicitamente.')
            print(f'{engine}: carga existente reutilizada; sin cambios.')
            return
        if engine == 'postgresql':
            exists = c.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='retail_bench')").fetchone()[0]
        else:
            exists = c.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='main'").fetchone()[0]
        if exists and not replace:
            raise RuntimeError('Hay otra carga o una carga incompleta. Usa --reemplazar para sustituirla.')
        if engine == 'postgresql':
            c.execute('DROP SCHEMA IF EXISTS retail_bench CASCADE')
            c.execute('CREATE SCHEMA retail_bench')
        else:
            c.execute('DROP TABLE IF EXISTS lab_metadata')
            for t in reversed(TABLES):
                c.execute(f'DROP TABLE IF EXISTS {t}')
        started = time.perf_counter()
        for t, ddl in TABLES.items():
            print(f'{engine}: cargando {t}...', flush=True)
            c.execute(f'CREATE TABLE {t} ({ddl})')
            if engine == 'duckdb':
                c.execute(f'COPY {t} FROM {literal(root / (t + ".csv"))} (FORMAT CSV, HEADER true)')
            else:
                with c.cursor() as cur:
                    with cur.copy(f'COPY {t} FROM STDIN WITH (FORMAT CSV, HEADER true)') as cp:
                        with (root / f'{t}.csv').open('rb') as f:
                            for block in iter(lambda: f.read(1024 * 1024), b''):
                                cp.write(block)
        loaded = time.perf_counter()
        for sql in KEYS + INDEXES:
            c.execute(sql)
        indexed = time.perf_counter()
        c.execute('ANALYZE')
        c.execute('CHECKPOINT')
        ready = time.perf_counter()
        # Solo se identifica como completa una carga cuyos conteos coinciden.
        for t in TABLES:
            if c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] != m['counts'][t]:
                raise RuntimeError(f'Conteo incorrecto: {t}')
        c.execute('CREATE TABLE lab_metadata (manifest_sha256 VARCHAR)')
        c.execute('INSERT INTO lab_metadata VALUES (' + literal(digest(root / 'manifest.json')) + ')')
        c.execute('CHECKPOINT')
        metrics = {'engine': engine, 'manifest_sha256': digest(root / 'manifest.json'),
                   'counts': m['counts'], 'load_seconds': loaded-started,
                   'index_seconds': indexed-loaded, 'analyze_checkpoint_seconds': ready-indexed,
                   'ready_seconds': ready-started}
        out = result_dir(root) / ('carga_' + engine + '_' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        dump(out, metrics)
        print(json.dumps(metrics, indent=2))
    finally:
        c.close()


def check(root):
    m = manifest(root)
    connections = []
    try:
        connections.append(db(root))
        connections.append(pg())
        connections.append(db(root, 'parquet'))
        require_loaded(connections[0], root, 'duckdb')
        require_loaded(connections[1], root, 'postgresql')
        connections[1].execute('SET default_transaction_read_only=on')
    except Exception:
        for c in connections:
            c.close()
        raise
    checks = {
        'orphan_customers': 'SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON c.id=o.customer_id WHERE c.id IS NULL',
        'orphan_orders': 'SELECT COUNT(*) FROM items i LEFT JOIN orders o ON o.id=i.order_id WHERE o.id IS NULL',
        'orphan_products': 'SELECT COUNT(*) FROM items i LEFT JOIN products p ON p.id=i.product_id WHERE p.id IS NULL',
        'dates': "SELECT COUNT(*) FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.ordered_at<c.registered_at OR (o.status='completed' AND (o.shipped_at IS NULL OR o.shipped_at<=o.ordered_at)) OR (o.status='cancelled' AND o.shipped_at IS NOT NULL)",
        'money': 'SELECT COUNT(*) FROM items WHERE quantity<1 OR unit_price_cents<=0 OR discount_cents<0 OR discount_cents>quantity*unit_price_cents',
        'line_count': 'SELECT COUNT(*) FROM (SELECT o.id FROM orders o LEFT JOIN items i ON i.order_id=o.id GROUP BY o.id HAVING COUNT(i.id) NOT BETWEEN 1 AND 5) s',
    }
    try:
        for c in connections:
            for t in TABLES:
                count, unique = c.execute(f'SELECT COUNT(*),COUNT(DISTINCT id) FROM {t}').fetchone()
                if count != m['counts'][t] or count != unique:
                    raise RuntimeError(f'Conteo/IDs incorrectos: {t}')
            for name, sql in checks.items():
                if c.execute(sql).fetchone()[0] != 0:
                    raise RuntimeError(f'Integridad incorrecta: {name}')
        hashes = {}
        for name, sql in QUERIES.items():
            results = [normal(c.execute(sql).fetchall()) for c in connections]
            if not results[0] == results[1] == results[2]:
                raise RuntimeError(f'Resultados diferentes: {name}')
            hashes[name] = result_hash(connections[0].execute(sql).fetchall())
        dump(result_dir(root) / 'validation.json', {'status': 'ok', 'hashes': hashes})
        print(f'OK: archivos, conteos, integridad y {len(QUERIES)} resultados en los tres modos.')
    finally:
        for c in connections:
            c.close()


def run(root, repeats, label):
    if repeats < 3:
        raise SystemExit('--repeticiones debe ser >=3')
    # Siempre validar antes. Esto calienta caches: la primera muestra NO es fria.
    check(root)
    modes = {'duckdb_tables': db(root), 'postgresql': pg(), 'duckdb_parquet': db(root, 'parquet')}
    modes['postgresql'].execute('SET default_transaction_read_only=on')
    output = result_dir(root) / 'mediciones' / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+label)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    expected = json.loads((result_dir(root) / 'validation.json').read_text())['hashes']
    rng = random.Random(2026)
    try:
        for round_no in range(repeats+2):
            print(f'Ronda {round_no+1}/{repeats+2}', flush=True)
            jobs = [(mode, q) for mode in modes for q in QUERIES]
            rng.shuffle(jobs)
            for mode, q in jobs:
                c = modes[mode]
                _, result, seconds = ejecutar_consulta(c, QUERIES[q])
                elapsed = seconds * 1000
                # Hash/calculo fuera del intervalo medido; fetchall SI esta dentro.
                if result_hash(result) != expected[q]:
                    raise RuntimeError(f'Resultado incorrecto: {mode}/{q}')
                rows.append({'mode': mode, 'query': q, 'round': round_no,
                             'phase': 'warmup' if round_no<2 else 'measured',
                             'ms': elapsed, 'rows': len(result)})
        with (output / 'raw.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        summary = []
        for mode in modes:
            for q in QUERIES:
                values = [r['ms'] for r in rows if r['mode']==mode and r['query']==q and r['phase']=='measured']
                summary.append({'mode': mode, 'query': q, 'median_ms': statistics.median(values),
                                'min_ms': min(values), 'max_ms': max(values)})
        with (output / 'summary.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
        settings = ['shared_buffers','work_mem','max_parallel_workers_per_gather',
                    'max_parallel_workers','jit','statement_timeout']
        dump(output / 'environment.json', {
            'platform': platform.platform(), 'python': platform.python_version(),
            'logical_cpus_visible': os.cpu_count(), 'duckdb': duckdb.__version__,
            'psycopg': psycopg.__version__, 'postgresql': modes['postgresql'].execute('SELECT version()').fetchone()[0],
            'postgresql_settings': {s: modes['postgresql'].execute('SHOW '+s).fetchone()[0] for s in settings},
            'duckdb_settings': {s: modes['duckdb_tables'].execute(f"SELECT current_setting('{s}')").fetchone()[0]
                                for s in ['threads','memory_limit']},
            'manifest_sha256': digest(root / 'manifest.json'), 'label': label,
            'repeats': repeats, 'metric': 'execute+fetchall wall time, warm cache',
            'queries': QUERIES,
        })
        dump(output / 'sizes.json', {
            'duckdb_file_bytes': (base(root) / 'analytics.duckdb').stat().st_size,
            'parquet_bytes': sum((root / f'{t}.parquet').stat().st_size for t in TABLES),
            'postgresql_tables_indexes_bytes': int(modes['postgresql'].execute("SELECT SUM(pg_total_relation_size(oid)) FROM pg_class WHERE relnamespace='retail_bench'::regnamespace AND relkind='r'").fetchone()[0]),
        })
    finally:
        for c in modes.values():
            c.close()
    print('Resultados:', output)
    mostrar_resumen(summary, QUERIES)


def explain(root):
    check(root)
    out = result_dir(root) / 'planes' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, exist_ok=False)
    for mode in ['tables','parquet','postgresql']:
        c = pg() if mode == 'postgresql' else db(root, mode)
        try:
            if mode == 'postgresql':
                c.execute('SET default_transaction_read_only=on')
            prefix = 'EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF, FORMAT JSON) ' if mode=='postgresql' else 'EXPLAIN ANALYZE '
            for name, sql in QUERIES.items():
                rows = c.execute(prefix+sql).fetchall()
                (out / f'{mode}_{name}.txt').write_text('\n'.join(str(row) for row in rows))
        finally:
            c.close()
    print('Planes:', out)

