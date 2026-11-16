# TODO

Mejoras detectadas el 2026-11-15 al ejecutar el ensayo completo. Todas están **pendientes**: se pospusieron para no mezclar cambios de código con la reorganización de la documentación.

- [ ] **Rutas del contenedor.** `medir`, `planes` y `consultar --csv` imprimen `/work/resultados/...`; traducirlas a rutas del equipo (`./resultados/...`) en `scripts/comun.py` (`run`, `explain`) y `scripts/consultar.py`. Al corregirlo, retirar las notas sobre `/work` de README.md (apartado 4) y AGENTS.md (apartado 1).
- [ ] **Consulta repetida en la verificación.** `check()` en `scripts/comun.py` ejecuta cada consulta una cuarta vez solo para calcular el hash; reutilizar `results[0]`.
- [ ] **Razón en el resumen.** `medir` podría mostrar la razón PostgreSQL/DuckDB en la tabla de medianas y añadirla a `summary.csv`.
- [ ] **Exportación repetida.** `consultar --csv` falla si el archivo existe; valorar un nombre por defecto con fecha.
- [ ] **Restos en `resultados/ventas-2m/mediciones/`.** `*_nueva-ejecucion` solo contiene un CSV exportado y `*_revision-ventas-2m` tiene archivos que `medir` no genera. Revisarlos y decidir si se limpian.
- [x] ~~**PRUEBAS.md.** Añadir la ejecución del 2026-11-15.~~ Resuelto: PRUEBAS.md se eliminó y sus resultados de referencia, actualizados, están en AGENTS.md (apartado 7).
- [x] ~~**Control de versiones.** El proyecto no es un repositorio git aunque tiene `.gitignore`; valorar `git init`.~~ Resuelto el 2026-11-15: `git init` con datos, bases y resultados excluidos.
