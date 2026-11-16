"""Verificar fuentes, integridad y equivalencia de todas las consultas SQL."""
from comun import check, dataset, parser
p = parser(__doc__)
a = p.parse_args()
check(dataset(a.perfil))
