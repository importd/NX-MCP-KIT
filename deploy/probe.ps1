param(
    [string[]]$NxRoot,
    [string]$OutDir
)

$ErrorActionPreference = "Stop"
if (-not $OutDir) {
    $OutDir = Join-Path $PSScriptRoot "..\contract\matrix"
}
if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force $OutDir | Out-Null
}

function Get-NxCandidates {
    $found = @()
    if ($env:UGII_BASE_DIR) { $found += $env:UGII_BASE_DIR }
    foreach ($base in @("C:\Program Files\Siemens", "D:\Program Files\Siemens")) {
        if (Test-Path $base) {
            Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $found += $_.FullName
            }
        }
    }
    return $found
}

if (-not $NxRoot) {
    $NxRoot = @(Get-NxCandidates | Where-Object {
        $_ -and ((Test-Path (Join-Path $_ "NXBIN\ugraf.exe")) -or (Test-Path (Join-Path $_ "UGII\ugraf.exe")))
    })
}

foreach ($root in @($NxRoot)) {
    if (-not $root -or -not (Test-Path $root)) { continue }
    $root = (Resolve-Path -LiteralPath $root).Path
    $ugraf = Join-Path $root "NXBIN\ugraf.exe"
    if (-not (Test-Path $ugraf)) { $ugraf = Join-Path $root "UGII\ugraf.exe" }

    $hasXml = $false
    foreach ($candidate in @(
        (Join-Path $root "NXBIN\managed\NXOpen.xml"),
        (Join-Path $root "UGII\managed\NXOpen.xml")
    )) {
        if (Test-Path $candidate) { $hasXml = $true }
    }

    $pyVersion = $null
    $pyDlls = Get-ChildItem -LiteralPath (Join-Path $root "NXBIN") -Filter "python*.dll" -ErrorAction SilentlyContinue
    if ($pyDlls) {
        foreach ($dll in $pyDlls) {
            if ($dll.Name -match "python3(\d)(\d)") {
                $pyVersion = "3." + $Matches[1] + $Matches[2]
            }
            elseif ($dll.Name -match "python3(\d)") {
                $pyVersion = "3." + $Matches[1]
            }
        }
    }
    if (-not $pyVersion) {
        $old = Get-ChildItem -LiteralPath (Join-Path $root "UGII") -Filter "python*.dll" -ErrorAction SilentlyContinue
        if ($old) { $pyVersion = "3.3" }
    }

    $version = ""
    try {
        $version = (Get-Item -LiteralPath $ugraf).VersionInfo.FileVersion
    } catch {
        $version = ""
    }

    $name = (Split-Path $root -Leaf) -replace "[^A-Za-z0-9._-]", "_"
    $data = [ordered]@{
        nx            = (Split-Path $root -Leaf)
        root          = $root
        ugraf         = $ugraf
        version       = $version
        py            = $pyVersion
        xml           = $hasXml
        matrix_source = "probe"
    }
    $target = Join-Path $OutDir ($name + ".json")
    $json = $data | ConvertTo-Json -Depth 5
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($target, $json, $utf8)
    Write-Output ("MATRIX: " + $target)
}
exit 0
