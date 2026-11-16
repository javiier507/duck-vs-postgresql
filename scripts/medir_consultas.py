"""Medir execute + fetchall: dos rondas de calentamiento y N medidas."""
from comun import dataset, parser, run, safe_name
p = parser(__doc__)
p.add_argument('--repeticiones', type=int, default=7)
p.add_argument('--etiqueta', type=safe_name, default='baseline')
a = p.parse_args()
run(dataset(a.perfil), a.repeticiones, a.etiqueta)
