[CmdletBinding()]
param(
    [ValidateSet("validate", "build", "render", "board", "all")]
    [string]$Action = "validate",

    [string]$Spec = "examples/drc-search-video/video_spec.yaml",

    [switch]$Force,

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
$Arguments = @("scripts/markdown_to_video.py", "--spec", $Spec)

if ($Force) {
    $Arguments += "--force"
}
if ($Json) {
    $Arguments += "--json"
}
$Arguments += $Action

Write-Host "EveDirector L2 — Markdown to Video" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Python:     $PythonExe"
Write-Host "Spec:       $Spec"
Write-Host "Action:     $Action"
Write-Host ""

if ([System.IO.Path]::GetFileName($PythonExe) -ieq "py.exe") {
    & $PythonExe -3 @Arguments
} else {
    & $PythonExe @Arguments
}

if ($LASTEXITCODE -ne 0) {
    throw "L2 action failed with exit code $LASTEXITCODE."
}
