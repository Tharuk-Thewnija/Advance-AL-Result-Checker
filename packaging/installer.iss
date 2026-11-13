#define AppVersion "0.2.1"
[Setup]
AppId={{FDC2638A-787B-4D1F-9945-E1D97B1B51F2}
AppName=A/L Results Collector
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\ALResultsCollector
DefaultGroupName=A-L Results Collector
OutputDir=..\dist\installer
OutputBaseFilename=ALResultsCollector-Setup-{#AppVersion}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ALResultsCollector.exe
CloseApplications=yes

[Files]
Source: "..\dist\ALResultsCollector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\A-L Results Collector"; Filename: "{app}\ALResultsCollector.exe"
Name: "{group}\Uninstall A-L Results Collector"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\ALResultsCollector.exe"; Description: "Open A/L Results Collector"; Flags: nowait postinstall skipifsilent
