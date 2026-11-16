"""Generación SQL por conjuntos; invocado dentro de un directorio temporal."""
import time
import json
import duckdb
from comun import TABLES, dump, literal, digest

def generate_files(root, n, seed):
    if (root / 'manifest.json').exists() or any(root.glob('*.csv')):
        raise SystemExit('Dataset existente: usa otro --dir; no se sobrescriben datos.')
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    c = duckdb.connect(str(root / 'generator.duckdb'))
    c.execute('SET threads=2')
    c.execute("SET memory_limit='1GB'")
    c.execute(f'SET temp_directory={literal(root / "tmp_generate")}')
    for t, ddl in TABLES.items():
        c.execute(f'CREATE TABLE {t} ({ddl})')
    # Mezcla aritmética reproducible. No es un generador criptográfico.
    def r(expr, salt):
        return f'(((({expr})::BIGINT * 48271 + {seed} + {salt} * 104729) % 2147483647) * 40692 % 2147483647)'
    def skew(expr, salt, size):
        u = f'({r(expr, salt)} / 2147483647.0)'
        return f'(1 + floor({u} * {u} * {size}))::BIGINT'
    c.execute("""INSERT INTO customers
        SELECT id, 'Cliente ' || CAST(id AS VARCHAR),
               CASE id%4 WHEN 0 THEN 'Panama' WHEN 1 THEN 'Colon'
                         WHEN 2 THEN 'Chiriqui' ELSE 'Cocle' END,
               DATE '2022-01-01' + CAST(id%365 AS INTEGER)
        FROM range(1,100001) t(id)""")
    c.execute(f"""INSERT INTO products
        SELECT id,'Producto ' || CAST(id AS VARCHAR),
               CASE id%4 WHEN 0 THEN 'Computo' WHEN 1 THEN 'Perifericos'
                         WHEN 2 THEN 'Hogar' ELSE 'Accesorios' END,
               CASE id%4 WHEN 0 THEN 40000 WHEN 1 THEN 2000
                         WHEN 2 THEN 5000 ELSE 500 END + {r('id', 1)}%10000
        FROM range(1,10001) t(id)""")
    c.execute(f"""INSERT INTO orders
        WITH base AS (
            SELECT id,{skew('id', 2, 100000)} AS customer_id,
                   CASE WHEN {r('id', 3)}%100 < 30
                        THEN make_date(CAST(2023+{r('id', 4)}%3 AS INTEGER),11,1)
                             + CAST({r('id', 5)}%61 AS INTEGER)
                        ELSE DATE '2023-01-01' + CAST({r('id', 6)}%1096 AS INTEGER)
                   END AS ordered_at,
                   CASE WHEN {r('id', 7)}%100 < 5
                        THEN 'cancelled' ELSE 'completed' END AS status
            FROM range(1,{n + 1}) t(id)
        ) SELECT id,customer_id,ordered_at,status,
                 CASE WHEN status='completed'
                      THEN ordered_at+CAST(1+{r('id', 8)}%5 AS INTEGER)
                      ELSE NULL END FROM base""")
    c.execute(f"""INSERT INTO items
        WITH lines AS (
            SELECT (o.id-1)*5+k AS id,o.id AS order_id,
                   {skew('(o.id-1)*5+k', 9, 10000)} AS product_id,
                   CAST(1+{r('(o.id-1)*5+k', 10)}%5 AS INTEGER) AS quantity
            FROM orders o CROSS JOIN range(1,6) t(k)
            WHERE k <= 1+{r('o.id', 11)}%5
        )
        SELECT l.id,l.order_id,l.product_id,l.quantity,p.base_price_cents,
               CAST(floor(l.quantity*p.base_price_cents *
                   CASE WHEN {r('l.id', 12)}%100<20 THEN 10 ELSE 0 END / 100.0) AS BIGINT)
        FROM lines l JOIN products p ON p.id=l.product_id""")
    files, counts = {}, {}
    for t in TABLES:
        counts[t] = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        for ext, options in [('csv', 'FORMAT CSV, HEADER true'),
                             ('parquet', 'FORMAT PARQUET, COMPRESSION ZSTD')]:
            path = root / f'{t}.{ext}'
            c.execute(f'COPY (SELECT * FROM {t} ORDER BY id) TO {literal(path)} ({options})')
            files[path.name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    c.close()
    dump(root / 'manifest.json', {'generator': 1, 'seed': seed, 'orders': n,
         'counts': counts, 'files': files, 'duckdb': duckdb.__version__,
         'generation_seconds': time.perf_counter()-started})
    print(json.dumps(counts))

