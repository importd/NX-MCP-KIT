param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

function Get-FileHashHex([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

$sourceFiles = Get-ChildItem -LiteralPath $Source -Recurse -File
$drift = @()
foreach ($file in $sourceFiles) {
    $relative = $file.FullName.Substring($Source.Length).TrimStart("\")
    $targetPath = Join-Path $Target $relative
    if (-not (Test-Path $targetPath)) {
        $drift += "missing: " + $relative
    }
    elseif ((Get-FileHashHex $file.FullName) -ne (Get-FileHashHex $targetPath)) {
        $drift += "diff: " + $relative
    }
}

if ($Check) {
    if ($drift.Count -gt 0) {
        foreach ($item in $drift) { Write-Output ("DRIFT: " + $item) }
        exit 1
    }
    Write-Output "SYNC: clean"
    exit 0
}

foreach ($file in $sourceFiles) {
    $relative = $file.FullName.Substring($Source.Length).TrimStart("\")
    $targetPath = Join-Path $Target $relative
    $parent = Split-Path -Parent $targetPath
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    Copy-Item -LiteralPath $file.FullName -Destination $targetPath -Force
}
Write-Output "SYNC: copied"
exit 0
