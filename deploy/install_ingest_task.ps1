param(
    [Parameter(Mandatory = $true)][string]$RuntimeHome,
    [string]$IoDir = "",
    [string]$PythonExe = "python.exe",
    [int]$IntervalMinutes = 10,
    [switch]$Remove,
    [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"
$taskName = "NXAgentKit-AutoIngest"
if (-not $IoDir) { $IoDir = Join-Path $RuntimeHome "io" }
$library = Join-Path $RuntimeHome "library"
$contract = Join-Path $RuntimeHome "contract"
$parts = Join-Path $IoDir "auto_parts"
$runnerCmd = Join-Path $RuntimeHome "run_auto_ingest.cmd"

if (-not $PrintOnly -and -not $Remove) {
    $lines = @(
        "@echo off",
        ('set PYTHONPATH=' + (Join-Path $RuntimeHome "runtime")),
        ('"{0}" -m nxkit.auto_ingest --io "{1}" --library "{2}" --contract "{3}" --parts "{4}"' -f $PythonExe, $IoDir, $library, $contract, $parts)
    )
    Set-Content -LiteralPath $runnerCmd -Value $lines -Encoding ASCII
    Write-Output ("RUNNER: " + $runnerCmd)
}

if ($Remove) {
    $command = 'schtasks /Delete /TN "{0}" /F' -f $taskName
}
else {
    $command = 'schtasks /Create /TN "{0}" /SC MINUTE /MO {1} /TR "\"{2}\"" /F' -f $taskName, $IntervalMinutes, $runnerCmd
}

if ($PrintOnly) {
    Write-Output $command
    exit 0
}

Invoke-Expression $command | Out-String | Write-Output
Write-Output ("TASK: " + $taskName + " every " + $IntervalMinutes + " min -> " + $runnerCmd)
exit 0
