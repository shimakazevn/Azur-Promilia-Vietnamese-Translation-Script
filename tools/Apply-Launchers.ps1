[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Apply', 'Restore', 'Verify', 'ValidatePayload')][string]$Action,
    [Parameter(Mandatory = $true)][ValidateSet('tw_launcher', 'jp_launcher')][string]$Target,
    [string]$Hint,
    [ValidateSet('vi', 'en', 'zhcn')][string]$Language = 'zhcn'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$commonPath = Join-Path $PSScriptRoot 'Localization-Common.ps1'
. $commonPath

function Safe([string]$Path) {
    Assert-NoReparse $Path
}

function Hash([string]$p) {
    return Get-FileSha256 $p
}

try {
    $module = Split-Path $PSScriptRoot -Parent
    $planFile = if ($Language -eq 'zhcn') { 'launcher-deployment.json' } else { "launcher-deployment-$Language.json" }
    $planPath = Join-Path $PSScriptRoot $planFile
    Safe $planPath
    $plan = Get-Content -Raw -LiteralPath $planPath -Encoding UTF8 | ConvertFrom-Json
    if ($Action -in @('Apply', 'ValidatePayload') -and ($plan.PSObject.Properties.Name -contains 'status') -and $plan.status -eq 'placeholder-no-payload') {
        throw "Launcher $Language chưa có payload."
    }
    $entry = @($plan.launchers | Where-Object id -eq $Target)
    if ($entry.Count -ne 1) { throw 'Invalid plan target' }
    $entry = $entry[0]
    if ($Action -in @('Apply', 'ValidatePayload') -and ($entry.PSObject.Properties.Name -contains 'status') -and $entry.status -eq 'placeholder-no-payload') {
        throw "Launcher $Target ($Language) chưa được Việt hóa."
    }
    if ($entry.relative_path -ne 'resources/app.asar' -or $entry.payload_dir -ne $Target -or $entry.backup_suffix -notmatch '^\.before-(?:zhcn|vi|en)-\d{8}\.bak$') {
        throw 'Unsafe plan paths'
    }
    foreach ($digest in @($entry.source_sha256, $entry.target_sha256) + @($entry.previous_sha256)) {
        if ($digest -notmatch '^[a-f0-9]{64}$') { throw 'Invalid plan hash' }
    }

    $payloadDir = if ($Language -eq 'zhcn') { 'payload' } else { "payload-$Language" }
    $payload = Join-Path $module "$payloadDir\$Target\resources\app.asar"
    if ($Action -in @('ValidatePayload', 'Apply')) {
        Safe $payload
        if ((Get-Item -LiteralPath $payload).Length -ne [long]$entry.size -or (Hash $payload) -ne $entry.target_sha256) {
            throw 'Bad payload'
        }
        if ($Action -eq 'ValidatePayload') {
            Write-Output "PAYLOAD_OK $Target $($entry.target_sha256)"
            exit 0
        }
    }

    . (Join-Path $PSScriptRoot 'Locate-Installations.ps1')
    $allowed = @($entry.source_sha256, $entry.target_sha256) + @($entry.previous_sha256)
    $resolved = Find-InstallLocations @(
        [pscustomobject]@{
            Id             = $Target
            Label          = $Target
            AllowedHashes  = $allowed
            Version        = [string]$entry.version
            SearchSubpaths = @($entry.search_subpaths)
        }
    ) $(if ($Hint) { @{ $Target = $Hint } } else { @{} }) -SearchRoots @()
    $loc = $resolved[$Target]
    if ($loc.State -ne 'found') { throw $(if ($loc.Problem) { $loc.Problem } else { 'Not found' }) }
    $root = $loc.Path

    $file = Resolve-SafeChild $root 'resources\app.asar'
    Safe $file
    $current = Hash $file
    if ($current -eq $entry.target_sha256) { $state = 'CURRENT' }
    elseif ($current -eq $entry.source_sha256) { $state = 'ORIGINAL' }
    elseif ($current -in $entry.previous_sha256) { $state = 'PRIOR_NEEDS_UPGRADE' }
    else { throw 'Unknown launcher version/hash' }

    $backup = $null
    $canonical = $file + $entry.backup_suffix
    $backups = @(Get-ChildItem -LiteralPath (Split-Path $file -Parent) -Filter 'app.asar.*.bak' -Force)
    foreach ($b in $backups) {
        Safe $b.FullName
        if ((Hash $b.FullName) -ne $entry.source_sha256) {
            if ($b.FullName -eq $canonical) { throw "Bad canonical backup refused: $($b.FullName)" }
            Write-Verbose "Skipped non-source backup: $($b.FullName)"
            continue
        }
        if (-not $backup -or $b.FullName -eq $canonical) { $backup = $b.FullName }
    }

    if ($Action -eq 'Verify') {
        Write-Output "$state $Target $current"
        if ($state -eq 'PRIOR_NEEDS_UPGRADE') { exit 2 }
        exit 0
    }

    $procName = [IO.Path]::GetFileNameWithoutExtension($entry.exe)
    $launcherAlwaysRefuse = if ($procName -ne 'launcher') { @($procName) } else { @() }
    $assertStopped = {
        Assert-ProcessesStopped -ProcessNames @($procName) -PathScopes @($root) -FriendlyError "请先完全退出启动器：$($entry.exe)" -AlwaysRefuseNames $launcherAlwaysRefuse
    }

    if ($Action -eq 'Restore' -and $state -eq 'ORIGINAL') {
        Write-Output "ALREADY_ORIGINAL $Target"
        exit 0
    }
    if ($Action -eq 'Apply' -and $state -eq 'CURRENT') {
        Write-Output "ALREADY_CURRENT $Target"
        exit 0
    }

    & $assertStopped

    $desired = if ($Action -eq 'Restore') { $backup } else { $payload }
    $expected = if ($Action -eq 'Restore') { $entry.source_sha256 } else { $entry.target_sha256 }

    if (-not $backup) {
        if ($state -ne 'ORIGINAL') { throw 'Verified original backup required' }
        Assert-FreeDiskSpace (Split-Path $file -Parent) ([long](Get-Item -LiteralPath $file).Length + [long]$entry.size)
        Safe $canonical
        $src = [IO.File]::Open($file, 'Open', 'Read', 'Read')
        try {
            $dst = [IO.File]::Open($canonical, 'CreateNew', 'Write', 'None')
            try {
                $src.CopyTo($dst)
                $dst.Flush($true)
            } finally {
                $dst.Dispose()
            }
        } finally {
            $src.Dispose()
        }
        if ((Hash $canonical) -ne $entry.source_sha256) { throw 'Backup verification failed' }
        $backup = $canonical
        if ($Action -eq 'Restore') { $desired = $backup }
    }

    $desiredSize = [long](Get-Item -LiteralPath $desired).Length
    Assert-FreeDiskSpace (Split-Path $file -Parent) ($desiredSize * 2)

    $stage = $file + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $rollback = $file + '.' + [Guid]::NewGuid().ToString('N') + '.rollback'
    $replaced = $false
    $preserveRollback = $false
    try {
        Safe $stage
        Safe $rollback
        [IO.File]::Copy($desired, $stage, $false)
        if ((Hash $stage) -ne $expected) { throw 'Stage verification failed' }
        & $assertStopped
        Safe $file
        Safe $backup
        if ((Hash $file) -ne $current -or (Hash $backup) -ne $entry.source_sha256) {
            throw 'Concurrent modification detected'
        }
        [IO.File]::Replace($stage, $file, $rollback, $true)
        $replaced = $true
        if ((Hash $file) -ne $expected) { throw 'Post-replace verification failed' }
        Write-Output "$($Action.ToUpperInvariant())_OK $Target $expected"
    } catch {
        if ($replaced) {
            $preserveRollback = $true
            Write-Warning "Attempting recovery; if recovery fails preserve snapshot at: $rollback"
            if ((Hash $rollback) -ne $current) { throw 'Rollback damaged; manual recovery required' }
            [IO.File]::Copy($rollback, $stage, $false)
            [IO.File]::Replace($stage, $file, [System.Management.Automation.Language.NullString]::Value, $true)
            if ((Hash $file) -ne $current) { throw "Rollback verification failed; recovery snapshot: $rollback" }
            $preserveRollback = $false
        }
        throw
    } finally {
        foreach ($temp in @($stage, $rollback)) {
            if ($temp -eq $rollback -and $preserveRollback) {
                Write-Warning "Preserved rollback snapshot: $rollback"
                continue
            }
            if (Test-Path -LiteralPath $temp) {
                Safe $temp
                Remove-Item -LiteralPath $temp -Force
            }
        }
    }
} catch {
    Write-Error $_
    exit 1
}
