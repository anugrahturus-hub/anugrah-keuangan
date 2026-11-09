[Setup]
AppId={{B3A1F6D2-5C7E-4E1B-9A44-2F0C8D7E6A11}
AppName=Anugrah Keuangan
AppVersion=1.0
AppPublisher=Anugrah Fotocopy
DefaultDirName={autopf}\AnugrahKeuangan
DefaultGroupName=Anugrah Keuangan
OutputDir=output
OutputBaseFilename=AnugrahKeuangan-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "dist\AnugrahKeuangan.exe"; DestDir: "{app}"
Source: "config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Anugrah Keuangan"; Filename: "{app}\AnugrahKeuangan.exe"
Name: "{autodesktop}\Anugrah Keuangan"; Filename: "{app}\AnugrahKeuangan.exe"

[Run]
Filename: "{app}\AnugrahKeuangan.exe"; Description: "Jalankan Anugrah Keuangan"; Flags: postinstall nowait skipifsilent
