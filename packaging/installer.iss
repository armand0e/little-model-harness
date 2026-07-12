; Inno Setup script — builds dist\LittleHarness-Setup.exe
; Per-user install (no admin prompt), Start Menu + optional desktop icon,
; launch after install, uninstaller in Settings > Apps.
; Build: ISCC.exe packaging\installer.iss   (or packaging\build_windows.ps1)

#define AppName "Little Harness"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppExe "LittleHarness.exe"

[Setup]
AppId={{7E2C3B8A-6F41-4D1B-9C0A-52A3B76F10E4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\LittleHarness
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LittleHarness-Setup
SetupIconFile=littleharness.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
CloseApplicationsFilter=LittleHarness.exe,LittleHarnessCLI.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\LittleHarness\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; user data in %LOCALAPPDATA%\LittleHarness is intentionally kept on uninstall
