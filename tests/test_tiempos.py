"""Pruebas sin Docker, motores instalados ni conexiones a las bases del ensayo.

Ejecutar: python3 -B -m unittest discover -s tests -v
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import copy
import csv
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import presentacion


class Clock:
    def __init__(self):
        self.ns = 0
        self.events = []

    def now(self):
        self.events.append('clock')
        return self.ns

    def advance(self, ns):
        self.ns += ns


class Connection:
    def __init__(self, clock, rows, queries):
        self.clock = clock
        self.rows = rows
        self.queries = queries
        self.executed = []
        self.fetched = 0
        self.closed = False

    def execute(self, sql):
        self.executed.append(sql)
        self.clock.events.append('execute')
        self.clock.advance(100_000_000 if sql in self.queries else 900_000_000)
        return self

    def fetchall(self):
        self.fetched += 1
        self.clock.events.append('fetchall')
        self.clock.advance(200_000_000)
        return self.rows

    @property
    def description(self):
        self.clock.events.append('description')
        self.clock.advance(600_000_000)
        return [('valor',)]

    def fetchone(self):
        if 'pg_total_relation_size' in self.executed[-1]:
            return (7,)
        return ('fixture',)

    def close(self):
        self.closed = True
        self.clock.advance(700_000_000)


def fake_duckdb():
    module = types.ModuleType('duckdb')
    module.__version__ = 'fixture'
    module.StatementType = types.SimpleNamespace(SELECT='SELECT')
    module.extract_statements = lambda sql: [types.SimpleNamespace(
        type='SELECT' if sql.lstrip().upper().startswith(('SELECT', 'WITH')) else 'OTHER')]
    return module


def load(name, filename, dependencies):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, dependencies):
        spec.loader.exec_module(module)
    return module


class TimingTests(unittest.TestCase):
    def test_execute_fetch_once_and_exclude_metadata(self):
        clock = Clock()
        query = 'SELECT 1'
        connection = Connection(clock, [(1,)], {query})
        with patch.object(presentacion.time, 'perf_counter_ns', clock.now):
            columns, rows, seconds = presentacion.ejecutar_consulta(connection, query)
        self.assertEqual(seconds, 0.3)
        self.assertEqual(columns, ['valor'])
        self.assertEqual(rows, [(1,)])
        self.assertEqual(connection.executed, [query])
        self.assertEqual(connection.fetched, 1)
        self.assertEqual(clock.events, ['clock', 'execute', 'fetchall', 'clock', 'description'])

    def test_summary_seconds_does_not_mutate_millisecond_values(self):
        summary = [dict(query='01_prueba', mode=mode, median_ms=value)
                   for mode, value in [('postgresql', 2500), ('duckdb_tables', 125), ('duckdb_parquet', 7.5)]]
        before = copy.deepcopy(summary)
        output = io.StringIO()
        with redirect_stdout(output):
            presentacion.mostrar_resumen(summary, ['01_prueba'])
        for value in ['2.500000', '0.125000', '0.007500', 'PostgreSQL (s)', 'DuckDB (s)', 'Parquet (s)']:
            self.assertIn(value, output.getvalue())
        self.assertEqual(summary, before)

    def test_empty_result(self):
        output = io.StringIO()
        with redirect_stdout(output):
            presentacion.mostrar_tabla(['valor'], [], limit=40)
        self.assertIn('valor', output.getvalue())


class ConsultarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.query = 'SELECT valor FROM prueba;'
        self.file = self.root / 'consulta.sql'
        self.file.write_text(self.query)
        self.clock = Clock()
        self.rows = [(f'fila-{n:03d}',) for n in range(45)]
        self.connection = Connection(self.clock, self.rows, {self.query})
        common = types.ModuleType('comun')
        common.ROOT = self.root
        def parser(description):
            p = argparse.ArgumentParser(description=description)
            p.add_argument('--perfil', default='ventas-2m')
            return p
        def connect(*args):
            self.clock.advance(2_000_000_000)
            return self.connection
        def require(*args):
            self.clock.advance(3_000_000_000)
        common.parser = parser
        common.dataset = lambda profile: self.root / 'datos' / profile
        common.db = Mock(side_effect=connect)
        common.pg = Mock(side_effect=connect)
        common.require_loaded = Mock(side_effect=require)
        self.common = common
        self.module = load('consultar_test', 'consultar.py', {'comun': common, 'duckdb': fake_duckdb()})

    def invoke(self, mode, extra=()):
        output = io.StringIO()
        with patch.object(presentacion.time, 'perf_counter_ns', self.clock.now), redirect_stdout(output):
            self.module.main(['--motor', mode, '--archivo', str(self.file), *extra])
        return output.getvalue()

    def test_each_mode_once_and_display_only_40_rows(self):
        for mode in ['postgresql', 'duckdb', 'parquet']:
            with self.subTest(mode=mode):
                self.reset_connection()
                output = self.invoke(mode)
                self.assertEqual(self.connection.executed.count(self.query), 1)
                self.assertEqual(self.connection.fetched, 1)
                self.assertIn('fila-039', output)
                self.assertNotIn('fila-040', output)
                self.assertIn('Mostrando 40 de 45 filas', output)
                self.assertIn('Tiempo: 0.300000 s | Filas: 45', output)
                self.assertTrue(self.connection.closed)

    def reset_connection(self):
        self.clock.ns = 0
        self.clock.events.clear()
        self.connection.executed.clear()
        self.connection.fetched = 0
        self.connection.closed = False

    def test_csv_all_rows_and_printing_writing_outside_timer(self):
        target = self.root / 'resultados/reporte.csv'
        real_export = presentacion.exportar_csv
        def slow_export(*args):
            self.clock.advance(9_000_000_000)
            return real_export(*args)
        with patch.object(self.module, 'exportar_csv', side_effect=slow_export):
            output = self.invoke('duckdb', ['--csv', str(target)])
        self.assertIn('Tiempo: 0.300000 s | Filas: 45', output)
        with target.open(newline='') as f:
            exported = list(csv.reader(f))
        self.assertEqual(exported, [['valor']] + [[r[0]] for r in self.rows])
        self.assertEqual(self.connection.executed.count(self.query), 1)
        self.assertEqual(self.connection.fetched, 1)

    def test_presentation_outside_timer(self):
        real_show = presentacion.mostrar_tabla
        def slow_show(*args, **kwargs):
            self.clock.advance(9_000_000_000)
            return real_show(*args, **kwargs)
        with patch.object(self.module, 'mostrar_tabla', side_effect=slow_show):
            output = self.invoke('parquet')
        self.assertIn('Tiempo: 0.300000 s | Filas: 45', output)

    def test_existing_csv_is_preserved_without_executing_query(self):
        target = self.root / 'resultados/reporte.csv'
        target.parent.mkdir()
        target.write_text('conservar')
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.invoke('duckdb', ['--csv', str(target)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(target.read_text(), 'conservar')
        self.assertEqual(self.connection.executed, [])

    def test_csv_cannot_escape_results(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke('postgresql', ['--csv', str(self.root / 'fuera.csv')])
        self.assertFalse((self.root / 'fuera.csv').exists())
        self.assertEqual(self.connection.executed, [])

    def test_read_query_required(self):
        self.file.write_text('DELETE FROM prueba')
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke('duckdb')
        self.assertEqual(self.connection.executed, [])


class MedirTests(unittest.TestCase):
    def test_loop_keeps_csv_schema_in_ms_and_shows_seconds(self):
        psycopg = types.ModuleType('psycopg')
        psycopg.__version__ = 'fixture'
        common = load('comun_test', 'comun.py', {'duckdb': fake_duckdb(), 'psycopg': psycopg})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'resultados'
            output.mkdir()
            base = root / 'duckdb'
            base.mkdir()
            (base / 'analytics.duckdb').write_bytes(b'fixture')
            (root / 'manifest.json').write_text('{}')
            for table in common.TABLES:
                (root / f'{table}.parquet').write_bytes(b'fixture')
            expected = {q: common.result_hash([(1,)]) for q in common.QUERIES}
            def check(_root):
                common.dump(output / 'validation.json', {'status': 'ok', 'hashes': expected})
            clock = Clock()
            connections = [Connection(clock, [(1,)], set(common.QUERIES.values())) for _ in range(3)]
            printed = io.StringIO()
            with patch.object(common, 'check', check), patch.object(common, 'db', side_effect=[connections[0], connections[2]]), \
                 patch.object(common, 'pg', return_value=connections[1]), patch.object(common, 'base', return_value=base), \
                 patch.object(common, 'result_dir', return_value=output), \
                 patch.object(presentacion.time, 'perf_counter_ns', clock.now), redirect_stdout(printed):
                common.run(root, 3, 'fixture')
            run = next((output / 'mediciones').iterdir())
            with (run / 'raw.csv').open() as f:
                raw = list(csv.DictReader(f))
            with (run / 'summary.csv').open() as f:
                summary = list(csv.DictReader(f))
            self.assertEqual(len(common.QUERIES), 6)
            self.assertEqual(len(raw), 90)
            self.assertEqual(sum(r['phase'] == 'measured' for r in raw), 54)
            self.assertEqual(len(summary), 18)
            self.assertEqual(set(raw[0]), {'mode', 'query', 'round', 'phase', 'ms', 'rows'})
            self.assertEqual(set(summary[0]), {'mode', 'query', 'median_ms', 'min_ms', 'max_ms'})
            self.assertTrue(all(float(r['ms']) == 300 for r in raw))
            self.assertTrue(all(float(r['median_ms']) == 300 for r in summary))
            self.assertIn('Medianas en segundos (s)', printed.getvalue())
            self.assertIn('0.300000', printed.getvalue())
            self.assertTrue(all(c.closed for c in connections))


if __name__ == '__main__':
    unittest.main()
