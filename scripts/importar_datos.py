"""Importar entradas existentes verificadas, sin copiar bases cargadas ni temporales."""
from pathlib import Path
import shutil
import tempfile
from comun import ROOT, dataset, manifest, parser

p = parser(__doc__)
p.add_argument('--desde', type=Path, required=True)
a = p.parse_args()
m = manifest(a.desde)
dest = dataset(a.perfil)
if dest.exists():
    existing = manifest(dest)
    if existing != m:
        raise SystemExit('Ya existe otro dataset: usa un perfil nuevo.')
    print('Fuentes existentes verificadas; no se copiaron otra vez.')
else:
    with tempfile.TemporaryDirectory(prefix='.importacion-', dir=ROOT / 'duckdb') as tmp:
        ready = Path(tmp) / 'ready'
        ready.mkdir()
        for name in list(m['files']) + ['manifest.json']:
            shutil.copy2(a.desde / name, ready / name)
        manifest(ready)
        dest.parent.mkdir(parents=True, exist_ok=True)
        ready.rename(dest)
    print('Fuentes importadas y verificadas:', dest)
