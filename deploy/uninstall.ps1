param(
    [Parameter(Mandatory = $true)][string]$RuntimeHome,
    [string]$StartupDir,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RuntimeHome)) {
    Write-Output "RESULT: nothing to remove"
    exit 0
}

if ($StartupDir -and (Test-Path (Join-Path $StartupDir "nx_agent_kit.py"))) {
    Remove-Item -LiteralPath (Join-Path $StartupDir "nx_agent_kit.py") -Force
    Write-Output ("STARTUP: removed from " + $StartupDir)
}

if (-not $Force) {
    Write-Output ("DRYRUN: would remove " + $RuntimeHome + " (pass -Force)")
    exit 0
}
Remove-Item -LiteralPath $RuntimeHome -Recurse -Force
Write-Output "RESULT: OK"
exit 0
