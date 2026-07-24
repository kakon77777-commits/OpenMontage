param(
    [ValidateSet("propose", "status", "validate", "apply", "reject")]
    [string]$Action = "status",

    [ValidateSet("ollama", "openai-compatible", "fixture")]
    [string]$Provider = "ollama",

    [string]$Model = $env:EVEDIRECTOR_LOCAL_MODEL,
    [string]$Endpoint = $env:EVEDIRECTOR_LOCAL_ENDPOINT,
    [string]$Instruction = "Improve clarity and pacing without adding unsupported claims.",
    [string]$RunId = "latest",
    [string]$Reviewer = "",
    [string]$Reason = "",
    [string]$ResponseFile = "",
    [switch]$AllowRemote,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScriptPath = Join-Path $RepoRoot "scripts\evedirector_local_agent.py"

$Python = $null
foreach ($candidate in @(
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    (Join-Path $RepoRoot "venv\Scripts\python.exe"),
    "python"
)) {
    if ($candidate -eq "python") {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command) {
            $Python = $command.Source
            break
        }
    }
    elseif (Test-Path $candidate) {
        $Python = $candidate
        break
    }
}

if (-not $Python) {
    throw "Python was not found. Run the repository setup first."
}

$Arguments = @($ScriptPath)
if ($Json) {
    $Arguments += "--json"
}

switch ($Action) {
    "propose" {
        $Arguments += @(
            "propose",
            "--provider", $Provider,
            "--instruction", $Instruction
        )
        if ($Provider -ne "fixture") {
            if ([string]::IsNullOrWhiteSpace($Model)) {
                throw "-Model or EVEDIRECTOR_LOCAL_MODEL is required."
            }
            $Arguments += @("--model", $Model)
        }
        if (-not [string]::IsNullOrWhiteSpace($Endpoint)) {
            $Arguments += @("--endpoint", $Endpoint)
        }
        if ($Provider -eq "fixture") {
            if ([string]::IsNullOrWhiteSpace($ResponseFile)) {
                throw "-ResponseFile is required for fixture provider."
            }
            $Arguments += @("--response-file", $ResponseFile)
        }
        if ($AllowRemote) {
            $Arguments += "--allow-remote"
        }
    }
    "status" {
        $Arguments += @("status", "--run-id", $RunId)
    }
    "validate" {
        $Arguments += @("validate", "--run-id", $RunId)
    }
    "apply" {
        if ([string]::IsNullOrWhiteSpace($Reviewer)) {
            throw "-Reviewer is required for apply."
        }
        $Arguments += @(
            "apply",
            "--run-id", $RunId,
            "--approve",
            "--reviewer", $Reviewer
        )
    }
    "reject" {
        if ([string]::IsNullOrWhiteSpace($Reviewer)) {
            throw "-Reviewer is required for reject."
        }
        if ([string]::IsNullOrWhiteSpace($Reason)) {
            throw "-Reason is required for reject."
        }
        $Arguments += @(
            "reject",
            "--run-id", $RunId,
            "--reviewer", $Reviewer,
            "--reason", $Reason
        )
    }
}

Push-Location $RepoRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "EveDirector L3 command failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
