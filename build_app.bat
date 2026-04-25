@echo off
setlocal EnableDelayedExpansion
title Classic Xbox Loader - Builder

echo.
echo ============================================
echo   Classic Xbox Loader - Build Script
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+
    pause & exit /b 1
)

echo [1/4] Instalando dependencias...
pip install -r requirements.txt
pip install pyinstaller
echo.

echo [2/4] Compilando con PyInstaller...
pyinstaller --noconfirm --clean ^
    --name "ClassicXboxLoader" ^
    --windowed ^
    --onedir ^
    --add-data "extract iso a xiso;extract iso a xiso" ^
    --hidden-import "PyQt6.QtCore" ^
    --hidden-import "PyQt6.QtWidgets" ^
    --hidden-import "PyQt6.QtGui" ^
    --hidden-import "PyQt6.QtWebEngineWidgets" ^
    --hidden-import "PyQt6.QtWebEngineCore" ^
    --hidden-import "ftplib" ^
    --hidden-import "zipfile" ^
    main.py

if errorlevel 1 (
    echo [ERROR] Fallo la compilacion.
    pause & exit /b 1
)

echo.
echo [3/4] Copiando extract-xiso...
if not exist "dist\ClassicXboxLoader\extract iso a xiso" (
    mkdir "dist\ClassicXboxLoader\extract iso a xiso"
)
copy /Y "extract iso a xiso\extract-xiso.exe" "dist\ClassicXboxLoader\extract iso a xiso\"
copy /Y "extract iso a xiso\LICENSE.TXT" "dist\ClassicXboxLoader\extract iso a xiso\"

echo.
echo [4/4] Buscando Inno Setup...
set INNO=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set INNO="C:\Program Files\Inno Setup 6\ISCC.exe"

if %INNO%=="" (
    echo [INFO] Inno Setup no encontrado.
    echo [INFO] Instala desde https://jrsoftware.org/isinfo.php
    echo [INFO] Luego ejecuta: ISCC installer\setup.iss
) else (
    if not exist "installer_output" mkdir "installer_output"
    %INNO% "installer\setup.iss"
    if errorlevel 1 (echo [WARN] Error al crear el instalador.) else (echo [OK] Instalador creado en installer_output\)
)

echo.
echo ============================================
echo   Build completado!
echo ============================================
echo Ejecutable: dist\ClassicXboxLoader\ClassicXboxLoader.exe
echo Prueba rapida: python main.py
echo.
pause
