param(
    [string]$OutputDir = "resources\libmpv"
)

$ErrorActionPreference = "Stop"

$tempDir = Join-Path $env:TEMP "chordcut_libmpv"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
}

# --- Find an extractor that can handle .7z ---

$extractor = $null
$extractorName = $null

# 1) 7-Zip
foreach ($path in @(
    "$env:ProgramFiles\7-Zip\7z.exe",
    "${env:ProgramFiles(x86)}\7-Zip\7z.exe"
)) {
    if (Test-Path $path) {
        $extractor = $path
        $extractorName = "7-Zip"
        break
    }
}
if (-not $extractor) {
    $inPath = Get-Command "7z" -ErrorAction SilentlyContinue
    if ($inPath) {
        $extractor = $inPath.Source
        $extractorName = "7-Zip"
    }
}

# 2) WinRAR
if (-not $extractor) {
    foreach ($path in @(
        "$env:ProgramFiles\WinRAR\WinRAR.exe",
        "${env:ProgramFiles(x86)}\WinRAR\WinRAR.exe"
    )) {
        if (Test-Path $path) {
            $extractor = $path
            $extractorName = "WinRAR"
            break
        }
    }
    if (-not $extractor) {
        $inPath = Get-Command "WinRAR" -ErrorAction SilentlyContinue
        if ($inPath) {
            $extractor = $inPath.Source
            $extractorName = "WinRAR"
        }
    }
}

# 3) Fallback: download portable 7zr.exe from 7-zip.org
if (-not $extractor) {
    Write-Host "No 7-Zip or WinRAR found. Downloading portable 7zr.exe..."
    $7zrPath = Join-Path $tempDir "7zr.exe"
    try {
        Invoke-WebRequest -Uri "https://7-zip.org/a/7zr.exe" -OutFile $7zrPath
    } catch {
        Write-Host "ERROR: Failed to download 7zr.exe from 7-zip.org" -ForegroundColor Red
        Write-Host "Please install 7-Zip (https://7-zip.org/) or WinRAR and try again."
        exit 1
    }
    if (Test-Path $7zrPath) {
        $extractor = $7zrPath
        $extractorName = "7zr (portable)"
    } else {
        Write-Host "ERROR: Failed to download 7zr.exe" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Using extractor: $extractorName ($extractor)"

# --- Download libmpv ---

Write-Host "Fetching latest release info from GitHub..."
$headers = @{ "User-Agent" = "ChordCut-Build-Script" }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest" -Headers $headers

# Find the standard x86_64 dev package (not v3)
$asset = $release.assets | Where-Object { $_.name -match "^mpv-dev-x86_64-\d" } | Select-Object -First 1

if (-not $asset) {
    Write-Host "ERROR: Could not find mpv-dev-x86_64 asset in the latest release." -ForegroundColor Red
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

$downloadUrl = $asset.browser_download_url
$fileName = $asset.name
$sizeMB = [math]::Round($asset.size / 1MB, 1)

Write-Host "Found: $fileName ($sizeMB MB)"
Write-Host "Downloading..."

$tempFile = Join-Path $tempDir $fileName
Invoke-WebRequest -Uri $downloadUrl -OutFile $tempFile

# --- Extract the DLL ---

Write-Host "Extracting libmpv-2.dll..."

$extractDir = Join-Path $tempDir "extracted"

if ($extractorName -eq "WinRAR") {
    # WinRAR: e = extract without paths, -y = assume yes
    & $extractor e -y "$tempFile" "libmpv-2.dll" "$extractDir\" 2>&1 | Out-Null
} else {
    # 7-Zip / 7zr: e = extract without paths, -y = assume yes
    & $extractor e "$tempFile" -o"$extractDir" "libmpv-2.dll" -y 2>&1 | Out-Null
}

$dllPath = Join-Path $extractDir "libmpv-2.dll"

if (-not (Test-Path $dllPath)) {
    # Fallback: try mpv-2.dll
    if ($extractorName -eq "WinRAR") {
        & $extractor e -y "$tempFile" "mpv-2.dll" "$extractDir\" 2>&1 | Out-Null
    } else {
        & $extractor e "$tempFile" -o"$extractDir" "mpv-2.dll" -y 2>&1 | Out-Null
    }
    $dllPath = Join-Path $extractDir "mpv-2.dll"
}

if (-not (Test-Path $dllPath)) {
    Write-Host "ERROR: Could not find libmpv DLL in the archive." -ForegroundColor Red
    Write-Host "Archive contents:"
    if ($extractorName -eq "WinRAR") {
        & $extractor l "$tempFile"
    } else {
        & $extractor l "$tempFile"
    }
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

# --- Install the DLL ---

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$dllName = Split-Path $dllPath -Leaf
Copy-Item $dllPath -Destination $OutputDir -Force

# Clean up
Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Successfully installed $dllName to $OutputDir" -ForegroundColor Green
