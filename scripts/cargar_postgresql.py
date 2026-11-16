"""Cargar postgresql desde los CSV; reutilizar una carga completa del mismo perfil."""
from comun import dataset, load_engine, parser
p = parser(__doc__)
p.add_argument('--reemplazar', action='store_true', help='Sustituir explicitamente la carga del laboratorio.')
a = p.parse_args()
load_engine(dataset(a.perfil), 'postgresql', a.reemplazar)
