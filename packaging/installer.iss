#define AppName "Dikte"
; Sürüm build betiğinden gelir: ISCC /DAppVersion=<pyproject.toml sürümü>.
; Yedek değer yalnızca ISCC elle, parametresiz çalıştırıldığında kullanılır.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
[Setup]
AppId={{7B1C0E52-3D7A-4B54-9C8F-2E1D6A5F0D1E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Sarpel GÜRAY
AppPublisherURL=https://github.com/sarpel/diktasyon-uygulamasi
AppSupportURL=https://github.com/sarpel/diktasyon-uygulamasi/issues
AppUpdatesURL=https://github.com/sarpel/diktasyon-uygulamasi/releases
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\Dikte.exe
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
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Dikte.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Dikte.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked
[Run]
Filename: "{app}\Dikte.exe"; Description: "{#AppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent
[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Dikte /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
