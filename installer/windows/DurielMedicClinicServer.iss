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

[Dirs]
Name: "{commonappdata}\DurielMedicClinicServer"; Permissions: users-modify
Name: "{commonappdata}\DurielMedicClinicServer\runtime"; Permissions: users-modify
Name: "{commonappdata}\DurielMedicClinicServer\runtime\logs"; Permissions: users-modify
Name: "{commonappdata}\DurielMedicClinicServer\runtime\media"; Permissions: users-modify

[Files]
Source: "..\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\durielmedic-clinic-server\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "Update-DurielMedicClinic.ps1"; DestDir: "{app}\updater"; Flags: ignoreversion
Source: "Configure-DurielMedicTasks.ps1"; DestDir: "{app}\updater"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{sys}\icacls.exe"; Parameters: """{commonappdata}\DurielMedicClinicServer"" /grant Users:(OI)(CI)M /T"; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""DurielMedic Clinic Server 9000"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=private,domain"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\updater\Configure-DurielMedicTasks.ps1"" -InstallDir ""{app}"" -Uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveDurielMedicTasks"

[Code]
var
  ActivationPage: TInputQueryWizardPage;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { An older clinic-server process may be holding the executable open. }
  { Stop only DurielMedic's known tasks/process before replacing the app. }
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "DurielMedic Clinic Server"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "DurielMedic Sync Worker"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM DurielMedicClinicServer.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

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

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ActivationArgs: String;
  ConfigureArgs: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Activating DurielMedic Clinic Server...';
    ActivationArgs := '--activate "' + ActivationPage.Values[0] + '"';
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), ActivationArgs, '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      RaiseException('Clinic activation failed. Generate a fresh activation URL in the cloud clinic settings and run Setup again.');
    end;

    WizardForm.StatusLabel.Caption := 'Enabling automatic clinic server and cloud sync...';
    ConfigureArgs := '-NoProfile -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\updater\Configure-DurielMedicTasks.ps1') + '" -InstallDir "' +
      ExpandConstant('{app}') + '" -Port 9000 -StartTasks';
    if (not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), ConfigureArgs,
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      RaiseException('DurielMedic background task setup failed. Run Setup as an administrator.');
    end;
  end;
end;
