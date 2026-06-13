# Classic Xbox Loader — Release 3

## Nuevas funciones

### Notificaciones del sistema
Se agregó un sistema de notificaciones nativas de Windows (via `QSystemTrayIcon`) que avisa cuando termina cada etapa del flujo de trabajo:

- **Descarga completada** — al terminar cualquier descarga de Internet Archive
- **Extracción de ZIP completada** — cuando el ZIP se descomprime correctamente
- **ISO procesada** — cuando extract-xiso termina de procesar el ISO
- **Instalación FTP completada** — cuando el juego queda instalado en el Xbox

Las notificaciones se pueden **activar o desactivar** desde la pestaña Configuración con un checkbox.

---

## Mejoras en descargas

### Velocidad de descarga corregida
El indicador de velocidad ahora muestra la **velocidad actual** en lugar del promedio desde el inicio. Se usa una ventana deslizante de 4 segundos, lo que refleja correctamente las variaciones de velocidad de Internet Archive.

### Reintentos automáticos por chunk
Cada uno de los hilos de descarga paralela ahora reintenta automáticamente hasta **5 veces** si la conexión se cae o el servidor corta la transmisión antes de terminar. Cada reintento espera exponencialmente (1s, 2s, 4s, 8s, 16s) y retoma desde el byte exacto donde quedó.

### Validación de tamaño final
Al terminar la descarga, se verifica que el archivo tenga el tamaño correcto. Si el servidor cerró la conexión antes de tiempo y el archivo está incompleto, ahora se reporta como error en lugar de marcarse como completado. Los archivos temporales se limpian automáticamente en caso de fallo.

### Corrección en reanudación parcial
Al reanudar una descarga interrumpida, los bytes ya descargados de cada chunk ahora se contabilizan correctamente en la barra de progreso desde el inicio.

### Timeout extendido
El timeout por conexión subió de 60 a 90 segundos para tolerar mejor la latencia variable de Internet Archive.

---

## Mejoras en FTP

### Detección real de conexión perdida
El panel Xbox FTP ahora detecta correctamente cuando se pierde la conexión con el Xbox, incluso si fue por un corte de red o el Xbox se apagó. Antes solo chequeaba un flag interno. Ahora envía un comando `NOOP` real al servidor cada 10 segundos en un hilo separado — si falla, el estado cambia a "Conexión perdida" y los botones se deshabilitan.

---

## Configuración

### Toggle de notificaciones
Nuevo checkbox en la pestaña **Configuración** para activar o desactivar las notificaciones del sistema. El estado se guarda en `settings.json`.

### Limpieza de rutas
Se eliminó la entrada `extract-xiso.exe` del grupo "Rutas del sistema" en Configuración, ya que el procesamiento de ISO es ahora nativo en Python.
