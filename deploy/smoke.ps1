param(
    [string]$RuntimeHome = (Split-Path -Parent $PSScriptRoot),
    [string]$IoDir,
    [string]$PythonExe,
    [switch]$Clean,
    [int]$TimeoutSec = 120
)
$ErrorActionPreference = "Stop"
if (-not $IoDir) { $IoDir = Join-Path $RuntimeHome "io" }
if (-not $PythonExe) {
    $venvPython = Join-Path $RuntimeHome ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { $PythonExe = $venvPython }
    else { $PythonExe = "python.exe" }
}
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
if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    Write-Output "RESULT: FAIL:PYTHON"
    Write-Output ("NEXT: python not found: " + $PythonExe)
    exit 2
}
$versionOutput = & $PythonExe -c "import sys; print('%d.%d' % sys.version_info[:2])"
$versionText = "$(@($versionOutput)[0])".Trim()
try { $version = [version]$versionText } catch { $version = $null }
if ($LASTEXITCODE -ne 0 -or -not $version) {
    Write-Output "RESULT: FAIL:PYTHON"
    Write-Output ("NEXT: cannot run " + $PythonExe)
    exit 2
}
if ($version -lt [version]"3.12") {
    Write-Output "RESULT: FAIL:PYTHON_VERSION"
    Write-Output ("NEXT: need Python >= 3.12, got " + $versionText + " at " + $PythonExe + "; pass -PythonExe <path>")
    exit 2
}
try {
    & $PythonExe @pyArgs
}
catch {
    Write-Output "RESULT: FAIL:INTERNAL"
    Write-Output ("NEXT: " + $_.Exception.Message)
    exit 2
}
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 2 }
exit $code
