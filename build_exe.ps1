#requires -Version 5.1

param(
    [string]$Entry = "start.py",
    [string]$Name = "git-repo-manager"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-BootstrapPython {
    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Args = @() }
    }

    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = $py.Source; Args = @("-3") }
    }

    throw "python/py not found. Install Python 3.10+ and add it to PATH."
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
    $bootstrap = Get-BootstrapPython
    & $bootstrap.Exe @($bootstrap.Args) -m venv ".venv"
}

& $venvPython -m pip install --upgrade pip pyinstaller | Out-Host
& $venvPython -m PyInstaller --clean --noconsole --onefile --name $Name $Entry

Write-Host ""
Write-Host "Build done: $repoRoot/dist/$Name.exe"
