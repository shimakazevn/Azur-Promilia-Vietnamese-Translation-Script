param(
    [ValidateSet('Menu','Apply','Restore','Verify')][string]$Action = 'Menu'
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false) } catch {}

$Root = Split-Path $PSScriptRoot -Parent
$PlanPath = Join-Path $PSScriptRoot 'android-deployment-vi.json'
if (-not (Test-Path -LiteralPath $PlanPath)) { throw "Khong tim thay $PlanPath" }
$Plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json

$Adb = $null
foreach ($cand in @('adb', "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe", 'C:\platform-tools\adb.exe')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $Adb = $cmd.Source; break }
}
if (-not $Adb) { throw "Khong tim thay adb.exe (hay cai Android Platform-Tools hoac dung app AzurPromilia-VI-Mobile.apk + Shizuku tren dien thoai)." }

$devLines = & $Adb devices | Where-Object { $_ -match '\tdevice$' }
if (-not $devLines) { throw "Chua thay dien thoai Android nao bat USB Debugging ket noi." }

$Pkg = $Plan.package_name
$Ver = $Plan.resource_version
$RemoteRes = "/sdcard/Android/data/$Pkg/files/.res"
$RemoteBak = "/sdcard/Android/data/$Pkg/files/.vi-android-backup-$Ver"
$PayloadDir = Join-Path $Root 'payload-vi\android_game'

if ($Action -eq 'Menu') {
    Write-Host "Azur Promilia Viet Hoa Android ($Ver) - ADB Tool" -ForegroundColor Cyan
    Write-Host "1 Cai dat Viet hoa (Apply)   2 Khoi phuc goc (Restore)   3 Kiem tra (Verify)   Khac Thoat"
    switch ((Read-Host 'Chon').Trim()) {
        '1' { $Action = 'Apply' }
        '2' { $Action = 'Restore' }
        '3' { $Action = 'Verify' }
        default { exit 0 }
    }
}

$manCheck = & $Adb shell "test -f '$RemoteRes/raw_base_package/ManifestFiles/0release_raw_base_package_$Ver.bytes' && echo OK || echo MISS"
if ($manCheck.Trim() -ne 'OK') {
    throw "Thiet bi chua cai game hoac chua tai xong tai nguyen phien ban $Ver ($RemoteRes)."
}

function Get-RemoteSha([string]$RemotePath) {
    $out = & $Adb shell "if [ -f '$RemotePath' ]; then sha256sum '$RemotePath'; else echo MISSING; fi"
    if ($out.Trim() -eq 'MISSING') { return 'MISSING' }
    return ($out.Trim() -split '\s+')[0].ToLowerInvariant()
}

if ($Action -eq 'Verify') {
    foreach ($f in $Plan.files) {
        $sha = Get-RemoteSha "$RemoteRes/$($f.relative_path)"
        if ($sha -eq $f.target_sha256) { Write-Host "[VIET HOA] $($f.relative_path)" -ForegroundColor Green }
        elseif ($sha -eq $f.source_sha256) { Write-Host "[BAN GOC]  $($f.relative_path)" -ForegroundColor Yellow }
        else { Write-Host "[KHAC/LOI] $($f.relative_path) ($sha)" -ForegroundColor Red }
    }
    exit 0
}

& $Adb shell "am force-stop $Pkg" | Out-Null

if ($Action -eq 'Apply') {
    foreach ($f in $Plan.files) {
        $local = Join-Path $PayloadDir ($f.relative_path -replace '/','\')
        if (-not (Test-Path -LiteralPath $local)) { throw "Thieu file payload: $local" }
        $lsha = (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($lsha -ne $f.target_sha256) { throw "Payload hong SHA256: $($f.relative_path)" }
    }
    & $Adb shell "mkdir -p '$RemoteBak'" | Out-Null
    foreach ($f in $Plan.files) {
        $rp = "$RemoteRes/$($f.relative_path)"
        $bp = "$RemoteBak/$($f.relative_path)"
        $cur = Get-RemoteSha $rp
        if ($cur -eq $f.source_sha256) {
            $bcur = Get-RemoteSha $bp
            if ($bcur -ne $f.source_sha256) {
                $bdir = ($bp -replace '/[^/]+$','')
                & $Adb shell "mkdir -p '$bdir' && cp -f '$rp' '$bp'" | Out-Null
                if ((Get-RemoteSha $bp) -ne $f.source_sha256) { throw "Backup that bai: $($f.relative_path)" }
            }
        } elseif ($cur -ne $f.target_sha256) {
            throw "File tren dien thoai khong khop goc/VI: $($f.relative_path)"
        }
        $local = Join-Path $PayloadDir ($f.relative_path -replace '/','\')
        & $Adb push "$local" "$rp" | Out-Host
        if ((Get-RemoteSha $rp) -ne $f.target_sha256) { throw "Push verify that bai: $($f.relative_path)" }
        Write-Host "[OK] $($f.relative_path)" -ForegroundColor Green
    }
    Write-Host "HOAN TAT! Da cai xong Viet hoa Android." -ForegroundColor Green
} elseif ($Action -eq 'Restore') {
    foreach ($f in $Plan.files) {
        $rp = "$RemoteRes/$($f.relative_path)"
        $bp = "$RemoteBak/$($f.relative_path)"
        if ((Get-RemoteSha $bp) -ne $f.source_sha256) { throw "Thieu hoac hong backup: $bp" }
        & $Adb shell "cp -f '$bp' '$rp'" | Out-Null
        if ((Get-RemoteSha $rp) -ne $f.source_sha256) { throw "Khoi phuc that bai: $($f.relative_path)" }
        Write-Host "[RESTORED] $($f.relative_path)" -ForegroundColor Yellow
    }
    Write-Host "Da khoi phuc ban goc JP cho Android." -ForegroundColor Green
}
