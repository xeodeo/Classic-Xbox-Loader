# Classic Xbox Loader v1.0.0

Primera versión pública de Classic Xbox Loader — una herramienta todo-en-uno para descargar, procesar e instalar juegos de Xbox Clásico directamente desde Internet Archive a tu consola moddeda por FTP.

---

## Descarga

> Descarga `ClassicXboxLoader.zip`, descomprime y ejecuta `ClassicXboxLoader.exe`
> No requiere instalación.

---

## ¿Qué incluye esta versión?

### Catálogo de juegos
- Navegación completa del catálogo de Xbox Clásico desde Internet Archive (Redump collection)
- Búsqueda por nombre en tiempo real
- Filtro por letra del alfabeto (A–Z + #)
- Acceso solo con sesión iniciada — sin login solo se puede navegar

### Descargas
- Descarga multi-hilo (hasta 16 conexiones simultáneas)
- Soporte de pausa, reanudación y cancelación
- Progreso en tiempo real con velocidad y tamaño
- Historial de descargas persistente entre sesiones
- Eliminar descarga de la lista o del disco directamente desde la UI

### Instalación pipeline
- **Paso 1** — Extracción de ZIP automática
- **Paso 2** — Procesamiento de ISO con `extract-xiso` (formato xdvdfs nativo del Xbox)
- **Paso 3** — Transferencia FTP al Xbox con progreso por archivo y total
- Detección automática de la carpeta de juegos en el Xbox
- Reconexión y reintento automático (hasta 3 intentos) si la conexión FTP cae durante la transferencia
- Sanitización automática de nombres con caracteres inválidos para FATX (paréntesis, comas)

### Xbox FTP
- Explorador de archivos del Xbox integrado
- Soporte de particiones: C, E, F, G (EvoX, UnleashX, XBMC4Xbox, PrometheOS)
- Crear carpetas, eliminar archivos y directorios
- Descarga de archivos desde el Xbox al PC

### Autenticación Internet Archive
- Login con email/contraseña
- Login con Google u otros proveedores via navegador integrado (WebEngine)
- Sesión persistente — no requiere volver a iniciar sesión al reabrir la app
- Restauración de sesión offline si no hay conexión al iniciar

### UI / UX
- Tema oscuro completo
- Popup de bienvenida en el primer inicio con info del proyecto y opción de no volver a mostrar
- Protección contra doble click en extracción y procesamiento ISO mientras están en curso
- Scrollbars limpias sin artefactos visuales

---

## Notas

- Requiere Xbox Clásica con chip mod y FTP activo en el dashboard
- Se recomienda conexión por cable para las transferencias FTP
- Los juegos se obtienen de colecciones públicas en Internet Archive
- Solo para uso personal con copias de juegos que el usuario posee legalmente

---

## Créditos

- **Desarrollador:** xeodeo
- **ISO processing:** extract-xiso por [in@fishtank.com](mailto:in@fishtank.com) — licencia BSD modificada
- **Fuente de juegos:** [Internet Archive](https://archive.org) — Redump Xbox Collection

---

[Ver repositorio](https://github.com/xeodeo/Classic-Xbox-Loader) · [Reportar un bug](https://github.com/xeodeo/Classic-Xbox-Loader/issues)
