#ifndef AppVersion
#define AppVersion "0.3.0"
#endif
[Setup]
#ifdef InstallTest
AppId={{7184842F-7369-4368-B812-46C6E56C7215}
AppName=A/L Results Collector (Install Test)
DefaultDirName={localappdata}\Programs\ALResultsCollector-InstallTest
DefaultGroupName=A-L Results Collector Install Test
OutputBaseFilename=ALResultsCollector-InstallTest-{#AppVersion}
#else
AppId={{FDC2638A-787B-4D1F-9945-E1D97B1B51F2}
AppName=A/L Results Collector
DefaultDirName={localappdata}\Programs\ALResultsCollector
DefaultGroupName=A-L Results Collector
OutputBaseFilename=ALResultsCollector-Setup-{#AppVersion}
#endif
AppVersion={#AppVersion}
OutputDir=..\dist\installer
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ALResultsCollector.exe
CloseApplications=yes
SetupIconFile=app.ico

[InstallDelete]
; This is the application-managed runtime payload, not the user's app-data.
; Remove stale Tk/Python DLLs when upgrading an old installation to Qt.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ALResultsCollector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\A-L Results Collector"; Filename: "{app}\ALResultsCollector.exe"
Name: "{group}\Uninstall A-L Results Collector"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\ALResultsCollector.exe"; Description: "Open A/L Results Collector"; Flags: nowait postinstall skipifsilent
