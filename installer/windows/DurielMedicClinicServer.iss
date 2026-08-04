#define MyAppName "DurielMedic Clinic Server"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DurielMedic"
#define SourceRoot "..\..\dist\durielmedic-clinic-server"

[Setup]
AppId={{A11C14B5-069A-4F76-8350-786EE9B39E55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\DurielMedic Clinic Server
DefaultGroupName=DurielMedic
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\..\dist
OutputBaseFilename=DurielMedic-Clinic-Server-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DurielMedic Clinic Server"; Filename: "http://localhost:8000"
Name: "{commondesktop}\DurielMedic Clinic Server"; Filename: "http://localhost:8000"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\windows\Install-DurielMedicClinic.ps1"" -ActivationUrl ""{code:GetActivationUrl}"" -InstallDir ""{app}"""; StatusMsg: "Activating DurielMedic Clinic Server..."; Flags: runhidden waituntilterminated

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
