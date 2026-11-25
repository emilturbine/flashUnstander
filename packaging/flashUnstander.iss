#ifndef AppVersion
  #error Pass AppVersion from pyproject.toml using /DAppVersion.
#endif

[Setup]
AppId=flashUnstander
AppName=flashUnstander
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\flashUnstander
DefaultGroupName=flashUnstander
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=flashUnstander-{#AppVersion}-setup
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\flashUnstander.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\flashUnstander"; Filename: "{app}\flashUnstander.exe"; WorkingDir: "{app}"
