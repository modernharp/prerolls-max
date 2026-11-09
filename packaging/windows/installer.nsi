; Prerolls Max installer (NSIS 3)
;
; Built by build.ps1, which first writes build\version.nsh (APP_VERSION,
; APP_VERSION_NUM from app/version.py), build\build_info.json and the icons.
;
; What it does:
; - Installs PrerollsMax.exe, PrerollsMaxService.exe and PrerollsMaxTray.exe
; - Prerolls Max replaces NeXroll. When NeXroll is found (registry
;   HKLM\Software\NeXroll, the NeXrollService service, its tray or app running,
;   or something on port 9393) a page offers:
;     Replace NeXroll (recommended): stop NeXroll and switch it off. It is not
;       uninstalled and its files stay, so its library can be imported in
;       Settings, Moving from NeXroll.
;     Keep NeXroll running too (advanced): leave NeXroll alone and give Prerolls
;       Max its own port (default 9494).
; - When the port is taken by another program, says so and asks for another one.
; - The port goes to %ProgramData%\Prerolls Max\startup.json ({"port": n}; no
;   "port" means 9393), the same file Settings > Moving from NeXroll writes.
;   PrerollsMax.exe, the service and the tray read it through one reader,
;   app/backend/port_config.py (PMAX_PORT still wins); the shortcuts open
;   http://localhost:<port>.
; - Optional: Windows service, Startup shortcut, FFmpeg and the Visual C++
;   runtime via winget, firewall rule.
; - Registers the "Prerolls Max Updater" task behind Install update.
;
; Command line:
;   /S                         silent; replaces NeXroll if it is there
;   /S /KEEPNEXROLL [/PORT=n]  silent, next to NeXroll (port n, default 9494)
;   /PORT=n                    use port n
;   /S /UPDATE                 what PrerollsMaxUpdater.ps1 runs: files only. The
;                              service, shortcuts, Startup entry, firewall rule,
;                              port and NeXroll stay as they are; nothing starts.
; Exit codes: 0 done, 1 cancelled, 2 the port is in use or not valid.

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "nsDialogs.nsh"
!include "x64.nsh"
!include "build\version.nsh"

!define NEXROLL_PORT "9393"
!define ALONGSIDE_PORT "9494"
!define REG_KEY "Software\Prerolls Max"

Name "Prerolls Max"
InstallDir "$PROGRAMFILES64\Prerolls Max"
InstallDirRegKey HKLM "${REG_KEY}" "InstallDir"
RequestExecutionLevel admin
ShowInstDetails show
Unicode true
Icon "PrerollsMax_ICON\icon_1758297097_64x64.ico"
UninstallIcon "PrerollsMax_ICON\icon_1758297097_32x32.ico"

VIProductVersion "${APP_VERSION_NUM}"
VIAddVersionKey /LANG=1033 "ProductName" "Prerolls Max"
VIAddVersionKey /LANG=1033 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "CompanyName" "Prerolls Max"
VIAddVersionKey /LANG=1033 "FileDescription" "Prerolls Max Installer"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Prerolls Max, based on NeXroll by JFLXCLOUD. MIT licence."
OutFile "dist\PrerollsMax_Installer_v${APP_VERSION}.exe"

; Variables
Var PREROLL_PATH
Var hPrerollEdit
Var UPDATE_MODE
Var PORT
Var NEXROLL_FOUND
Var NEXROLL_WHAT
Var KEEP_NEXROLL
Var NEXROLL_HANDLED
Var PORT_GIVEN
Var hReplaceRadio
Var hKeepRadio
Var hPortEdit
Var hPortLabel

; Interface
!define MUI_ABORTWARNING
!define MUI_HEADERIMAGE

; Pages
!insertmacro MUI_PAGE_WELCOME
Page custom NeXrollPageCreate NeXrollPageLeave
Page custom PortPageCreate PortPageLeave
!insertmacro MUI_PAGE_DIRECTORY
Page custom PrerollPathPageCreate PrerollPathPageLeave
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

; ------------------------------
; NeXroll and the port
; ------------------------------

; $NEXROLL_FOUND = 1 when NeXroll is installed or running; $NEXROLL_WHAT says what was seen.
Function DetectNeXroll
  StrCpy $NEXROLL_FOUND "0"
  StrCpy $NEXROLL_WHAT ""
  SetRegView 64
  ReadRegStr $0 HKLM "Software\NeXroll" "InstallDir"
  ${If} $0 == ""
    SetRegView 32
    ReadRegStr $0 HKLM "Software\NeXroll" "InstallDir"
    SetRegView 64
  ${EndIf}
  ${If} $0 != ""
    StrCpy $NEXROLL_FOUND "1"
    StrCpy $NEXROLL_WHAT "$NEXROLL_WHAT$\r$\n  - NeXroll is installed in $0"
  ${EndIf}
  nsExec::ExecToStack 'sc query "NeXrollService"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    StrCpy $NEXROLL_FOUND "1"
    StrCpy $NEXROLL_WHAT "$NEXROLL_WHAT$\r$\n  - the NeXroll Windows service"
  ${EndIf}
  nsExec::ExecToStack 'cmd /c tasklist /NH /FI "IMAGENAME eq NeXrollTray.exe" | findstr /I "NeXrollTray.exe"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    StrCpy $NEXROLL_FOUND "1"
    StrCpy $NEXROLL_WHAT "$NEXROLL_WHAT$\r$\n  - the NeXroll tray icon is running"
  ${EndIf}
  nsExec::ExecToStack 'cmd /c tasklist /NH /FI "IMAGENAME eq NeXroll.exe" | findstr /I "NeXroll.exe"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    StrCpy $NEXROLL_FOUND "1"
    StrCpy $NEXROLL_WHAT "$NEXROLL_WHAT$\r$\n  - NeXroll is running"
  ${EndIf}
FunctionEnd

; The port saved in %ProgramData%\Prerolls Max\startup.json into $PORT ("" when none).
Function ReadPortFile
  StrCpy $PORT ""
  nsExec::ExecToStack 'powershell -NoProfile -NonInteractive -Command "try { $$p = (Get-Content -Raw -LiteralPath (Join-Path $$env:ProgramData \"Prerolls Max\startup.json\") | ConvertFrom-Json).port; if ($$p) { [Console]::Write([int]$$p) } } catch { }"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    Push $1
    Call ValidPort
    ${If} $0 == "1"
      StrCpy $PORT $1
    ${EndIf}
  ${EndIf}
FunctionEnd

; Save $PORT in startup.json (other keys stay); 9393 removes "port" instead.
Function WritePortFile
  ${If} $PORT == ${NEXROLL_PORT}
    StrCpy $R7 "$$d.Remove('port')"
  ${Else}
    StrCpy $R7 "$$d['port'] = $PORT"
  ${EndIf}
  nsExec::ExecToStack 'powershell -NoProfile -NonInteractive -Command "$$f = Join-Path $$env:ProgramData \"Prerolls Max\startup.json\"; $$d = @{}; if (Test-Path -LiteralPath $$f) { try { (Get-Content -Raw -LiteralPath $$f | ConvertFrom-Json).psobject.Properties | ForEach-Object { $$d[$$_.Name] = $$_.Value } } catch { } }; $R7; New-Item -ItemType Directory -Force -Path (Split-Path $$f) | Out-Null; [IO.File]::WriteAllText($$f, ($$d | ConvertTo-Json -Compress))"'
  Pop $0
  Pop $1
  DetailPrint "Port $PORT saved in startup.json ($0)"
FunctionEnd

; Push a port; pops it and leaves $0 = 1 when something listens on it, else 0.
Function PortInUse
  Exch $R9
  nsExec::ExecToStack 'cmd /c netstat -ano | findstr LISTENING | findstr /C:":$R9 "'
  Pop $0
  Pop $R8
  ${If} $0 == 0
    StrCpy $0 "1"
  ${Else}
    StrCpy $0 "0"
  ${EndIf}
  Pop $R9
FunctionEnd

; Push a value; leaves $0 = 1 when it is a usable port (1024-65535), else 0.
Function ValidPort
  Exch $R9
  StrCpy $0 "0"
  ${If} $R9 != ""
    IntOp $R8 $R9 + 0
    ${If} "$R8" == "$R9"
    ${AndIf} $R8 >= 1024
    ${AndIf} $R8 <= 65535
      StrCpy $0 "1"
    ${EndIf}
  ${EndIf}
  Pop $R9
FunctionEnd

; Stop NeXroll and switch it off: the service no longer starts, its tray no
; longer starts at sign-in. Nothing is uninstalled or deleted.
Function SwitchOffNeXroll
  ${If} $NEXROLL_HANDLED == "1"
    Return
  ${EndIf}
  StrCpy $NEXROLL_HANDLED "1"
  DetailPrint "Stopping NeXroll and switching it off (it stays installed)..."
  nsExec::ExecToStack 'sc stop "NeXrollService"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'sc config "NeXrollService" start= disabled'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM NeXrollTray.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM NeXroll.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM NeXrollService.exe /T'
  Pop $0
  Pop $1
  ; Startup shortcuts are renamed, not deleted, so NeXroll can be switched back on.
  SetShellVarContext current
  Call RenameNeXrollStartup
  SetShellVarContext all
  Call RenameNeXrollStartup
  SetShellVarContext current
  SetRegView 64
  WriteRegStr HKLM "${REG_KEY}" "NeXrollSwitchedOff" "1"
  Sleep 2000
FunctionEnd

Function RenameNeXrollStartup
  ${If} ${FileExists} "$SMSTARTUP\NeXroll Tray.lnk"
    Rename "$SMSTARTUP\NeXroll Tray.lnk" "$SMSTARTUP\NeXroll Tray.lnk.switched-off-by-prerolls-max"
  ${EndIf}
  ${If} ${FileExists} "$SMSTARTUP\NeXroll.lnk"
    Rename "$SMSTARTUP\NeXroll.lnk" "$SMSTARTUP\NeXroll.lnk.switched-off-by-prerolls-max"
  ${EndIf}
FunctionEnd

Function NeXrollPageCreate
  ${If} $UPDATE_MODE == "1"
  ${OrIf} $NEXROLL_FOUND != "1"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "Prerolls Max replaces NeXroll" "NeXroll was found on this computer."
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateLabel} 0 0 100% 44u "Prerolls Max replaces NeXroll. NeXroll will be stopped and switched off (not uninstalled, your NeXroll files stay). Your NeXroll library can be imported in Settings, Moving from NeXroll.$\r$\n$\r$\nFound:$NEXROLL_WHAT"
  Pop $0
  ${NSD_CreateRadioButton} 0 50u 100% 12u "Replace NeXroll (recommended)"
  Pop $hReplaceRadio
  ${NSD_OnClick} $hReplaceRadio NeXrollChoiceClicked
  ${NSD_CreateLabel} 12u 62u 95% 18u "Stop NeXroll and switch it off. Prerolls Max uses port ${NEXROLL_PORT}, so your bookmarks and media server settings keep working."
  Pop $0
  ${NSD_CreateRadioButton} 0 84u 100% 12u "Keep NeXroll running too (advanced)"
  Pop $hKeepRadio
  ${NSD_OnClick} $hKeepRadio NeXrollChoiceClicked
  ${NSD_CreateLabel} 12u 96u 95% 18u "NeXroll is left alone. Prerolls Max needs its own port. Let only one of them manage intros on each media server."
  Pop $0
  ${NSD_CreateLabel} 12u 118u 60u 12u "Prerolls Max port:"
  Pop $hPortLabel
  ${NSD_CreateNumber} 75u 116u 40u 12u "$PORT"
  Pop $hPortEdit
  ${If} $KEEP_NEXROLL == "1"
    ${NSD_Check} $hKeepRadio
  ${Else}
    ${NSD_Check} $hReplaceRadio
  ${EndIf}
  Call NeXrollChoiceChanged
  nsDialogs::Show
FunctionEnd

Function NeXrollChoiceClicked
  Pop $0 ; the clicked control
  Call NeXrollChoiceChanged
FunctionEnd

Function NeXrollChoiceChanged
  ${NSD_GetState} $hKeepRadio $1
  ${If} $1 == ${BST_CHECKED}
    EnableWindow $hPortEdit 1
    EnableWindow $hPortLabel 1
    ${NSD_GetText} $hPortEdit $2
    ${If} $2 == ${NEXROLL_PORT}
      ${NSD_SetText} $hPortEdit "${ALONGSIDE_PORT}"
    ${EndIf}
  ${Else}
    ${NSD_SetText} $hPortEdit "${NEXROLL_PORT}"
    EnableWindow $hPortEdit 0
    EnableWindow $hPortLabel 0
  ${EndIf}
FunctionEnd

Function NeXrollPageLeave
  ${NSD_GetState} $hKeepRadio $1
  ${If} $1 == ${BST_CHECKED}
    StrCpy $KEEP_NEXROLL "1"
    ${NSD_GetText} $hPortEdit $PORT
    Push $PORT
    Call ValidPort
    ${If} $0 != "1"
      MessageBox MB_ICONEXCLAMATION|MB_OK "Enter a port number from 1024 to 65535, for example ${ALONGSIDE_PORT}."
      Abort
    ${EndIf}
    ${If} $PORT == ${NEXROLL_PORT}
      MessageBox MB_ICONEXCLAMATION|MB_OK "NeXroll uses port ${NEXROLL_PORT}. Choose another port for Prerolls Max, for example ${ALONGSIDE_PORT}."
      Abort
    ${EndIf}
    Push $PORT
    Call PortInUse
    ${If} $0 == "1"
      MessageBox MB_ICONEXCLAMATION|MB_OK "Port $PORT is in use by another program. Choose a different port."
      Abort
    ${EndIf}
  ${Else}
    StrCpy $KEEP_NEXROLL "0"
    StrCpy $PORT "${NEXROLL_PORT}"
    Call SwitchOffNeXroll
  ${EndIf}
FunctionEnd

; Shown only when the port is still taken by something that isn't NeXroll.
Function PortPageCreate
  ${If} $UPDATE_MODE == "1"
    Abort
  ${EndIf}
  Push $PORT
  Call PortInUse
  ${If} $0 != "1"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "Port $PORT is in use" "Another program is using the port Prerolls Max would use."
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateLabel} 0 0 100% 40u "Port $PORT is in use by another program, so Prerolls Max can't use it.$\r$\n$\r$\nEnter a free port below (for example ${ALONGSIDE_PORT}), or click Cancel, close the other program and run setup again."
  Pop $0
  ${NSD_CreateLabel} 0 48u 60u 12u "Prerolls Max port:"
  Pop $0
  ${NSD_CreateNumber} 62u 46u 40u 12u "${ALONGSIDE_PORT}"
  Pop $hPortEdit
  nsDialogs::Show
FunctionEnd

Function PortPageLeave
  ${NSD_GetText} $hPortEdit $1
  Push $1
  Call ValidPort
  ${If} $0 != "1"
    MessageBox MB_ICONEXCLAMATION|MB_OK "Enter a port number from 1024 to 65535, for example ${ALONGSIDE_PORT}."
    Abort
  ${EndIf}
  Push $1
  Call PortInUse
  ${If} $0 == "1"
    MessageBox MB_ICONEXCLAMATION|MB_OK "Port $1 is in use too. Choose a different port."
    Abort
  ${EndIf}
  StrCpy $PORT $1
FunctionEnd

; ------------------------------
; Custom Page - Preroll Path
; ------------------------------
; The preroll folder Prerolls Max uses now: the registry's PrerollPath (64-bit
; view first, then 32-bit), else the app's own default.
Function ResolvePrerollPath
  SetRegView 64
  ReadRegStr $PREROLL_PATH HKLM "${REG_KEY}" "PrerollPath"
  ${If} $PREROLL_PATH == ""
    SetRegView 32
    ReadRegStr $PREROLL_PATH HKLM "${REG_KEY}" "PrerollPath"
    SetRegView 64
  ${EndIf}
  ${If} $PREROLL_PATH == ""
    ReadEnvStr $PREROLL_PATH "ProgramData"
    StrCpy $PREROLL_PATH "$PREROLL_PATH\Prerolls Max\Prerolls"
  ${EndIf}
FunctionEnd

Function PrerollPathPageCreate
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateLabel} 0 0 100% 12u "Select Preroll Video Storage"
  ${NSD_CreateLabel} 0 18u 100% 12u "Choose a directory where Preroll videos will be stored:"
  Call ResolvePrerollPath
  ${NSD_CreateText} 0 36u 80% 12u "$PREROLL_PATH"
  Pop $hPrerollEdit
  ${NSD_CreateButton} 82% 35u 18% 14u "Browse..."
  Pop $1
  ${NSD_OnClick} $1 PrerollPathBrowse
  nsDialogs::Show
FunctionEnd

Function PrerollPathBrowse
  nsDialogs::SelectFolderDialog "Select Preroll Video Storage Folder" "$PREROLL_PATH"
  Pop $0
  ${If} $0 == "error"
    Return
  ${EndIf}
  ${If} $0 == ""
    Return
  ${EndIf}
  StrCpy $PREROLL_PATH "$0"
  ${NSD_SetText} $hPrerollEdit "$PREROLL_PATH"
FunctionEnd

Function PrerollPathPageLeave
  ${NSD_GetText} $hPrerollEdit $PREROLL_PATH
  ${If} $PREROLL_PATH == ""
    ReadEnvStr $PREROLL_PATH "ProgramData"
    StrCpy $PREROLL_PATH "$PREROLL_PATH\Prerolls Max\Prerolls"
  ${EndIf}
FunctionEnd

; ------------------------------
; Components
; ------------------------------
Section "!Prerolls Max Application (Required)" SEC_APP
  SectionIn RO
  SetRegView 64

  ; Stop a running Prerolls Max before copying files, so the new one can bind
  ; its port and the old files aren't locked.
  nsExec::ExecToStack 'cmd /c sc stop "PrerollsMaxService"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMaxTray.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMax.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMaxService.exe /T'
  Pop $0
  Pop $1
  Sleep 1500

  SetOutPath "$INSTDIR"
  SetOverwrite on

  ; Built by build.ps1 (PyInstaller, one file each)
  File "dist\PrerollsMax.exe"
  File "dist\PrerollsMaxService.exe"
  File "dist\PrerollsMaxTray.exe"
  ; Run by the Prerolls Max Updater task (registered below)
  File "PrerollsMaxUpdater.ps1"
  ; Which GitHub repository publishes this copy's updates (read by the updater)
  File /nonfatal "build\build_info.json"
  File "..\..\app\CHANGELOG.md"
  File "..\..\LICENSE"
  File "..\..\NOTICE.md"

  ; Files older installs left behind
  Delete "$INSTDIR\setup_plex_token.exe"
  Delete "$INSTDIR\start_windows.bat"
  nsExec::ExecToStack 'cmd /c if exist "$INSTDIR\resources" rd /s /q "$INSTDIR\resources"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'cmd /c if exist "$INSTDIR\frontend" rd /s /q "$INSTDIR\frontend"'
  Pop $0
  Pop $1

  ; A silent install never showed the folder page
  ${If} $PREROLL_PATH == ""
    Call ResolvePrerollPath
  ${EndIf}

  CreateDirectory "$PREROLL_PATH"
  ; Standard Users may change the preroll folder (Modify, recursive)
  nsExec::ExecToStack 'icacls "$PREROLL_PATH" /grant *S-1-5-32-545:(OI)(CI)M /T /C'
  Pop $0
  Pop $1

  ; Older versions kept prerolls under $INSTDIR\data\prerolls
  IfFileExists "$INSTDIR\data\prerolls\*.*" 0 no_legacy_prerolls
    DetailPrint "Moving existing prerolls from $INSTDIR\data\prerolls to $PREROLL_PATH"
    nsExec::ExecToStack 'cmd /c xcopy /E /I /Y "$INSTDIR\data\prerolls" "$PREROLL_PATH"'
    Pop $0
    Pop $1
  no_legacy_prerolls:

  WriteRegStr HKLM "${REG_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${REG_KEY}" "PrerollPath" "$PREROLL_PATH"
  WriteRegStr HKLM "${REG_KEY}" "Version" "${APP_VERSION}"

  ; The port, in startup.json (see the top of this file). An update keeps it.
  ${If} $UPDATE_MODE != "1"
    Call WritePortFile
  ${EndIf}

  ; ProgramData\Prerolls Max (database, logs) writable by standard Users
  nsExec::ExecToStack 'cmd /c if not exist "%ProgramData%\Prerolls Max\logs" mkdir "%ProgramData%\Prerolls Max\logs"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'cmd /c icacls "%ProgramData%\Prerolls Max" /grant *S-1-5-32-545:(OI)(CI)M /T /C'
  Pop $0
  Pop $1

  ; Shortcuts go to the current user's folders. An update runs as SYSTEM and
  ; the shortcuts from the first install still work.
  ${If} $UPDATE_MODE != "1"
    CreateDirectory "$SMPROGRAMS\Prerolls Max"
    ; "Prerolls Max" opens the web page on the chosen port
    Delete "$SMPROGRAMS\Prerolls Max\Prerolls Max.lnk"
    Delete "$DESKTOP\Prerolls Max.lnk"
    WriteINIStr "$SMPROGRAMS\Prerolls Max\Prerolls Max.url" "InternetShortcut" "URL" "http://localhost:$PORT/"
    WriteINIStr "$SMPROGRAMS\Prerolls Max\Prerolls Max.url" "InternetShortcut" "IconFile" "$INSTDIR\PrerollsMax.exe"
    WriteINIStr "$SMPROGRAMS\Prerolls Max\Prerolls Max.url" "InternetShortcut" "IconIndex" "0"
    WriteINIStr "$DESKTOP\Prerolls Max.url" "InternetShortcut" "URL" "http://localhost:$PORT/"
    WriteINIStr "$DESKTOP\Prerolls Max.url" "InternetShortcut" "IconFile" "$INSTDIR\PrerollsMax.exe"
    WriteINIStr "$DESKTOP\Prerolls Max.url" "InternetShortcut" "IconIndex" "0"
    CreateShortCut "$SMPROGRAMS\Prerolls Max\Prerolls Max Tray.lnk" "$INSTDIR\PrerollsMaxTray.exe" "" "$INSTDIR\PrerollsMaxTray.exe" 0
    CreateShortCut "$SMPROGRAMS\Prerolls Max\Uninstall.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
  ${EndIf}

  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; The task Install update starts. The script leaves an up-to-date task
  ; alone, which matters during an update: the task is running the old copy.
  nsExec::ExecToStack 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\PrerollsMaxUpdater.ps1" -Register -InstallDir "$INSTDIR"'
  Pop $0
  Pop $1
  DetailPrint "Updater task ($0): $1"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "DisplayName" "Prerolls Max"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "Publisher" "Prerolls Max"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max" "DisplayIcon" "$INSTDIR\PrerollsMax.exe"
SectionEnd

Section "Install as Windows Service" SEC_SERVICE
  SetOutPath "$INSTDIR"
  Call InstallService
SectionEnd

Section "Start with Windows (Startup Shortcut)" SEC_STARTUP
  CreateShortCut "$SMSTARTUP\Prerolls Max Tray.lnk" "$INSTDIR\PrerollsMaxTray.exe" "" "$INSTDIR\PrerollsMaxTray.exe" 0
SectionEnd

Section "Install Dependencies (FFmpeg via winget)" SEC_DEPS
  nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements -e }"'
  Pop $0
  Pop $1
SectionEnd

Section "Visual C++ Runtime (YouTube downloader)" SEC_VCREDIST
  ; The YouTube PO-token provider's Node modules (canvas) need the Microsoft
  ; Visual C++ 2015-2022 x64 runtime. winget is slow to start, so only when missing.
  SetRegView 64
  ReadRegDWORD $1 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" "Installed"
  ${If} $1 = 1
    DetailPrint "Visual C++ runtime already installed - skipping."
  ${Else}
    DetailPrint "Installing Visual C++ runtime (required by the YouTube downloader)..."
    nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Get-Command winget -ErrorAction SilentlyContinue) { winget install Microsoft.VCRedist.2015+.x64 --accept-source-agreements --accept-package-agreements -e }"'
    Pop $0
    Pop $1
  ${EndIf}
SectionEnd

; Record where ffmpeg/ffprobe are, so the service and tray find them without PATH.
Section "FFmpeg Path Registration (Auto-detect)" SEC_FFREG
  SetRegView 64
  StrCpy $0 ""
  IfFileExists "$PROGRAMFILES64\ffmpeg\bin\ffmpeg.exe" 0 +2
    StrCpy $0 "$PROGRAMFILES64\ffmpeg\bin\ffmpeg.exe"
  IfFileExists "$PROGRAMFILES\ffmpeg\bin\ffmpeg.exe" 0 +2
    StrCpy $0 "$PROGRAMFILES\ffmpeg\bin\ffmpeg.exe"
  IfFileExists "C:\ProgramData\chocolatey\bin\ffmpeg.exe" 0 +2
    StrCpy $0 "C:\ProgramData\chocolatey\bin\ffmpeg.exe"
  IfFileExists "C:\ffmpeg\bin\ffmpeg.exe" 0 +2
    StrCpy $0 "C:\ffmpeg\bin\ffmpeg.exe"
  ${If} $0 != ""
    WriteRegStr HKLM "${REG_KEY}" "FFmpegPath" "$0"
  ${EndIf}
  StrCpy $1 ""
  IfFileExists "$PROGRAMFILES64\ffmpeg\bin\ffprobe.exe" 0 +2
    StrCpy $1 "$PROGRAMFILES64\ffmpeg\bin\ffprobe.exe"
  IfFileExists "$PROGRAMFILES\ffmpeg\bin\ffprobe.exe" 0 +2
    StrCpy $1 "$PROGRAMFILES\ffmpeg\bin\ffprobe.exe"
  IfFileExists "C:\ProgramData\chocolatey\bin\ffprobe.exe" 0 +2
    StrCpy $1 "C:\ProgramData\chocolatey\bin\ffprobe.exe"
  IfFileExists "C:\ffmpeg\bin\ffprobe.exe" 0 +2
    StrCpy $1 "C:\ffmpeg\bin\ffprobe.exe"
  ${If} $1 != ""
    WriteRegStr HKLM "${REG_KEY}" "FFprobePath" "$1"
  ${EndIf}
SectionEnd

Section "Windows Firewall Rule (allow the Prerolls Max port)" SEC_FIREWALL
  ; One rule named "Prerolls Max", for the port chosen above
  nsExec::ExecToStack 'netsh advfirewall firewall delete rule name="Prerolls Max"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'netsh advfirewall firewall delete rule name="Prerolls Max (TCP 9393)"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'netsh advfirewall firewall add rule name="Prerolls Max" dir=in action=allow protocol=TCP localport=$PORT'
  Pop $0
  Pop $1
SectionEnd

Function InstallService
  DetailPrint "Installing and starting the Prerolls Max service..."
  ${If} ${FileExists} "$INSTDIR\PrerollsMaxService.exe"
    nsExec::ExecToStack '"$INSTDIR\PrerollsMaxService.exe" --startup auto install'
    Pop $0
    Pop $1
    DetailPrint "Service install ($0): $1"
    ; An existing service keeps its settings; make sure it starts with Windows.
    nsExec::ExecToStack 'sc config "PrerollsMaxService" start= auto'
    Pop $0
    Pop $1
    Sleep 1000
    nsExec::ExecToStack '"$INSTDIR\PrerollsMaxService.exe" start'
    Pop $0
    Pop $1
    DetailPrint "Service start ($0): $1"
  ${Else}
    DetailPrint "Warning: PrerollsMaxService.exe not found; service will not be installed."
  ${EndIf}
FunctionEnd

; ------------------------------
; Uninstaller
; ------------------------------
Section "Uninstall"
  SetRegView 64

  nsExec::ExecToStack 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\PrerollsMaxUpdater.ps1" -Unregister'
  Pop $0
  Pop $1

  IfFileExists "$INSTDIR\PrerollsMaxService.exe" 0 no_service
    nsExec::ExecToStack '"$INSTDIR\PrerollsMaxService.exe" stop'
    Pop $0
    Pop $1
    nsExec::ExecToStack '"$INSTDIR\PrerollsMaxService.exe" remove'
    Pop $0
    Pop $1
  no_service:

  nsExec::ExecToStack 'taskkill /F /IM PrerollsMaxTray.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMax.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMaxService.exe /T'
  Pop $0
  Pop $1

  nsExec::ExecToStack 'netsh advfirewall firewall delete rule name="Prerolls Max"'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'netsh advfirewall firewall delete rule name="Prerolls Max (TCP 9393)"'
  Pop $0
  Pop $1

  Delete "$SMPROGRAMS\Prerolls Max\Prerolls Max.url"
  Delete "$SMPROGRAMS\Prerolls Max\Prerolls Max.lnk"
  Delete "$SMPROGRAMS\Prerolls Max\Prerolls Max Tray.lnk"
  Delete "$SMPROGRAMS\Prerolls Max\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Prerolls Max"
  Delete "$DESKTOP\Prerolls Max.url"
  Delete "$DESKTOP\Prerolls Max.lnk"
  Delete "$SMSTARTUP\Prerolls Max.lnk"
  Delete "$SMSTARTUP\Prerolls Max Tray.lnk"

  ; Program files only: the database, settings and prerolls stay
  Delete "$INSTDIR\PrerollsMax.exe"
  Delete "$INSTDIR\PrerollsMaxService.exe"
  Delete "$INSTDIR\PrerollsMaxTray.exe"
  Delete "$INSTDIR\PrerollsMaxUpdater.ps1"
  Delete "$INSTDIR\build_info.json"
  RMDir /r "$INSTDIR\update"
  Delete "$INSTDIR\CHANGELOG.md"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\NOTICE.md"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  DeleteRegValue HKLM "${REG_KEY}" "InstallDir"
  DeleteRegValue HKLM "${REG_KEY}" "PrerollPath"
  DeleteRegValue HKLM "${REG_KEY}" "Version"
  DeleteRegValue HKLM "${REG_KEY}" "FFmpegPath"
  DeleteRegValue HKLM "${REG_KEY}" "FFprobePath"
  DeleteRegValue HKLM "${REG_KEY}" "NeXrollSwitchedOff"
  DeleteRegKey /ifempty HKLM "${REG_KEY}"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Prerolls Max"
SectionEnd

; ------------------------------
; Init
; ------------------------------
Function .onInit
  SetRegView 64
  StrCpy $KEEP_NEXROLL "0"
  StrCpy $NEXROLL_HANDLED "0"
  StrCpy $PORT_GIVEN ""
  ${GetParameters} $R0

  ; /UPDATE (from PrerollsMaxUpdater.ps1): install the files and change nothing
  ; else. The service, Startup and firewall sections would add back what the
  ; user turned off; winget needs the signed-in user, and an update runs as SYSTEM.
  ClearErrors
  ${GetOptions} $R0 "/UPDATE" $R1
  ${IfNot} ${Errors}
    StrCpy $UPDATE_MODE "1"
    SectionSetFlags ${SEC_SERVICE} 0
    SectionSetFlags ${SEC_STARTUP} 0
    SectionSetFlags ${SEC_DEPS} 0
    SectionSetFlags ${SEC_VCREDIST} 0
    SectionSetFlags ${SEC_FIREWALL} 0
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/KEEPNEXROLL" $R1
  ${IfNot} ${Errors}
    StrCpy $KEEP_NEXROLL "1"
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/PORT=" $R1
  ${IfNot} ${Errors}
    StrCpy $PORT_GIVEN $R1
  ${EndIf}

  ; Stop a running Prerolls Max so an upgrade can replace its files and its
  ; port is free for the checks below.
  nsExec::ExecToStack 'sc stop "PrerollsMaxService"'
  Pop $0
  Pop $1
  Sleep 1500
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMaxTray.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMax.exe /T'
  Pop $0
  Pop $1
  nsExec::ExecToStack 'taskkill /F /IM PrerollsMaxService.exe /T'
  Pop $0
  Pop $1
  Sleep 1500

  ${If} $UPDATE_MODE == "1"
    Return
  ${EndIf}

  ; The port: /PORT=, else the one this computer already uses, else 9393 (or
  ; 9494 next to NeXroll).
  Call ReadPortFile
  ${If} $PORT == ""
    StrCpy $PORT "${NEXROLL_PORT}"
  ${EndIf}
  ${If} $KEEP_NEXROLL == "1"
  ${AndIf} $PORT == ${NEXROLL_PORT}
    StrCpy $PORT "${ALONGSIDE_PORT}"
  ${EndIf}
  ${If} $PORT_GIVEN != ""
    Push $PORT_GIVEN
    Call ValidPort
    ${If} $0 != "1"
      MessageBox MB_ICONSTOP|MB_OK "/PORT=$PORT_GIVEN is not a port number from 1024 to 65535." /SD IDOK
      SetErrorLevel 2
      Quit
    ${EndIf}
    StrCpy $PORT $PORT_GIVEN
  ${EndIf}

  Call DetectNeXroll

  ${If} ${Silent}
    ${If} $KEEP_NEXROLL == "1"
      ${If} $PORT == ${NEXROLL_PORT}
        StrCpy $PORT "${ALONGSIDE_PORT}"
      ${EndIf}
    ${ElseIf} $NEXROLL_FOUND == "1"
      Call SwitchOffNeXroll
    ${EndIf}
    Push $PORT
    Call PortInUse
    ${If} $0 == "1"
      ; Silent installs can't ask: fail with exit code 2 (see the top of this file).
      SetErrorLevel 2
      Quit
    ${EndIf}
  ${EndIf}
FunctionEnd

Function .onInstSuccess
  ; An update: PrerollsMaxUpdater.ps1 starts Prerolls Max the way it was running
  ${If} $UPDATE_MODE == "1"
    Return
  ${EndIf}

  ; Start the tray as the signed-in user (not elevated), through a scheduled
  ; task that runs once, so it can reach mapped drives and the user's network
  ; credentials.
  nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -Command "\
     $$action = New-ScheduledTaskAction -Execute \"$INSTDIR\PrerollsMaxTray.exe\"; \
     $$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(2); \
     $$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; \
     $$principal = New-ScheduledTaskPrincipal -GroupId \"S-1-5-32-545\" -RunLevel Limited; \
     Register-ScheduledTask -TaskName \"PrerollsMaxLaunch\" -Action $$action -Trigger $$trigger -Settings $$settings -Principal $$principal -Force | Out-Null; \
     Start-Sleep -Seconds 3; \
     Unregister-ScheduledTask -TaskName \"PrerollsMaxLaunch\" -Confirm:$$false -ErrorAction SilentlyContinue"'
  Pop $0
  Pop $1

  ${If} $NEXROLL_HANDLED == "1"
    MessageBox MB_ICONINFORMATION|MB_OK "Installation complete!$\r$\n$\r$\nPrerolls Max is running at http://localhost:$PORT$\r$\n$\r$\nNeXroll has been stopped and switched off; its files are still there. To bring your NeXroll library across, open Settings, Moving from NeXroll." /SD IDOK
  ${ElseIf} $KEEP_NEXROLL == "1"
    MessageBox MB_ICONINFORMATION|MB_OK "Installation complete!$\r$\n$\r$\nPrerolls Max is running at http://localhost:$PORT, next to NeXroll. Let only one of them manage intros on each media server." /SD IDOK
  ${Else}
    MessageBox MB_ICONINFORMATION|MB_OK "Installation complete!$\r$\n$\r$\nPrerolls Max is running in the system tray.$\r$\nOpen http://localhost:$PORT in your browser." /SD IDOK
  ${EndIf}
FunctionEnd
