<#!
.SYNOPSIS
  Windows 一键打包并上传至服务器 /tmp，用于后续服务器端一键部署。

.DESCRIPTION
  - 打包当前项目为 project_YYYYMMDDHHMM.tgz（默认）
  - 排除 data、logs、venv、.git、decisions、__pycache__、*.pyc
  - 通过 scp 上传到远程 /tmp 目录

.PARAMETER Server
  远程服务器，形如 ubuntu@106.52.47.82

.PARAMETER RemoteTmp
  远程临时目录，默认 /tmp

.EXAMPLE
  pwsh -File scripts/windows_pack_upload.ps1 -Server ubuntu@106.52.47.82 -RemoteTmp /tmp

#>
param(
  [string]$Server = "ubuntu@106.52.47.82",
  [string]$RemoteTmp = "/tmp"
)

$ErrorActionPreference = 'Stop'

function New-TarArchive {
  param(
    [string]$ProjectRoot,
    [string]$ArchivePath
  )
  Push-Location $ProjectRoot
  try {
    $tarCmd = @(
      'tar','-czf',$ArchivePath,
      "--exclude=./data",
      "--exclude=./logs",
      "--exclude=./venv",
      "--exclude=./.git",
      "--exclude=./decisions",
      "--exclude=*/__pycache__",
      "--exclude=*.pyc",
      '.'
    )
    Write-Host "[+] 运行: $($tarCmd -join ' ')"
    & $tarCmd | Out-Null
  } finally {
    Pop-Location
  }
}

# 计算路径
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ts = Get-Date -Format "yyyyMMddHHmm"
$ArchiveName = "project_$ts.tgz"
$ArchivePath = Join-Path $ProjectRoot $ArchiveName

Write-Host "[+] 项目根目录: $ProjectRoot"
Write-Host "[+] 输出归档:   $ArchivePath"

# 生成 tgz
if (Get-Command tar -ErrorAction SilentlyContinue) {
  New-TarArchive -ProjectRoot $ProjectRoot -ArchivePath $ArchivePath
} else {
  throw "未找到 tar 命令，建议在 Windows 安装 Windows Subsystem for Linux(WSL) 或 Git Bash 以使用 tar。"
}

# 校验文件
if (!(Test-Path $ArchivePath)) { throw "打包失败: $ArchivePath 未生成" }

# 上传
Write-Host "[+] 上传到 $Server:$RemoteTmp/"
$scpArgs = @('-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null',"$ArchivePath", "$Server`:$RemoteTmp/")
& scp $scpArgs

Write-Host "[✓] 完成上传: $ArchiveName -> $Server:$RemoteTmp/"
Write-Host "[→] 下一步在服务器执行: sudo bash /opt/ai-etf-trader/deploy/jan2_deploy.sh $RemoteTmp/$ArchiveName"

