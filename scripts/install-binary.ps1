param(
    [string]$Repo = $(if ($env:SKILL_REPO_RELEASE_REPO) { $env:SKILL_REPO_RELEASE_REPO } else { "weijunjiang123/skill-repo" }),
    [string]$Version = $(if ($env:SKILL_REPO_VERSION) { $env:SKILL_REPO_VERSION } else { "latest" }),
    [string]$InstallDir = $(if ($env:SKILL_REPO_INSTALL_DIR) { $env:SKILL_REPO_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\skill-repo\bin" }),
    [string]$BinName = $(if ($env:SKILL_REPO_BIN_NAME) { $env:SKILL_REPO_BIN_NAME } else { "skill-repo.exe" })
)

$ErrorActionPreference = "Stop"

function Get-AssetName {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    switch ($arch) {
        "X64" { return "skill-repo-windows-x64.exe" }
        default { throw "暂不支持当前 Windows CPU 架构: $arch" }
    }
}

function Get-ReleaseApiUrl {
    if ($Version -eq "latest") {
        return "https://api.github.com/repos/$Repo/releases/latest"
    }
    return "https://api.github.com/repos/$Repo/releases/tags/$Version"
}

function Add-ToUserPath {
    param([string]$Directory)

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if ($userPath) {
        $entries = $userPath -split ";" | Where-Object { $_ }
    }

    if ($entries -contains $Directory) {
        return
    }

    $newPath = (($entries + $Directory) -join ";")
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$Directory"
    Write-Host "已把 $Directory 写入用户 PATH；新终端中可直接运行 skill-repo。"
}

$asset = Get-AssetName
$apiUrl = Get-ReleaseApiUrl
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

try {
    Write-Host "获取 release 信息: $Repo ($Version)"
    $release = Invoke-RestMethod -Uri $apiUrl
    $download = $release.assets | Where-Object { $_.name -eq $asset } | Select-Object -First 1
    if (-not $download) {
        throw "未找到适用于当前平台的 release 资产: $asset"
    }

    $target = Join-Path $InstallDir $BinName
    $tmpAsset = Join-Path $tempDir $asset

    Write-Host "下载: $asset"
    Invoke-WebRequest -Uri $download.browser_download_url -OutFile $tmpAsset
    Move-Item -Force $tmpAsset $target
    Add-ToUserPath -Directory $InstallDir

    Write-Host "安装完成: $target"
    & $target --version
}
finally {
    Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
}
