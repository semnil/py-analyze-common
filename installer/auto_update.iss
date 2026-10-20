; What an auto-update run of an analyze-* installer does differently.
;
; analyze_common.update starts the installer with INSTALLER_ARGS, which carry
; /UPDATE=1.  Such a run waits for the app's mutex to disappear before
; installing, and starts the app again afterwards as the user who started the
; installer.  When the app still runs after AutoUpdateWaitMs, Setup's own
; "is currently running" message asks to close it: OK waits again, Cancel
; ends Setup without installing.  Any other run behaves as before.
;
; Define these before including this file:
;   MyAppName     the app's display name
;   MyAppExeName  the app's executable name
;   MyAppMutex    the mutex the app holds (analyze_common.update.hold_instance_mutex)
; The including script must not define InitializeSetup itself.

[Run]
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: IsAutoUpdate

[Code]
const
  AutoUpdateWaitMs = 30000;
  AutoUpdatePollMs = 200;

function IsAutoUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;

function InitializeSetup: Boolean;
var
  Waited: Integer;
begin
  Result := True;
  if not IsAutoUpdate then
    Exit;
  Waited := 0;
  while CheckForMutexes('{#MyAppMutex}') do
  begin
    if Waited >= AutoUpdateWaitMs then
    begin
      { MsgBox, unlike SuppressibleMsgBox, shows under /SUPPRESSMSGBOXES. }
      if MsgBox(FmtMessage(SetupMessage(msgSetupAppRunningError), ['{#MyAppName}']),
                mbError, MB_OKCANCEL) = IDCANCEL then
      begin
        Result := False;
        Exit;
      end;
      Waited := 0;
    end
    else
    begin
      Sleep(AutoUpdatePollMs);
      Waited := Waited + AutoUpdatePollMs;
    end;
  end;
end;
