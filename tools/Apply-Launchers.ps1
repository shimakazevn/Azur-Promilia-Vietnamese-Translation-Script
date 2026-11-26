[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Apply', 'Restore', 'Verify', 'ValidatePayload')][string]$Action,
    [Parameter(Mandatory = $true)][ValidateSet('tw_launcher', 'jp_launcher')][string]$Target,
    [string]$Hint
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
    $planPath = Join-Path $PSScriptRoot 'launcher-deployment.json'
    Safe $planPath
    $plan = Get-Content -Raw -LiteralPath $planPath -Encoding UTF8 | ConvertFrom-Json
    $entry = @($plan.launchers | Where-Object id -eq $Target)
    if ($entry.Count -ne 1) { throw 'Invalid plan target' }
    $entry = $entry[0]
    if ($entry.relative_path -ne 'resources/app.asar' -or $entry.payload_dir -ne $Target -or $entry.backup_suffix -ne '.before-zhcn-20261124.bak') {
        throw 'Unsafe plan paths'
    }
    foreach ($digest in @($entry.source_sha256, $entry.target_sha256) + @($entry.previous_sha256)) {
        if ($digest -notmatch '^[a-f0-9]{64}$') { throw 'Invalid plan hash' }
    }

    $payload = Join-Path $module "payload\$Target\resources\app.asar"
    if ($Action -in @('ValidatePayload', 'Apply')) {
        if (-not [IO.File]::Exists($payload)) { throw "Bad payload: missing $payload" }
        Safe $payload
        if ((Get-Item -LiteralPath $payload).Length -ne $entry.size -or (Hash $payload) -ne $entry.target_sha256) {
            throw 'Bad payload'
        }
        if ($Action -eq 'ValidatePayload') {
            Write-Output "PAYLOAD_VALID $Target $($entry.target_sha256)"
            exit 0
        }
    }

    $root = $null
    if ($PSBoundParameters.ContainsKey('Hint')) {
        if ([string]::IsNullOrWhiteSpace($Hint) -or -not [IO.Path]::IsPathRooted($Hint)) {
            throw 'Hint must be an absolute exact launcher root'
        }
        $root = [IO.Path]::GetFullPath($Hint)
        Safe $root
        if (-not (Test-Path -LiteralPath (Join-Path $root 'resources\app.asar') -PathType Leaf)) {
            throw 'Hint does not contain resources/app.asar; no fallback'
        }
    } else {
        $candidates = New-Object 'System.Collections.Generic.List[string]'
        $seenCandidates = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $allowedSet = @($entry.source_sha256, $entry.target_sha256) + @($entry.previous_sha256)
        foreach ($drive in [IO.DriveInfo]::GetDrives()) {
            if (-not $drive.IsReady -or $drive.DriveType -ne [IO.DriveType]::Fixed) { continue }
            foreach ($sub in $entry.search_subpaths) {
                $base = Join-Path $drive.RootDirectory.FullName $sub
                foreach ($candidate in @($base, (Join-Path $base $entry.version))) {
                    $file = Join-Path $candidate 'resources\app.asar'
                    if (Test-Path -LiteralPath $file -PathType Leaf) {
                        Safe $candidate
                        $fullCand = [IO.Path]::GetFullPath($candidate).TrimEnd('\')
                        if ($seenCandidates.Contains($fullCand)) { continue }
                        $hash = Hash $file
                        if ($hash -in $allowedSet) {
                            $seenCandidates.Add($fullCand) | Out-Null
                            $candidates.Add($fullCand)
                        }
                    }
                }
            }
        }
        if ($candidates.Count -ne 1) {
            throw "Expected one supported fixed-version launcher; found $($candidates.Count). Supply exact Hint."
        }
        $root = $candidates[0]
    }

    $exePath = Join-Path $root $entry.exe
    Safe $exePath
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw 'Corresponding launcher EXE required at exact root'
    }
    $file = Join-Path $root 'resources\app.asar'
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

    & $assertStopped
    if ($Action -eq 'Restore' -and $state -eq 'ORIGINAL') {
        Write-Output "ALREADY_ORIGINAL $Target"
        exit 0
    }
    if ($Action -eq 'Apply' -and $state -eq 'CURRENT') {
        Write-Output "ALREADY_CURRENT $Target"
        exit 0
    }

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

    # Stage and rollback files are transient siblings needed for atomic NTFS replacement.
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

