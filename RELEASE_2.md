# Classic Xbox Loader — Release 2

## Bugs arreglados

### Extractor de Xbox ISO reescrito en Python puro
Se eliminó la dependencia de `extract-xiso.exe`. El extractor ahora está implementado directamente en Python (`core/xiso_processor.py`) usando el formato XDVDFS documentado en el código fuente original de extract-xiso.

**Bugs corregidos en el proceso:**

- **Offset del segundo magic incorrecto** — el descriptor de volumen XDVDFS tiene la firma `MICROSOFT*XBOX*MEDIA` al inicio y al final del sector (offset `0x7EC` = 2028, los últimos 20 bytes del sector de 2048 bytes). Se usaba `0x7F8` (2040), que rebasa el buffer y nunca coincidía, causando que ningún ISO fuera reconocido como válido.

- **Base de sectores errónea** — se usaba `base_offset` (`0x10000`) como punto de origen para calcular la posición de cada sector dentro del ISO. El valor correcto es `lseek_offset = 0` para ISOs estándar; `0x10000` solo indica dónde encontrar el descriptor de volumen, no la base de los sectores. Esto hacía que todos los sectores de datos se leyeran desde posiciones completamente incorrectas.

- **Null bytes en rutas al extraer** — consecuencia directa del bug anterior: al leer sectores equivocados, el parser interpretaba datos arbitrarios como entradas de directorio, generando nombres de archivo con caracteres nulos (`\x00`) que provocaban el error `mkdir: embedded null character in path`.

### Build limpiado
Se eliminaron del script `build_app.bat` las referencias a `extract iso a xiso/` (el `--add-data` de PyInstaller y el paso de copia del `.exe`), ya que el extractor es ahora código Python incluido automáticamente en el bundle.
