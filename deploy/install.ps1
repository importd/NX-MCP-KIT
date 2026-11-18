param(
    [Parameter(Mandatory = $true)][string]$RuntimeHome,
    [string]$StartupDir,
    [string]$CustomDirsFile,
    [string]$PythonExe = "python.exe",
    [switch]$NoNx
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $RuntimeHome)) {
    New-Item -ItemType Directory -Force $RuntimeHome | Out-Null
}

foreach ($folder in @("bridge", "runtime", "contract", "skills")) {
    $source = Join-Path $repo $folder
    if (Test-Path $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $RuntimeHome $folder) -Recurse -Force
    }
}

$serverPath = Join-Path $RuntimeHome "runtime\nxkit\server.py"
$config = @{
    mcpServers = @{
        nx = @{
            command = $PythonExe
            args    = @($serverPath)
            env     = @{
                NXKIT_IO_DIR   = (Join-Path $RuntimeHome "io")
                NXKIT_LIBRARY  = (Join-Path $RuntimeHome "library")
                NXKIT_CONTRACT_DIR = (Join-Path $RuntimeHome "contract")
                NXKIT_KB_DB    = (Join-Path $RuntimeHome "kb\nxopen.db")
            }
        }
    }
}
$json = $config | ConvertTo-Json -Depth 8
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $RuntimeHome "mcp_config.json"), $json, $utf8)

$bridgeHome = Join-Path $RuntimeHome "bridge"
if ($StartupDir) {
    if (-not (Test-Path $StartupDir)) {
        New-Item -ItemType Directory -Force $StartupDir | Out-Null
    }
    Copy-Item -LiteralPath (Join-Path $bridgeHome "startup\nx_agent_kit.py") -Destination $StartupDir -Force
    Write-Output ("STARTUP: " + (Join-Path $StartupDir "nx_agent_kit.py"))
}

if ($CustomDirsFile) {
    $line = $bridgeHome
    $existing = ""
    if (Test-Path $CustomDirsFile) {
        $existing = Get-Content -LiteralPath $CustomDirsFile -Raw -Encoding UTF8
    }
    if ($existing -notmatch [regex]::Escape($line)) {
        if ($existing -and -not $existing.EndsWith("`n")) {
            Add-Content -LiteralPath $CustomDirsFile -Value "" -Encoding UTF8
        }
        Add-Content -LiteralPath $CustomDirsFile -Value $line -Encoding UTF8
        Write-Output ("CUSTOMDIRS: appended " + $line)
    }
    else {
        Write-Output "CUSTOMDIRS: already registered"
    }
}

if (-not $NoNx) {
    Write-Output "NOTE: 重启 NX 后启动目录才会加载新桥；用 nx_status 确认 connected=true"
}
Write-Output "RESULT: OK"
exit 0
