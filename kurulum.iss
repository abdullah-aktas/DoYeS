; DÖSE Yönetim Sistemi - Inno Setup kurulum betiği (exe_olustur.bat tarafından derlenir)
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppName "DÖSE Yönetim Sistemi"
#define AppPublisher "Derik MTAL Döner Sermaye İşletmesi"
#define AppExe "DOSE_Yonetim.exe"

[Setup]
; AppId sonraki sürümlerde değiştirilmemelidir; güncelleme kurulumları bu kimlikle eski sürümün üzerine yazar.
AppId={{DCB49076-A4CA-4612-A908-FE02EDACF2E4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\DOSE Yonetim
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=kurulum_paketi
OutputBaseFilename=DOSE_Yonetim_Kurulum_{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=dose\gorsel\ikon.ico
WizardImageFile=dose\gorsel\kurulum_buyuk.bmp
WizardSmallImageFile=dose\gorsel\kurulum_kucuk.bmp
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright={#AppPublisher}
CloseApplications=yes

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; Veriler program klasöründeki 'veri' altında tutulur; Program Files altında da tüm kullanıcılar yazabilsin.
; Kaldırmada silinmez, böylece yeniden kurulumda veriler korunur.
Name: "{app}\veri"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "dist\DOSE_Yonetim\*"; DestDir: "{app}"; Excludes: "\veri"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "KURULUM.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\DÖSE Mobil Sunucu (telefon ve web erişimi)"; Filename: "{app}\MobilSunucu\DOSE_Mobil_Sunucu.exe"; WorkingDir: "{app}"
Name: "{group}\Kurulum ve Kullanım Kılavuzu"; Filename: "{app}\KURULUM.md"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
