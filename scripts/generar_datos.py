"""Generar una vez; volver a ejecutar verifica y reutiliza los archivos."""
from pathlib import Path
import shutil
import tempfile
from comun import ROOT, dataset, manifest, parser
from generador import generate_files

p = parser(__doc__)
p.add_argument('--pedidos', type=int, default=2_000_000)
p.add_argument('--semilla', type=int, default=42)
a = p.parse_args()
if not 100 <= a.pedidos <= 100_000_000 or not 0 <= a.semilla <= 1_000_000:
    p.error('--pedidos entre 100 y 100000000; --semilla entre 0 y 1000000')
dest = dataset(a.perfil)
if dest.exists():
    m = manifest(dest)
    if m['orders'] != a.pedidos or m['seed'] != a.semilla:
        raise SystemExit('El perfil existente tiene otros parametros; usa otro --perfil o destruye las fuentes explicitamente.')
    print('Fuentes verificadas y reutilizadas. No se generaron datos.')
else:
    (ROOT / 'duckdb').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.generacion-', dir=ROOT / 'duckdb') as tmp:
        stage = Path(tmp) / 'dataset'
        generate_files(stage, a.pedidos, a.semilla)
        m = manifest(stage)
        # La base de generacion no forma parte de las fuentes persistentes.
        ready = Path(tmp) / 'ready'
        ready.mkdir()
        for name in list(m['files']) + ['manifest.json']:
            shutil.move(str(stage / name), str(ready / name))
        dest.parent.mkdir(parents=True, exist_ok=True)
        ready.rename(dest)
    print('Fuentes generadas:', dest)
