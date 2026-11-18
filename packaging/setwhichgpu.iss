; Inno Setup script for SetWhichGPU – build with tools/release/build_installer.ps1
; (expects the PyInstaller output in build\pyi-dist\SetWhichGPU and the collected licenses in build\licenses).

#ifndef AppVersion
  #error AppVersion must be passed: ISCC /DAppVersion=x.y.z setwhichgpu.iss
#endif

#define AppName "SetWhichGPU"
#define AppExe "SetWhichGPU.exe"
#define AppUrl "https://mastertoken.github.io/SetWhichGPU/"
#define RepoUrl "https://github.com/Mastertoken/SetWhichGPU"

[Setup]
AppId={{A02DBAA2-BEB0-4C42-A005-7B386B32E1EB}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=SetWhichGPU contributors
AppPublisherURL={#AppUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
AppCopyright=MIT License – SetWhichGPU contributors
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
; Per-user install by default: no administrator rights needed (the app itself never needs them either).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-setup
SetupIconFile=..\src\gpucc\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 11 – the "specific GPU" preference is a Windows 11 feature; Windows 10 is untested.
MinVersion=10.0.22000
ShowLanguageDialog=auto
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.AutostartTask=Start {#AppName} with Windows
german.AutostartTask={#AppName} mit Windows starten
spanish.AutostartTask=Iniciar {#AppName} con Windows
french.AutostartTask=Lancer {#AppName} avec Windows
english.AppStillRunning={#AppName} is still running. Please quit it from the tray menu and try again.
german.AppStillRunning={#AppName} läuft noch. Bitte über das Tray-Menü beenden und erneut versuchen.
spanish.AppStillRunning={#AppName} sigue en ejecución. Ciérralo desde el menú de la bandeja e inténtalo de nuevo.
french.AppStillRunning={#AppName} est toujours en cours d'exécution. Quittez-le depuis la zone de notification et réessayez.
english.AskRevert=Restore all GPU preferences that {#AppName} changed to their original state?%n%nChoose "No" to keep the GPU assignments you made.
german.AskRevert=Alle von {#AppName} geänderten GPU-Präferenzen auf den ursprünglichen Zustand zurücksetzen?%n%n"Nein" behält deine GPU-Zuweisungen.
spanish.AskRevert=¿Restablecer al estado original todas las preferencias de GPU que cambió {#AppName}?%n%nElige "No" para conservar tus asignaciones de GPU.
french.AskRevert=Rétablir l'état d'origine de toutes les préférences GPU modifiées par {#AppName} ?%n%nChoisissez « Non » pour conserver vos attributions de GPU.
english.AskDeleteData=Also delete the settings, change journal and logs of {#AppName}?
german.AskDeleteData=Auch Einstellungen, Änderungsprotokoll und Logs von {#AppName} löschen?
spanish.AskDeleteData=¿Eliminar también la configuración, el registro de cambios y los registros de {#AppName}?
french.AskDeleteData=Supprimer également les paramètres, le journal des modifications et les journaux de {#AppName} ?
english.CleanupFailed={#AppName} could not finish its clean-up (see the log). A GPU disabled by game mode can be enabled again in Device Manager.
german.CleanupFailed={#AppName} konnte nicht vollständig aufräumen (siehe Log). Eine vom Spielmodus deaktivierte GPU lässt sich im Geräte-Manager wieder aktivieren.
spanish.CleanupFailed={#AppName} no pudo completar la limpieza (consulta el registro). Una GPU desactivada por el modo juego se puede volver a activar en el Administrador de dispositivos.
french.CleanupFailed={#AppName} n'a pas pu terminer le nettoyage (voir le journal). Un GPU désactivé par le mode jeu peut être réactivé dans le Gestionnaire de périphériques.

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Updates replace the whole runtime so no stale files of an older version stay behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\build\pyi-dist\SetWhichGPU\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the app writes from its tray menu ("Start with Windows").
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WM_APP_QUIT = $8048;  { WM_APP + 0x48, see gpucc.platform.win32.user32 }
  MUTEX_NAME = 'Local\SetWhichGPU.Singleton';
  MESSAGE_WINDOW = 'SetWhichGPU.MessageWindow';

function AppRunning(): Boolean;
begin
  Result := CheckForMutexes(MUTEX_NAME);
end;

{ Ask a running instance to quit cleanly (it also ends game mode, which re-enables the GPU). }
procedure CloseRunningApp();
var
  Wnd: HWND;
  I: Integer;
begin
  Wnd := FindWindowByWindowName(MESSAGE_WINDOW);
  if Wnd <> 0 then
    PostMessage(Wnd, WM_APP_QUIT, 0, 0);
  for I := 1 to 80 do
  begin
    if not AppRunning() then
      Break;
    Sleep(250);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if AppRunning() then
  begin
    CloseRunningApp();
    if AppRunning() then
      Result := CustomMessage('AppStillRunning');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Params: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Before any file is removed: quit the app, re-enable a GPU left disabled by game mode,
      remove autostart and – if wanted – restore the GPU preferences from the change journal. }
    Params := '--uninstall';
    if SuppressibleMsgBox(CustomMessage('AskRevert'), mbConfirmation, MB_YESNO, IDNO) = IDYES then
      Params := Params + ' --revert-preferences';
    if not Exec(ExpandConstant('{app}\{#AppExe}'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
       or (ResultCode <> 0) then
      SuppressibleMsgBox(CustomMessage('CleanupFailed'), mbInformation, MB_OK, IDOK);
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    if SuppressibleMsgBox(CustomMessage('AskDeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\{#AppName}'), True, True, True);
  end;
end;
