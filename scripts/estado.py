"""Consultar estado sin generar ni cargar datos."""
import json
from comun import base, dataset, db, digest, manifest, parser, pg, stamp
p = parser(__doc__)
a = p.parse_args()
root = dataset(a.perfil)
if not (root / 'manifest.json').exists():
    print('Fuentes ausentes:', root)
    expected = None
else:
    m = manifest(root)
    expected = digest(root / 'manifest.json')
    print('Fuentes verificadas:', json.dumps(m['counts']))
for engine in ['duckdb', 'postgresql']:
    try:
        c = db(root) if engine == 'duckdb' else pg()
        try:
            print(engine, ':', 'perfil cargado' if expected and stamp(c, engine) == expected else 'sin carga de este perfil')
        finally:
            c.close()
    except Exception as e:
        print(engine, ': no disponible -', str(e).splitlines()[0])
