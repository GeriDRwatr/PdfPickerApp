[Setup]
AppName=PdfPickerApp
AppVersion=1.0
AppPublisher=PdfPickerApp
DefaultDirName={autopf}\PdfPickerApp
DefaultGroupName=PdfPickerApp
OutputDir=installer_output
OutputBaseFilename=PdfPickerApp_Setup_v1.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\PdfPickerApp.exe
; Requires admin so we can write to HKLM
PrivilegesRequired=admin

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english";   MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столі";   GroupDescription: "Додаткові параметри"
Name: "setdefault";  Description: "Встановити як стандартний переглядач PDF"; GroupDescription: "Асоціація файлів"; Flags: unchecked

[Files]
Source: "dist\PdfPickerApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PdfPickerApp";          Filename: "{app}\PdfPickerApp.exe"
Name: "{commondesktop}\PdfPickerApp";  Filename: "{app}\PdfPickerApp.exe"; Tasks: desktopicon

; ── Registry ──────────────────────────────────────────────────────────────────
; All keys go to HKLM so the registration is visible to all users
; and Windows shows PdfPickerApp in "Open with" for everyone.

[Registry]
; ProgId — describes the file type handler
Root: HKLM; Subkey: "SOFTWARE\Classes\PdfPickerApp.PDF";                           ValueType: string; ValueName: "";                  ValueData: "PDF Document";                             Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Classes\PdfPickerApp.PDF\DefaultIcon";               ValueType: string; ValueName: "";                  ValueData: "{app}\PdfPickerApp.exe,0"
Root: HKLM; Subkey: "SOFTWARE\Classes\PdfPickerApp.PDF\shell\open";                ValueType: string; ValueName: "FriendlyAppName";    ValueData: "PdfPickerApp"
Root: HKLM; Subkey: "SOFTWARE\Classes\PdfPickerApp.PDF\shell\open\command";        ValueType: string; ValueName: "";                  ValueData: """{app}\PdfPickerApp.exe"" ""%1"""

; Link ProgId to .pdf extension — this is what adds the entry to "Open with"
Root: HKLM; Subkey: "SOFTWARE\Classes\.pdf\OpenWithProgids";                       ValueType: string; ValueName: "PdfPickerApp.PDF";   ValueData: ""

; App capabilities — required for "Default apps" Settings page
Root: HKLM; Subkey: "SOFTWARE\PdfPickerApp\Capabilities";                          ValueType: string; ValueName: "ApplicationName";        ValueData: "PdfPickerApp";           Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\PdfPickerApp\Capabilities";                          ValueType: string; ValueName: "ApplicationDescription";  ValueData: "PDF Viewer & Editor"
Root: HKLM; Subkey: "SOFTWARE\PdfPickerApp\Capabilities\FileAssociations";         ValueType: string; ValueName: ".pdf";               ValueData: "PdfPickerApp.PDF"
Root: HKLM; Subkey: "SOFTWARE\RegisteredApplications";                             ValueType: string; ValueName: "PdfPickerApp";        ValueData: "SOFTWARE\PdfPickerApp\Capabilities"

[Run]
Filename: "{app}\PdfPickerApp.exe"; Description: "Запустити PdfPickerApp"; Flags: nowait postinstall skipifsilent

[Code]
procedure SHChangeNotify(wEventId: Integer; uFlags: Cardinal;
                         dwItem1: Cardinal; dwItem2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

var
  ErrorCode: Integer;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    // Refresh Windows shell so "Open with" list updates immediately
    SHChangeNotify($08000000, $0000, 0, 0);

    // If user chose "Set as default", open Windows Settings → Default apps
    if WizardIsTaskSelected('setdefault') then
      ShellExecAsOriginalUser('open', 'ms-settings:defaultapps', '', '', SW_SHOW,
                              ewNoWait, ErrorCode);
  end;
end;
