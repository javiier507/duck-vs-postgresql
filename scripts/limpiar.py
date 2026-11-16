"""Limpieza acotada a duckdb/ o al perfil explicito dentro de datos/."""
import shutil
from comun import ROOT, dataset, parser
import duckdb

p = parser(__doc__)
p.add_argument('destino', choices=['duckdb', 'datos'])
p.add_argument('--confirmar', action='store_true')
a = p.parse_args()
if a.destino == 'datos':
    if not a.confirmar:
        p.error('Destruir fuentes requiere --confirmar.')
    targets = [dataset(a.perfil)]
else:
    # Detectar archivos abiertos en otro proceso antes de intentar eliminarlos.
    for folder in (ROOT / 'duckdb').iterdir():
        if folder.is_dir() and not folder.is_symlink():
            path = folder / 'analytics.duckdb'
            if path.is_file() and not path.is_symlink():
                with duckdb.connect(str(path)):
                    pass
    targets = [p for p in (ROOT / 'duckdb').iterdir() if p.name != '.gitkeep']
for target in targets:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.exists():
        shutil.rmtree(target)
print('Limpieza completada:', a.destino, '(fuentes y resultados conservados)' if a.destino == 'duckdb' else a.perfil)
