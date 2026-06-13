# Classic Xbox Loader — Release 4

## Mejoras en descargas

### Recuperación de descargas interrumpidas por Internet Archive

Internet Archive corta frecuentemente conexiones largas (timeouts, `IncompleteRead`) en archivos grandes. Antes, cuando esto ocurría tras agotar todos los reintentos automáticos, el progreso se perdía por completo — los archivos parciales de cada chunk eran eliminados y la siguiente descarga empezaba desde cero.

**Ahora los archivos `.partN` se conservan en disco al fallar.** Al reintentar, cada chunk detecta los bytes ya descargados y continúa exactamente desde donde quedó, sin volver a descargar lo que ya estaba guardado.

### Botón Reintentar en el panel de Descargas

Las descargas con estado **Error** ahora muestran un botón 🔄 **Reintentar** directamente en la tabla de descargas. Al pulsarlo, la descarga se reanuda desde los datos parciales guardados — no hace falta volver al Catálogo a buscar el juego de nuevo.

El botón solo aparece cuando la sesión de Internet Archive sigue activa (errores ocurridos en la sesión actual). Las entradas del historial cargadas al arrancar la app no lo muestran.
