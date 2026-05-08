@echo off
title Classic Xbox Loader - Build EXE
echo.
echo Compilando Classic Xbox Loader...
echo.

pyinstaller --noconfirm --clean ^
    --name "ClassicXboxLoader" ^
    --windowed ^
    --onedir ^
    --icon "app_icon.ico" ^
    --add-data "app_icon.ico;." ^
    --add-data "microsoft-xbox-1.svg;." ^
    --hidden-import "PyQt6.QtCore" ^
    --hidden-import "PyQt6.QtWidgets" ^
    --hidden-import "PyQt6.QtGui" ^
    --hidden-import "PyQt6.QtWebEngineWidgets" ^
    --hidden-import "PyQt6.QtWebEngineCore" ^
    --hidden-import "PyQt6.QtSvg" ^
    --hidden-import "ftplib" ^
    --hidden-import "zipfile" ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la compilacion.
    pause
    exit /b 1
)

echo.
echo Listo! Ejecutable en: dist\ClassicXboxLoader\ClassicXboxLoader.exe
echo.
pause
