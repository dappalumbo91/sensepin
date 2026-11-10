# Install the Sensepin desk for this user.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA "Sensepin"
$fold = Join-Path $dest "fold"
New-Item -ItemType Directory -Force -Path $fold | Out-Null
$foldSrc = Join-Path $root "fold"
foreach ($name in @("foldc.py", "sensepin.py", "lsp.py", "runtime.c", "runtime.h", "SPEC.md")) {
    Copy-Item -Force (Join-Path $foldSrc $name) (Join-Path $fold $name)
}
python -c "import sys; sys.path.insert(0, r'$fold'); import foldc; foldc.shared_import()"
$cmd = Join-Path $dest "sensepin.cmd"
@(
    "@echo off",
    "python `"%~dp0fold\sensepin.py`" %*"
) | Set-Content -Encoding ascii $cmd
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) {
    $userPath = ""
}
$parts = $userPath.Split(";") | Where-Object { $_ -ne "" }
if ($parts -notcontains $dest) {
    $joined = (@($parts) + $dest) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $joined, "User")
}
Write-Output $dest
