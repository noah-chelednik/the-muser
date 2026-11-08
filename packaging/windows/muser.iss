; Inno Setup script for The Muser Studio. Build:  iscc /DAppVersion=1.1.0 packaging\windows\muser.iss
; Input:  dist\TheMuser\   (PyInstaller output)    Output: dist\installer\TheMuser-Setup-<ver>-win64.exe
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{6F4C3B1E-7B1A-4E55-9D50-4D6E7A2C1A11}
AppName=The Muser
AppVersion={#AppVersion}
AppPublisher=The Muser Contributors
AppPublisherURL=https://github.com/myaiplug/the-muser
AppSupportURL=https://github.com/myaiplug/the-muser/issues
DefaultDirName={autopf}\The Muser
DefaultGroupName=The Muser
DisableProgramGroupPage=yes
; Installs for the current user by default (no admin prompt); the dialog offers "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\installer
OutputBaseFilename=TheMuser-Setup-{#AppVersion}-win64
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\TheMuser.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
DiskSpaceMBRequired=1500

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\..\dist\TheMuser\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\The Muser"; Filename: "{app}\TheMuser.exe"
Name: "{autodesktop}\The Muser"; Filename: "{app}\TheMuser.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TheMuser.exe"; Description: "Launch The Muser"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedLabel=The Muser is installed. Your tracks, exports and downloaded models are kept in %LOCALAPPDATA%\TheMuser, so uninstalling never deletes your music.%n%nFor the AI assistant, install Ollama from https://ollama.com/download (optional; the Studio also works in demo mode).
