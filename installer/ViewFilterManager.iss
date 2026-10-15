#ifndef AppVersion
#define VersionFile FileOpen("..\VERSION")
#define AppVersion Trim(FileRead(VersionFile))
#expr FileClose(VersionFile)
#endif
#ifndef PayloadDir
 #define PayloadDir "..\artifacts\ViewFilterManager-" + AppVersion + "-Revit2026"
#endif
#ifndef OutputPath
 #define OutputPath "..\artifacts"
#endif
[Setup]
#ifdef TestRoot
AppId={{4966D9C5-84C7-42EF-88E9-9A9B2748FE1E}
OutputBaseFilename=ViewFilterManager-{#AppVersion}-Installer-Test
#else
AppId={{EF9954D7-1DE6-4EE0-BEF4-B88DBB2F16D7}
OutputBaseFilename=ViewFilterManager-{#AppVersion}-Revit2026-Setup
#endif
AppName=View Filter Manager
AppVersion={#AppVersion}
AppPublisher=View Filter Manager
AppPublisherURL=https://github.com/thephongluc/ViewFilterManager
AppSupportURL=https://github.com/thephongluc/ViewFilterManager/issues
AppUpdatesURL=https://github.com/thephongluc/ViewFilterManager/releases
DefaultDirName={code:GetInstallDir}
DisableDirPage=yes
UsePreviousAppDir=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupIconFile=..\runtime\icon.ico
UninstallDisplayIcon={code:GetBootstrapDir}\Content\icon.ico
SetupLogging=yes
OutputDir={#OutputPath}
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
UninstallDisplayName=View Filter Manager
UninstallFilesDir={app}\Setup
VersionInfoVersion={#AppVersion}.0
InfoBeforeFile=Before-install.txt
InfoAfterFile=After-install.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{code:GetBootstrapDir}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{tmp}\ViewFilterManager.addin"; DestDir: "{code:GetAddinsRoot}"; Flags: external ignoreversion
Source: "{tmp}\ViewFilterManager-version.txt"; DestDir: "{app}"; DestName: "installed-version.txt"; Flags: external ignoreversion

[Code]
var ProcessCheckFailed: Boolean;
function GetAddinsRoot(Param: String): String;
begin
#ifdef TestRoot
 Result := '{#TestRoot}\Addins';
#else
 Result := ExpandConstant('{userappdata}\Autodesk\Revit\Addins\2026');
#endif
end;
function GetInstallDir(Param: String): String;
begin
#ifdef TestRoot
 Result := '{#TestRoot}\App';
#else
 Result := ExpandConstant('{localappdata}\TPT\ViewFilterManager');
#endif
end;
function GetBootstrapDir(Param: String): String;
begin
 Result := GetAddinsRoot('') + '\ViewFilterManager\Versions\{#AppVersion}';
end;
function RevitRunning: Boolean;
var Locator, Services, Processes: Variant;
begin
 Result := True; ProcessCheckFailed := False;
 try
  Locator := CreateOleObject('WbemScripting.SWbemLocator');
  Services := Locator.ConnectServer('', 'root\cimv2');
  Processes := Services.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''Revit.exe''');
  Result := Processes.Count > 0;
 except
  ProcessCheckFailed := True;
  Log('Unable to check Revit processes; no installation changes allowed.');
 end;
end;
function RevitInstalled: Boolean;
var Location: String;
begin
#ifdef TestRoot
 Result := True;
#else
 Result := FileExists(ExpandConstant('{commonpf64}\Autodesk\Revit 2026\Revit.exe'));
 if not Result then
  if RegQueryStringValue(HKLM64, 'SOFTWARE\Autodesk\Revit\2026', 'InstallationLocation', Location) then
   Result := FileExists(AddBackslash(Location) + 'Revit.exe');
#endif
end;
function XmlEscape(Value: String): String;
begin
 StringChangeEx(Value, '&', '&amp;', True);
 StringChangeEx(Value, '<', '&lt;', True);
 StringChangeEx(Value, '>', '&gt;', True);
 StringChangeEx(Value, '"', '&quot;', True);
 Result := Value;
end;
function ManifestOwned: Boolean;
var Contents: AnsiString;
begin
 Result := not FileExists(GetAddinsRoot('') + '\ViewFilterManager.addin');
 if not Result then
  if LoadStringFromFile(GetAddinsRoot('') + '\ViewFilterManager.addin', Contents) then
   Result := Pos('C5B839AD-C5B7-4C67-A0FA-9F843AE927B3', Uppercase(String(Contents))) > 0;
end;
function NextVersionPart(var Value: String): Integer;
var At: Integer; Part: String;
begin
 At := Pos('.', Value);
 if At > 0 then begin Part := Copy(Value, 1, At - 1); Delete(Value, 1, At); end
 else begin Part := Value; Value := ''; end;
 Result := StrToIntDef(Part, 0);
end;
function CompareVersions(A, B: String): Integer;
var Index, ValueA, ValueB: Integer;
begin
 A := Trim(A); B := Trim(B); Result := 0;
 while (Length(A) > 0) and ((A[1] < '0') or (A[1] > '9')) do Delete(A, 1, 1);
 while (Length(B) > 0) and ((B[1] < '0') or (B[1] > '9')) do Delete(B, 1, 1);
 for Index := 0 to 2 do begin
  ValueA := NextVersionPart(A); ValueB := NextVersionPart(B);
  if ValueA > ValueB then begin Result := 1; exit; end;
  if ValueA < ValueB then begin Result := -1; exit; end;
 end;
end;
function InitializeSetup: Boolean;
begin
 Result := RevitInstalled;
 if not Result then SuppressibleMsgBox('Revit 2026 was not found. Install Revit 2026 before running this setup.', mbError, MB_OK, IDOK);
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Manifest, AssemblyPath: String; Lines: TArrayOfString; Previous: AnsiString;
begin
 Result := '';
 if CompareText(ExpandConstant('{app}'), GetInstallDir('')) <> 0 then begin
  Result := 'Install this add-in in its fixed current-user location.'; exit;
 end;
 if RevitRunning then begin
  if ProcessCheckFailed then Result := 'Windows could not verify whether Revit is running. Run setup again from your normal Windows account.'
  else Result := 'Save your work and close Revit, then retry installation.';
  exit;
 end;
 if not ManifestOwned then begin
  Result := 'ViewFilterManager.addin belongs to another application. No files have been replaced.'; exit;
 end;
 if LoadStringFromFile(ExpandConstant('{app}\installed-version.txt'), Previous) then
  if CompareVersions(String(Previous), '{#AppVersion}') > 0 then begin
   Result := 'A newer version is installed. Uninstall it before installing an older version.'; exit;
  end;
 AssemblyPath := GetBootstrapDir('') + '\ViewFilterManager.Addin.dll';
 Manifest := '<?xml version="1.0" encoding="utf-8"?>' + #13#10 +
 '<RevitAddIns><AddIn Type="Application"><Name>View Filter Manager</Name><Assembly>' + XmlEscape(AssemblyPath) +
 '</Assembly><AddInId>C5B839AD-C5B7-4C67-A0FA-9F843AE927B3</AddInId>' +
 '<FullClassName>ViewFilterManager.Addin.Application</FullClassName><VendorId>TPVF</VendorId>' +
 '<VendorDescription>View Filter Manager</VendorDescription></AddIn></RevitAddIns>';
 SetArrayLength(Lines, 1); Lines[0] := Manifest;
 if not SaveStringsToUTF8File(ExpandConstant('{tmp}\ViewFilterManager.addin'), Lines, False) then begin
  Result := 'Unable to prepare the Revit registration file.'; exit;
 end;
 Lines[0] := '{#AppVersion}';
 if not SaveStringToFile(ExpandConstant('{tmp}\ViewFilterManager-version.txt'), '{#AppVersion}', False) then
  Result := 'Unable to prepare the installation version record.';
end;
function InitializeUninstall: Boolean;
begin
 Result := not RevitRunning;
 if not Result then SuppressibleMsgBox('Save your work and close Revit before uninstalling. Windows must be able to verify that Revit is closed.', mbError, MB_OK, IDOK);
 if Result and not ManifestOwned then begin
  SuppressibleMsgBox('ViewFilterManager.addin was replaced by another application. Restore or remove that registration before uninstalling.', mbError, MB_OK, IDOK);
  Result := False;
 end;
end;
