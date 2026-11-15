param([string]$Iscc = '', [switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements-dev.txt first; see README.md.'
}
Push-Location $projectRoot
try {
    & $pythonPath packaging/create_assets.py
    if ($LASTEXITCODE) { throw 'Icon/version generation failed.' }
    & $pythonPath -m PyInstaller --noconfirm --clean packaging/checker.spec
    if ($LASTEXITCODE) { throw 'PyInstaller build failed.' }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination (Join-Path $projectRoot 'dist/ALResultsCollector/LICENSE.txt') -Force
    $appVersion = (& $pythonPath -c 'from al_results import __version__; print(__version__)').Trim()
    & $pythonPath packaging/create_portable.py --folder (Join-Path $projectRoot 'dist/ALResultsCollector') --output (Join-Path $projectRoot "dist/ALResultsCollector-$appVersion-portable.zip")
    if ($LASTEXITCODE) { throw 'Portable ZIP creation or verification failed.' }
    if (-not $SkipInstaller) {
        if (-not $Iscc) {
            $candidates = @(
                (Join-Path $projectRoot 'build/tools/InnoSetup/ISCC.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs/Inno Setup 6/ISCC.exe'),
                'C:/Program Files (x86)/Inno Setup 6/ISCC.exe',
                'C:/Program Files/Inno Setup 7/ISCC.exe'
            )
            $Iscc = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        }
        if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)) {
            throw 'Install Inno Setup or pass -Iscc with the path to ISCC.exe.'
        }
        & $Iscc "/DAppVersion=$appVersion" packaging/installer.iss
        if ($LASTEXITCODE) { throw 'Installer build failed.' }
    }
    Write-Output "Built version $appVersion in dist."
} finally {
    Pop-Location
}
