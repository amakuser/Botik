#define MyAppName "Botik"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "Botik"
#define MyAppExeName "botik.exe"

[Setup]
AppId={{9EC78B85-420F-4E74-8A57-3D87DE8BDE35}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=BotikInstaller
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Запускать Botik при входе в Windows"; GroupDescription: "Параметры запуска:"

[Dirs]
Name: "{app}\logs"
Name: "{app}\data"

[Files]
Source: "dist\botik.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist
Source: "config.example.yaml"; DestDir: "{app}"; DestName: "config.yaml"; Flags: onlyifdoesntexist
Source: "version.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.db-shm,*.db-wal"

[Icons]
Name: "{group}\Запустить Botik (GUI)"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Запустить Botik Bot (без GUI)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--nogui"
Name: "{commondesktop}\Запустить Botik (GUI)"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Name: "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Botik"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart
Name: "HKCU\Software\Botik"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Name: "HKCU\Software\Botik"; ValueType: string; ValueName: "InstallVersion"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Name: "HKCU\Software\Botik"; ValueType: string; ValueName: "VersionFile"; ValueData: "{app}\version.txt"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Botik"; Flags: nowait postinstall skipifsilent

