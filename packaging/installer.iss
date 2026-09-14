#define AppName "Dikte"
#define AppVersion "0.1.0"
[Setup]
AppId={{7B1C0E52-3D7A-4B54-9C8F-2E1D6A5F0D1E}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Dikte-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=dikte.ico
[Files]
Source: "..\dist\Dikte\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Dikte.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Dikte.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked
[Run]
Filename: "{app}\Dikte.exe"; Description: "{#AppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent
[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Dikte /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
