param(
    [string]$RuntimeHome = (Split-Path -Parent $PSScriptRoot),
    [string]$IoDir,
    [string]$PythonExe = "python.exe",
    [switch]$Clean,
    [int]$TimeoutSec = 120
)
$ErrorActionPreference = "Stop"
if (-not $IoDir) { $IoDir = Join-Path $RuntimeHome "io" }
$env:PYTHONPATH = Join-Path $RuntimeHome "runtime"
$env:PYTHONIOENCODING = "utf-8"
$pyArgs = @(
    "-m", "nxkit.smoke",
    "--io", $IoDir,
    "--contract", (Join-Path $RuntimeHome "contract"),
    "--library", (Join-Path $RuntimeHome "library"),
    "--timeout-s", "$TimeoutSec"
)
if ($Clean) { $pyArgs += "--clean" }
& $PythonExe @pyArgs
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 2 }
exit $code
