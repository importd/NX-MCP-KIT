param(
    [Parameter(Mandatory = $true)][string]$RuntimeHome,
    [string]$PythonExe = "python.exe",
    [int]$IntervalMinutes = 10,
    [switch]$Remove,
    [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"
$taskName = "NXAgentKit-AutoIngest"
$io = Join-Path $RuntimeHome "io"
$library = Join-Path $RuntimeHome "library"
$contract = Join-Path $RuntimeHome "contract"
$parts = Join-Path $io "auto_parts"

$arguments = '-m nxkit.auto_ingest --io "{0}" --library "{1}" --contract "{2}" --parts "{3}"' -f $io, $library, $contract, $parts

if ($Remove) {
    $command = 'schtasks /Delete /TN "{0}" /F' -f $taskName
}
else {
    $command = 'schtasks /Create /TN "{0}" /SC MINUTE /MO {1} /TR "\"{2}\" {3}" /F' -f $taskName, $IntervalMinutes, $PythonExe, $arguments
}

if ($PrintOnly) {
    Write-Output $command
    exit 0
}

Invoke-Expression $command | Out-String | Write-Output
Write-Output ("TASK: " + $taskName + " (every " + $IntervalMinutes + " min)")
exit 0
