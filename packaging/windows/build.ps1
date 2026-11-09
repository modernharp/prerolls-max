<#
Builds the Prerolls Max Windows installer:
  packaging\windows\dist\PrerollsMax_Installer_v<version>.exe  (+ .sha256)

Needs Python 3.12 with ..\..\requirements.txt and requirements-build.txt
installed, Node.js 22 (for the web interface) and NSIS 3 (makensis). The
Jellyfin/Emby plugins are bundled when plugins\out holds them (plugins/build.sh,
or the plugins workflow's artifact); without them the app still builds.

  powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
  ... -SkipFrontend   reuse frontend\dist

build_info.json (which GitHub repository publishes updates) comes from
PMAX_BUILD_REPOSITORY, else GITHUB_REPOSITORY (GitHub Actions); a local build has update
checks off. The version comes from app\version.py.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = (Resolve-Path (Join-Path $here '..\..')).Path

function Invoke-Step([string]$Name, [scriptblock]$Block) {
    Write-Host "==> $Name"
    & $Block
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)" }
}

Invoke-Step 'Version resource and icons' { python (Join-Path $here 'prepare.py') }
Invoke-Step 'Build info' {
    python (Join-Path $root 'scripts\write_build_info.py') --out (Join-Path $here 'build\build_info.json')
}

if (-not $SkipFrontend) {
    Push-Location (Join-Path $root 'frontend')
    try {
        Invoke-Step 'npm ci' { npm ci --no-audit --no-fund }
        Invoke-Step 'Web interface' { npm run build }
    } finally { Pop-Location }
}
if (-not (Test-Path (Join-Path $root 'frontend\dist\index.html'))) { throw 'frontend\dist is missing: build the web interface first' }

$plugins = @(Get-ChildItem (Join-Path $root 'plugins\out') -Filter 'PrerollsMax.*' -ErrorAction SilentlyContinue)
Write-Host "Bundling $($plugins.Count) plugin file(s) from plugins\out"

Push-Location $here
try {
    Remove-Item -Recurse -Force (Join-Path $here 'dist') -ErrorAction SilentlyContinue
    Invoke-Step 'PyInstaller' {
        python -m PyInstaller --noconfirm --clean --distpath (Join-Path $here 'dist') --workpath (Join-Path $here 'build\pyinstaller') (Join-Path $here 'PrerollsMax.spec')
    }

    $makensis = (Get-Command makensis -ErrorAction SilentlyContinue).Source
    if (-not $makensis) {
        foreach ($p in @("${env:ProgramFiles(x86)}\NSIS\makensis.exe", "$env:ProgramFiles\NSIS\makensis.exe")) {
            if (Test-Path $p) { $makensis = $p; break }
        }
    }
    if (-not $makensis) { throw 'makensis not found: install NSIS 3 (choco install nsis)' }
    Invoke-Step 'Installer' { & $makensis /V3 /WX (Join-Path $here 'installer.nsi') }
} finally { Pop-Location }

$installer = Get-ChildItem (Join-Path $here 'dist') -Filter 'PrerollsMax_Installer_v*.exe' | Select-Object -First 1
if (-not $installer) { throw 'The installer was not built' }
$hash = (Get-FileHash -Algorithm SHA256 $installer.FullName).Hash.ToLowerInvariant()
Set-Content -Path "$($installer.FullName).sha256" -Value "$hash  $($installer.Name)" -Encoding ascii
Write-Host "Built $($installer.Name) ($([math]::Round($installer.Length / 1MB, 1)) MB) sha256 $hash"
