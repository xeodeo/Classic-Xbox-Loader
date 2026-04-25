; Classic Xbox Loader - Inno Setup Script
; Requires Inno Setup 6+ from https://jrsoftware.org/isinfo.php

#define MyAppName "Classic Xbox Loader"
#define MyAppVersion "1.0.0"
#define MyAppExeName "ClassicXboxLoader.exe"

[Setup]
AppId={{8B3F2C1A-4E6D-4F8A-9C2E-1D5B7A3F9E0C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=XboxLoader
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=ClassicXboxLoader_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el Escritorio"; GroupDescription: "Iconos adicionales:"

[Files]
Source: "dist\ClassicXboxLoader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "extract iso a xiso\extract-xiso.exe"; DestDir: "{app}\extract iso a xiso"; Flags: ignoreversion
Source: "extract iso a xiso\LICENSE.TXT"; DestDir: "{app}\extract iso a xiso"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}\downloads"
