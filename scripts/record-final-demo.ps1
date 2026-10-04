<#
One continuous live OBS take. See docs/final-recording-automation.md.
No installations, uploads, credentials or media files are written to the repository.
#>
[CmdletBinding()]
param(
    [string]$NarrationPath,
    [string]$ExpectedCommit,
    [string]$ObsExe,
    [int]$ObsPort = 4455,
    [string]$Ffprobe = 'ffprobe',
    [string]$Microphone,
    [switch]$DryRun,
    [switch]$PreflightOnly,
    [switch]$AllowReviewBranch
)

$ErrorActionPreference = 'Stop'
$recordingRoot = Split-Path -Parent $PSScriptRoot
$recordingPython = Join-Path $recordingRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $recordingPython -PathType Leaf)) {
    throw 'Missing .venv. Run python scripts/run_demo.py --no-open before recording.'
}
$recordingArgs = @('-m', 'mwalimulens.final_recording', '--obs-port', "$ObsPort", '--ffprobe', $Ffprobe)
if ($NarrationPath) { $recordingArgs += @('--narration', $NarrationPath) }
if ($ExpectedCommit) { $recordingArgs += @('--expected-commit', $ExpectedCommit) }
if ($ObsExe) { $recordingArgs += @('--obs-exe', $ObsExe) }
if ($Microphone) { $recordingArgs += @('--microphone', $Microphone) }
if ($DryRun) { $recordingArgs += '--dry-run' }
if ($PreflightOnly) { $recordingArgs += '--preflight-only' }
if ($AllowReviewBranch) { $recordingArgs += '--allow-review-branch' }

Push-Location -LiteralPath $recordingRoot
try {
    & $recordingPython @recordingArgs
    $recordingExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $recordingExitCode
