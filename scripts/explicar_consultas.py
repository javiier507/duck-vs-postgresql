"""Exportar planes de las consultas; separado de las mediciones normales."""
from comun import dataset, explain, parser
p = parser(__doc__)
a = p.parse_args()
explain(dataset(a.perfil))
