<#
Installs the built installer silently, checks Prerolls Max answers, then
uninstalls. Run on a throwaway Windows machine (the CI runner): it installs a
Windows service.

  powershell -ExecutionPolicy Bypass -File packaging\windows\smoke-test.ps1 [-Installer path]

1. /S                       Prerolls Max on port 9393 (the default, as when it replaces NeXroll)
2. /S /KEEPNEXROLL /PORT=9494   reinstall next to NeXroll on 9494 (startup.json); the
                                service, PrerollsMax.exe and the tray move to it; 9393 is then free
3. uninstall /S             the service, the files and the registry key are gone
#>
[CmdletBinding()]
param(
    [string]$Installer = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Installer) {
    $Installer = (Get-ChildItem (Join-Path $PSScriptRoot 'dist') -Filter 'PrerollsMax_Installer_v*.exe' | Select-Object -First 1).FullName
}
if (-not $Installer -or -not (Test-Path $Installer)) { throw 'No installer to test' }
$installDir = Join-Path ${env:ProgramFiles} 'Prerolls Max'

function Install([string[]]$Arguments) {
    Write-Host "==> $Installer $($Arguments -join ' ')"
    $p = Start-Process -FilePath $Installer -ArgumentList $Arguments -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "The installer exited with $($p.ExitCode)" }
}

function Wait-Health([int]$Port, [int]$Seconds = 180) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { Write-Host "GET /health on $Port -> 200 $($r.Content)"; return }
        } catch { }
        Start-Sleep -Seconds 3
    }
    Get-Service PrerollsMaxService -ErrorAction SilentlyContinue | Format-List | Out-String | Write-Host
    Get-ChildItem "$env:ProgramData\Prerolls Max\logs" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "--- $($_.Name)"; Get-Content $_.FullName -Tail 60 | Write-Host
    }
    throw "Prerolls Max did not answer on port $Port within $Seconds s"
}

function Test-Listening([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

# 1. Default install
Install @('/S')
foreach ($exe in 'PrerollsMax.exe', 'PrerollsMaxService.exe', 'PrerollsMaxTray.exe', 'PrerollsMaxUpdater.ps1', 'uninstall.exe') {
    if (-not (Test-Path (Join-Path $installDir $exe))) { throw "$exe was not installed" }
}
$svc = Get-Service PrerollsMaxService -ErrorAction Stop
Write-Host "Service: $($svc.Status) $($svc.StartType)"
Wait-Health 9393
# What a fresh install shows before the admin account exists: the web page
# (the "Welcome" page), the setup status, and /servers sent to its #/ page.
$page = Invoke-WebRequest -Uri 'http://127.0.0.1:9393/' -UseBasicParsing -TimeoutSec 15
if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<div id="root"') { throw "The web page did not load ($($page.StatusCode))" }
$status = Invoke-RestMethod -Uri 'http://127.0.0.1:9393/auth/status' -TimeoutSec 15
if (-not $status.setup_required) { throw "A fresh install should ask for the admin account: $($status | ConvertTo-Json -Compress)" }
$jump = Invoke-WebRequest -Uri 'http://127.0.0.1:9393/servers' -Headers @{ Accept = 'text/html' } -UseBasicParsing `
    -MaximumRedirection 0 -SkipHttpErrorCheck -ErrorAction SilentlyContinue -TimeoutSec 15
if ($jump.StatusCode -ne 307 -or "$($jump.Headers.Location)" -ne '/#/servers') { throw "/servers should redirect to /#/servers (got $($jump.StatusCode) $($jump.Headers.Location))" }
Write-Host 'Web page 200, setup required, /servers -> /#/servers'
$info = Get-Content (Join-Path $installDir 'build_info.json') -Raw | ConvertFrom-Json
Write-Host "build_info.json: repository=$($info.repository) version=$($info.version)"
$expected = if ($env:PMAX_BUILD_REPOSITORY) { $env:PMAX_BUILD_REPOSITORY } else { $env:GITHUB_REPOSITORY }
if ($expected -eq 'none') { $expected = '' }
if ($null -ne $expected -and "$($info.repository)" -ne "$expected") { throw "build_info.json names '$($info.repository)', expected '$expected'" }

# 2. Next to NeXroll, on another port
Install @('/S', '/KEEPNEXROLL', '/PORT=9494')
# The one port setting: startup.json in the data folder (Settings writes it too)
$startup = Join-Path $env:ProgramData 'Prerolls Max\startup.json'
$port = (Get-Content -Raw -LiteralPath $startup | ConvertFrom-Json).port
if ("$port" -ne '9494') { throw "startup.json has port '$port', expected 9494" }
$url = Get-Content (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Prerolls Max\Prerolls Max.url') -ErrorAction SilentlyContinue
if (-not $url) { $url = Get-Content (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Prerolls Max\Prerolls Max.url') }
if (-not ($url -match 'URL=http://localhost:9494/')) { throw "The Start menu shortcut doesn't open port 9494: $url" }
Wait-Health 9494
# The tray, started again by the installer for the signed-in user, follows the port too.
$trayLog = Join-Path $env:ProgramData 'Prerolls Max\logs\tray.log'
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline -and -not (Select-String -LiteralPath $trayLog -Pattern 'starting \(port 9494[,)]' -Quiet -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 3 }
if (-not (Select-String -LiteralPath $trayLog -Pattern 'starting \(port 9494[,)]' -Quiet -ErrorAction SilentlyContinue)) {
    Get-Content $trayLog -Tail 20 -ErrorAction SilentlyContinue | Write-Host
    throw 'The tray did not start on port 9494'
}
Write-Host 'Tray started on port 9494'
if (Test-Listening 9393) { throw 'Something still listens on 9393 after moving to 9494' }

# 3. Uninstall
Write-Host '==> uninstall /S'
$p = Start-Process -FilePath (Join-Path $installDir 'uninstall.exe') -ArgumentList '/S', "_?=$installDir" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "The uninstaller exited with $($p.ExitCode)" }
Start-Sleep -Seconds 5
if (Get-Service PrerollsMaxService -ErrorAction SilentlyContinue) { throw 'The service is still installed' }
if (Test-Path (Join-Path $installDir 'PrerollsMax.exe')) { throw 'PrerollsMax.exe is still there' }
if (Test-Listening 9494) { throw 'Prerolls Max still listens on 9494' }
Write-Host 'Smoke test passed'
