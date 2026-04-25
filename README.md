# Classic Xbox Loader

<div align="center">

![Xbox](https://img.shields.io/badge/Xbox-Classic-107c10?style=for-the-badge&logo=xbox&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-GUI-41CD52?style=for-the-badge)
![License](https://img.shields.io/badge/License-Free-green?style=for-the-badge)

**Descarga, extrae e instala juegos de Xbox Clásico directamente desde Internet Archive a tu consola moddeda.**

[📦 Descargar](#instalación) · [🐛 Reportar Bug](https://github.com/xeodeo/Classic-Xbox-Loader/issues) · [⭐ Repositorio](https://github.com/xeodeo/Classic-Xbox-Loader)

</div>

---

## ¿Qué hace esta app?

Classic Xbox Loader automatiza el proceso completo de instalar juegos en una Xbox Clásica moddeda:

```
Internet Archive  ──▶  Descargar ZIP  ──▶  Extraer ZIP  ──▶  Procesar ISO (xdvdfs)  ──▶  FTP al Xbox
```

Sin herramientas externas, sin pasos manuales, todo desde una sola interfaz.

---

## Requisitos

- Xbox Clásica con **chip mod** y dashboard que soporte FTP (EvoX, UnleashX, XBMC4Xbox)
- Windows 10/11
- Cuenta gratuita en [Internet Archive](https://archive.org) *(necesaria para descargar)*
- Red local con el Xbox conectado (cable o WiFi)

---

## Instalación

1. Descarga la última versión desde [Releases](https://github.com/xeodeo/Classic-Xbox-Loader/releases)
2. Descomprime la carpeta `ClassicXboxLoader`
3. Ejecuta `ClassicXboxLoader.exe`
4. No requiere instalación adicional

---

## Guía de uso

### 1. Iniciar sesión en Internet Archive

> Sin sesión puedes navegar el catálogo, pero **no descargar**.

1. Ve a la pestaña **⚙️ Configuración**
2. Ingresa tu email y contraseña de [archive.org](https://archive.org)
3. Haz click en **Iniciar sesión**

También puedes usar **Login con Google / Navegador** si tu cuenta está vinculada a Google:
- Se abre un navegador integrado
- Inicia sesión normalmente (incluye Google OAuth)
- La app detecta el login automáticamente y guarda la sesión

> La sesión se guarda en disco — no necesitas volver a iniciar sesión cada vez que abres la app.

---

### 2. Buscar y descargar un juego

1. Ve a la pestaña **🎮 Catálogo**
2. Selecciona una letra del alfabeto o escribe en el buscador
3. Haz click en **⬇ Descargar** en el juego que quieras
4. El archivo ZIP se descarga en la carpeta `downloads\`

> Las descargas son multi-hilo (hasta 16 conexiones simultáneas) para máxima velocidad.

---

### 3. Gestionar descargas

En la pestaña **⬇️ Descargas** puedes:

| Botón | Acción |
|-------|--------|
| ⏸ | Pausar descarga activa |
| ▶ | Reanudar descarga pausada |
| ⏹ | Cancelar descarga |
| ✕ | Quitar de la lista |
| 🗑 | Eliminar archivo del disco |

---

### 4. Instalar el juego en el Xbox

Ve a la pestaña **📦 Instalación** y sigue el pipeline de 3 pasos:

#### Paso 1 — Extraer ZIP
- Selecciona el ZIP descargado en la lista izquierda
- Haz click en **Extraer ZIP**
- Se extrae el `.iso` dentro de una carpeta `_extracted`

#### Paso 2 — Procesar ISO
- Haz click en **Procesar ISO**
- La herramienta `extract-xiso` convierte el ISO al formato **xdvdfs** que el Xbox lee
- Se genera una carpeta con el contenido del juego listo para transferir

#### Paso 3 — Instalar en Xbox (FTP)
- Asegúrate de estar conectado al Xbox (pestaña **🎮 Xbox FTP**)
- Haz click en **🔍 Detectar destino** para encontrar la carpeta de juegos automáticamente
- Haz click en **Instalar en Xbox**
- La app transfiere todos los archivos por FTP con progreso por archivo y total

> Si la conexión cae durante la transferencia, la app **reconecta y reintenta automáticamente** hasta 3 veces por archivo.

---

### 5. Conectar al Xbox por FTP

1. Ve a la pestaña **🎮 Xbox FTP**
2. Ingresa la **IP del Xbox** (visible en el dashboard de tu Xbox)
3. Usuario y contraseña por defecto: `xbox` / `xbox`
4. Haz click en **Conectar**

Desde esta pestaña también puedes navegar los archivos del Xbox, crear carpetas y eliminar juegos.

---

## Configuración avanzada

En **⚙️ Configuración** puedes ajustar:

- **Hilos de descarga** (1–16): más hilos = mayor velocidad. Recomendado: 5
- **Sesión de Internet Archive**: iniciar o cerrar sesión

---

## Estructura de archivos

```
ClassicXboxLoader/
├── ClassicXboxLoader.exe       ← Ejecutable principal
├── _internal/                  ← Dependencias (no eliminar)
├── downloads/                  ← ZIPs descargados (se crea al usar la app)
├── settings.json               ← Configuración guardada
└── ia_session.json             ← Sesión de Internet Archive
```

---

## Solución de problemas

| Problema | Solución |
|----------|----------|
| No puedo descargar | Inicia sesión en Configuración |
| Error FTP 553 | El nombre del juego tiene caracteres inválidos — la app los sanitiza automáticamente |
| Error FTP 502 / conexión caída | La app reconecta y reintenta sola |
| Login con Google no funciona | Asegúrate de tener PyQt6-WebEngine instalado |
| Xbox no detectado | Verifica la IP y que el dashboard tenga FTP activo |

---

## Créditos

### extract-xiso

Este proyecto utiliza **extract-xiso** para procesar los archivos ISO al formato xdvdfs nativo del Xbox.

---

### Licencia de extract-xiso

```
This is an xdvdfs (xbox iso) file creation/extraction utility for linux/darwin/freebsd.

I wrote this code completely from scratch because xbiso keeps seg-faulting and the
code is buggy. I got useful documentation on the xdvdfs file system from
http://xbox-linux.sourceforge.net.

Copyright (c) 2003 in <in@fishtank.com>
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. All advertising materials mentioning features or use of this software must
   display the following acknowledgement:
   "This product includes software developed by in <in@fishtank.com>."

4. Neither the name "in" nor the email address "in@fishtank.com" may be used
   to endorse or promote products derived from this software without specific
   prior written permission.

THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHOR
OR ANY CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT
OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
OF SUCH DAMAGE.
```

---

### Licencia de Classic Xbox Loader

Classic Xbox Loader es un proyecto de código abierto desarrollado por **xeodeo**.
Repositorio: [github.com/xeodeo/Classic-Xbox-Loader](https://github.com/xeodeo/Classic-Xbox-Loader)

El uso de este software es para fines personales con copias de juegos que el usuario posee legalmente.

---

<div align="center">
Hecho con por <strong>xeodeo</strong>
</div>
