$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Join-Path $env:USERPROFILE 'Blaze'
$runtime = Join-Path $root '.runtime'
$bin = Join-Path $runtime 'bin'
$staging = Join-Path $runtime ('setup-' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $PSScriptRoot 'Blaze-Universal-4.1.21.py'
$uv = Join-Path $bin 'uv.exe'
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$lock = $null
function Run-Checked([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $exe" }
}
function Publish-File([string]$candidate, [string]$destination) {
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        [IO.File]::Replace($candidate, $destination, $null)
    } else {
        [IO.File]::Move($candidate, $destination)
    }
}
try {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Extract the complete ZIP before running Install-Blaze.bat.' }
    $arch = $env:PROCESSOR_ARCHITEW6432
    if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
    switch ($arch.ToUpperInvariant()) {
        'AMD64' { $target = 'x86_64-pc-windows-msvc' }
        'ARM64' { throw 'This package targets x64 Windows. A native ARM64 FFmpeg bundle is not included.' }
        default { throw 'This installer supports 64-bit x64 Windows 10/11.' }
    }
    New-Item -ItemType Directory -Force -Path $runtime, $bin, $staging | Out-Null
    $lock = [IO.File]::Open((Join-Path $runtime 'setup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
    $env:UV_CACHE_DIR = Join-Path $runtime 'cache'
    $env:UV_PYTHON_BIN_DIR = $bin
    $env:UV_TOOL_DIR = Join-Path $runtime 'tools'
    $env:UV_TOOL_BIN_DIR = $bin
    $env:UV_NO_CONFIG = '1'
    $env:UV_PYTHON_INSTALL_BIN = '0'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    $env:TEMP = Join-Path $runtime 'tmp'
    $env:TMP = $env:TEMP
    $env:PYTHONNOUSERSITE = '1'
    Remove-Item Env:PYTHONPATH, Env:PYTHONHOME -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
    Write-Host "`nBLAZE PRIVATE INSTALLER`nDestination: $root`n" -ForegroundColor Cyan
    Write-Host '[1/5] Downloading the private runtime manager...'
    # Pin the tool release; verify its archive against the published SHA-256.
    $version = '0.12.19'
    $asset = "uv-$target.zip"
    $base = "https://github.com/astral-sh/uv/releases/download/$version"
    $zip = Join-Path $staging $asset
    $checksum = Join-Path $staging 'checksum.txt'
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $zip -TimeoutSec 180
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset.sha256" -OutFile $checksum -TimeoutSec 60
    $match = [regex]::Match((Get-Content -LiteralPath $checksum -Raw), '(?i)\b[a-f0-9]{64}\b')
    if (-not $match.Success) { throw 'Invalid uv checksum file.' }
    $hasher = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($zip)
    try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $hasher.Dispose() }
    if ($actualHash -ne $match.Value) { throw 'uv checksum mismatch. Nothing from the download was executed.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, (Join-Path $staging 'uv'))
    $executables = @(Get-ChildItem -LiteralPath (Join-Path $staging 'uv') -Recurse -Filter 'uv.exe' -File)
    if ($executables.Count -ne 1) { throw 'Unexpected uv archive contents.' }
    Publish-File $executables[0].FullName $uv
    Run-Checked $uv @('--version')
    Write-Host '[2/5] Installing private Python 3.13...'
    Run-Checked $uv @('python', 'install', '3.13', '--no-bin', '--no-registry', '--no-config')
    Write-Host '[3/5] Preparing the private Python environment...'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Run-Checked $uv @('venv', '--python', '3.13', '--managed-python', '--seed', '--no-config', (Join-Path $runtime 'venv'))
    }
    Run-Checked $python @('-c', 'import sys; assert sys.version_info >= (3,10); print(sys.version)')
    Write-Host '[4/5] Installing Blaze dependencies...'
    Run-Checked $uv @('pip', 'install', '--python', $python, '--no-config', '--no-cache', 'yt-dlp', 'rich', 'mutagen', 'imageio-ffmpeg')
    $ffmpeg = & $python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $ffmpeg -PathType Leaf)) { throw 'Bundled FFmpeg was not found.' }
    $ffmpegCandidate = Join-Path $staging 'ffmpeg.exe'
    Copy-Item -LiteralPath $ffmpeg -Destination $ffmpegCandidate
    Run-Checked $ffmpegCandidate @('-version')
    Publish-File $ffmpegCandidate (Join-Path $bin 'ffmpeg.exe')
    Write-Host '[5/5] Installing Blaze and creating its launcher...'
    $app = Join-Path $root 'App'
    New-Item -ItemType Directory -Force -Path $app | Out-Null
    $candidate = Join-Path $staging 'blaze.py'
    Copy-Item -LiteralPath $source -Destination $candidate
    Run-Checked $python @('-m', 'py_compile', $candidate)
    Run-Checked $python @($candidate, '--help')
    Publish-File $candidate (Join-Path $app 'blaze.py')
    $launcher = @'
@echo off
setlocal
set "BLAZE_ROOT=%~dp0"
set "PATH=%BLAZE_ROOT%.runtime\bin;%BLAZE_ROOT%.runtime\venv\Scripts;%PATH%"
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH="
set "PYTHONHOME="
set "TEMP=%BLAZE_ROOT%.runtime\tmp"
set "TMP=%TEMP%"
"%BLAZE_ROOT%.runtime\venv\Scripts\python.exe" "%BLAZE_ROOT%App\blaze.py" %*
set "BLAZE_RESULT=%ERRORLEVEL%"
if not "%BLAZE_RESULT%"=="0" pause
exit /b %BLAZE_RESULT%
'@
    $launcherCandidate = Join-Path $staging 'Start-Blaze.bat'
    Set-Content -LiteralPath $launcherCandidate -Value $launcher -Encoding ASCII
    Publish-File $launcherCandidate (Join-Path $root 'Start-Blaze.bat')
    Write-Host "`nInstalled successfully. Run: $root\Start-Blaze.bat" -ForegroundColor Green
    Write-Host 'Python, packages, tools, cache and installer temporary files stay in Blaze.'
    Write-Host 'Existing downloads and settings are preserved. No admin rights or global PATH changes.'
} catch {
    Write-Host "`nINSTALLATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue }
}

