param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath("Desktop")) "PLUS_Agent_Delivery")
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$skillSource = Join-Path $projectRoot "agent_skills\plus-model-tools"
$backendSource = Join-Path $projectRoot "plus-backend"
$assetsSource = Join-Path $projectRoot "delivery_assets"

if (Test-Path -LiteralPath $Destination) {
    throw "目标目录已存在，为防止覆盖已停止：$Destination"
}
if ($Destination -match "[^\x00-\x7F]") {
    throw "目标目录必须只包含 ASCII 字符：$Destination"
}

New-Item -ItemType Directory -Path $Destination | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Destination ".agents\skills") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Destination "plus-runtime") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Destination "setup") -Force | Out-Null

Copy-Item -LiteralPath $skillSource -Destination (Join-Path $Destination ".agents\skills\plus-model-tools") -Recurse
Copy-Item -LiteralPath $backendSource -Destination (Join-Path $Destination "plus-runtime\plus-backend") -Recurse
Copy-Item -LiteralPath (Join-Path $assetsSource "environment.yml") -Destination (Join-Path $Destination "setup\environment.yml")
Copy-Item -LiteralPath (Join-Path $assetsSource "install_windows.ps1") -Destination (Join-Path $Destination "setup\install_windows.ps1")
Copy-Item -LiteralPath (Join-Path $assetsSource "doctor.ps1") -Destination (Join-Path $Destination "setup\doctor.ps1")
Copy-Item -LiteralPath (Join-Path $assetsSource "使用说明.md") -Destination (Join-Path $Destination "使用说明.md")

Write-Host "交付包已生成：$Destination"
