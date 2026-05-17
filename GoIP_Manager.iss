; -- GoIP Manager Inno Setup Script --

[Setup]
AppName=GoIP Manager 1.3.1v
AppVersion=1.3.1
AppPublisher=Rico Yarte
AppPublisherURL=https://www.linkedin.com/in/rico-yarte/
DefaultDirName={autopf}\GoIP Manager
DefaultGroupName=GoIP Manager
OutputDir=dist_installer
OutputBaseFilename=GoIP_Manager_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=installer_files\icons\signal.ico
UninstallDisplayIcon={app}\GoIP.Manager.exe

[Files]
; Main EXE (built with PyInstaller)
Source: "dist\GoIP.Manager.exe"; DestDir: "{app}"; Flags: ignoreversion

; Copy the app icon into {app} (used by shortcuts)
Source: "installer_files\icons\signal.ico"; DestDir: "{app}"; Flags: ignoreversion

; Runtime files → go to AppData (user-writable)
Source: "installer_files\devices.json"; DestDir: "{userappdata}\GoIP.Manager"; Flags: onlyifdoesntexist
Source: "installer_files\notification_setting.json"; DestDir: "{userappdata}\GoIP.Manager"; Flags: onlyifdoesntexist
Source: "installer_files\restart_setting.json"; DestDir: "{userappdata}\GoIP.Manager"; Flags: onlyifdoesntexist
Source: "installer_files\msedgedriver.exe"; DestDir: "{userappdata}\GoIP.Manager"; Flags: ignoreversion
Source: "installer_files\logs\*"; DestDir: "{userappdata}\GoIP.Manager\logs"; Flags: recursesubdirs createallsubdirs

; ✅ UI icons → install next to the EXE so resource_path('icons/...') works
Source: "installer_files\icons\*"; DestDir: "{app}\installer_files\icons"; Flags: recursesubdirs createallsubdirs


[Tasks]
; Optional checkboxes during installation (Autostart removed from here)
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Icons]
; Start Menu shortcut (always created)
Name: "{group}\GoIP Manager"; Filename: "{app}\GoIP.Manager.exe"; IconFilename: "{app}\signal.ico"

; Desktop shortcut (only if user chooses)
Name: "{commondesktop}\GoIP Manager"; Filename: "{app}\GoIP.Manager.exe"; IconFilename: "{app}\signal.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "GoIP Manager"; \


[Run]
; Launch app after install
Filename: "{app}\GoIP.Manager.exe"; Description: "Launch GoIP Manager"; Flags: nowait postinstall skipifsilent
