[CmdletBinding()]
param(
    [ValidateSet("doctor", "smoke", "demo", "board", "all")]
    [string]$Action = "doctor",

    [string]$Project = "evedirector-local-smoke",

    [string]$Demo = "code-to-screen",

    [switch]$Json
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Resolve-OpenMontagePython {
    $Candidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "venv\Scripts\python.exe")
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            return $Candidate
        }
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        return $Python.Source
    }

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        return $PyLauncher.Source
    }

    throw "Python 3.10+ was not found. Install Python, then run this script again."
}

$PythonExe = Resolve-OpenMontagePython
$Arguments = @("scripts/evedirector_local_first.py", "--project", $Project)

if ($Json) {
    $Arguments += "--json"
}

$Arguments += $Action

if ($Action -eq "demo" -or $Action -eq "all") {
    $Arguments += @("--name", $Demo)
}

Write-Host "EveDirector local-first" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Python:     $PythonExe"
Write-Host "Action:     $Action"
Write-Host ""

if ([System.IO.Path]::GetFileName($PythonExe) -ieq "py.exe") {
    & $PythonExe -3 @Arguments
} else {
    & $PythonExe @Arguments
}

if ($LASTEXITCODE -ne 0) {
    throw "Local-first action failed with exit code $LASTEXITCODE."
}
