#ifndef MyAppName
#define MyAppName "DurielMedic Clinic Server"
#endif
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif
#ifndef MyAppPublisher
#define MyAppPublisher "DurielMedic"
#endif
#ifndef MyAppExeName
#define MyAppExeName "DurielMedicClinicServer.exe"
#endif

[Setup]
AppId={{A11C14B5-069A-4F76-8350-786EE9B39E55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://durielmedic.com.ng
AppSupportURL=https://durielmedic.com.ng
AppUpdatesURL=https://durielmedic.com.ng
DefaultDirName={autopf}\DurielMedic Clinic Server
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\..\dist
OutputBaseFilename=DurielMedic-Clinic-Server-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "..\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""DurielMedic Clinic Server 9000"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=private,domain"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "--activate ""{code:GetActivationUrl}"""; StatusMsg: "Activating DurielMedic Clinic Server..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{commonappdata}\DurielMedicClinicServer"

[Code]
var
  ActivationPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ActivationPage := CreateInputQueryPage(
    wpSelectDir,
    'Clinic Activation',
    'Connect this local clinic server to the cloud account',
    'Paste the activation URL generated from the DurielMedic cloud account.'
  );
  ActivationPage.Add('Activation URL:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ActivationPage.ID then
  begin
    if Trim(ActivationPage.Values[0]) = '' then
    begin
      MsgBox('Enter the activation URL before continuing.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function GetActivationUrl(Param: String): String;
begin
  Result := ActivationPage.Values[0];
end;
