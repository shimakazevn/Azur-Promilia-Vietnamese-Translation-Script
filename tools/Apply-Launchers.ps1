[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidateSet('Apply','Restore','Verify','ValidatePayload')][string]$Action,
 [Parameter(Mandatory=$true)][ValidateSet('tw_launcher','jp_launcher')][string]$Target,
 [string]$Hint,
 [ValidateSet('vi','en','zhcn')][string]$Language='zhcn'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
function Safe([string]$Path) {
 $p=[IO.Path]::GetFullPath($Path)
 if ($p.StartsWith('\\')) { throw 'UNC paths refused' }
 while ($p) {
  if (Test-Path -LiteralPath $p) {
   if (([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point refused: $p" }
  }
  $p=[IO.Path]::GetDirectoryName($p)
 }
}
function Hash([string]$p) { Safe $p; $stream=[IO.File]::OpenRead($p);$algo=[Security.Cryptography.SHA256]::Create();try { return [BitConverter]::ToString($algo.ComputeHash($stream)).Replace('-','').ToLowerInvariant() } finally {$algo.Dispose();$stream.Dispose()} }
function Stopped {
 foreach ($proc in [Diagnostics.Process]::GetProcessesByName([IO.Path]::GetFileNameWithoutExtension($entry.exe))) {
  try { if (!$proc.HasExited) { $image=$proc.MainModule.FileName; if (($image.StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase))) { throw "Launcher running: $($proc.Id). Close it first." } } } finally { $proc.Dispose() }
 }
}
try {
 $module=Split-Path $PSScriptRoot -Parent
 $planFile=if ($Language -eq 'zhcn') { 'launcher-deployment.json' } else { 'launcher-deployment-'+$Language+'.json' }
 $planPath=Join-Path $PSScriptRoot $planFile;Safe $planPath
 $plan=Get-Content -Raw -LiteralPath $planPath -Encoding UTF8 | ConvertFrom-Json
 if ($plan.status -eq 'placeholder-no-payload') { throw "Launcher payload $Language chua duoc build: chua co app.asar dich thay the. Xem README muc Trang thai ngon ngu." }
 $payloadDir=if ($Language -eq 'zhcn') { 'payload' } else { 'payload-'+$Language }
 $entry=@($plan.launchers | Where-Object id -eq $Target)
 if ($entry.Count -ne 1) { throw 'Invalid plan target' };$entry=$entry[0]
 if ($entry.relative_path -ne 'resources/app.asar' -or $entry.payload_dir -ne $Target -or $entry.backup_suffix -notmatch '^\.before-(zhcn|vi|en)-\d{8}\.bak$') { throw 'Unsafe plan paths' }
 foreach ($digest in @($entry.source_sha256,$entry.target_sha256)+@($entry.previous_sha256)) { if ($digest -notmatch '^[a-f0-9]{64}$') { throw 'Invalid plan hash' } }
 $payload=Join-Path $module "$payloadDir\$Target\resources\app.asar"
 if ((Hash $payload) -ne $entry.target_sha256 -or (Get-Item -LiteralPath $payload).Length -ne $entry.size) { throw 'Bad payload' }
 if ($Action -eq 'ValidatePayload') { Write-Output "PAYLOAD_VALID $Target $($entry.target_sha256)";exit 0 }
 if ($PSBoundParameters.ContainsKey('Hint')) {
  if ([string]::IsNullOrWhiteSpace($Hint) -or ![IO.Path]::IsPathRooted($Hint)) { throw 'Hint must be an absolute exact launcher root' }
  $root=[IO.Path]::GetFullPath($Hint);Safe $root
  if (!(Test-Path -LiteralPath (Join-Path $root 'resources\app.asar') -PathType Leaf)) { throw 'Hint does not contain resources/app.asar; no fallback' }
 } else {
  $candidates=@()
  foreach ($drive in [IO.DriveInfo]::GetDrives()) {
   if (!$drive.IsReady -or $drive.DriveType -ne 'Fixed') { continue }
   foreach ($sub in $entry.search_subpaths) {
    $base=Join-Path $drive.RootDirectory.FullName $sub
    foreach ($candidate in @($base,(Join-Path $base $entry.version))) {
     $file=Join-Path $candidate 'resources\app.asar'
     if (Test-Path -LiteralPath $file -PathType Leaf) {
      Safe $candidate;$hash=Hash $file
      if ($hash -in (@($entry.source_sha256,$entry.target_sha256)+@($entry.previous_sha256))) { $candidates+=$candidate }
     }
    }
   }
  }
  $candidates=@($candidates | Select-Object -Unique)
  if ($candidates.Count -ne 1) { throw "Expected one supported fixed-version launcher; found $($candidates.Count). Supply exact Hint." }
  $root=$candidates[0]
 }
 $exePath=Join-Path $root $entry.exe;Safe $exePath
 if (!(Test-Path -LiteralPath $exePath -PathType Leaf)) {throw 'Corresponding launcher EXE required at exact root'}
 $file=Join-Path $root 'resources\app.asar';Safe $file
 $current=Hash $file
 if ($current -eq $entry.target_sha256) {$state='CURRENT'} elseif ($current -eq $entry.source_sha256) {$state='ORIGINAL'} elseif ($current -in $entry.previous_sha256) {$state='PRIOR_NEEDS_UPGRADE'} else {throw 'Unknown launcher version/hash'}
 $backup=$null;$canonical=$file+$entry.backup_suffix
 $backups=@(Get-ChildItem -LiteralPath (Split-Path $file -Parent) -Filter 'app.asar.*.bak' -Force)
 foreach ($b in $backups) {
  Safe $b.FullName
  if ((Hash $b.FullName) -ne $entry.source_sha256) { if ($b.FullName -eq $canonical) {throw "Bad canonical backup refused: $($b.FullName)"}; Write-Verbose "Skipped non-source backup: $($b.FullName)";continue }
  if (!$backup -or $b.FullName -eq $canonical) { $backup=$b.FullName }
 }
 if ($Action -eq 'Verify') { Write-Output "$state $Target $current";if ($state -eq 'PRIOR_NEEDS_UPGRADE') {exit 2};exit 0 }
 Stopped
 if ($Action -eq 'Restore' -and $state -eq 'ORIGINAL') {Write-Output "ALREADY_ORIGINAL $Target";exit 0}
 if (!$backup) {
  if ($state -ne 'ORIGINAL') {throw 'Verified original backup required'}
  Safe $canonical
  $src=[IO.File]::Open($file,'Open','Read','Read');try {$dst=[IO.File]::Open($canonical,'CreateNew','Write','None');try {$src.CopyTo($dst);$dst.Flush($true)} finally {$dst.Dispose()}} finally {$src.Dispose()}
  if ((Hash $canonical) -ne $entry.source_sha256) {throw 'Backup verification failed'};$backup=$canonical
 }
 if ($Action -eq 'Apply' -and $state -eq 'CURRENT') {Write-Output "ALREADY_CURRENT $Target";exit 0}
 $desired=$payload;$expected=$entry.target_sha256
 if ($Action -eq 'Restore') {$desired=$backup;$expected=$entry.source_sha256}
 # Stage and rollback files are transient siblings needed for atomic NTFS replacement.
 $stage=$file+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
 $rollback=$file+'.'+[Guid]::NewGuid().ToString('N')+'.rollback'
 $replaced=$false;$preserveRollback=$false
 try {
  Safe $stage;Safe $rollback
  [IO.File]::Copy($desired,$stage,$false)
  if ((Hash $stage) -ne $expected) {throw 'Stage verification failed'}
  Stopped;Safe $file;Safe $backup
  if ((Hash $file) -ne $current -or (Hash $backup) -ne $entry.source_sha256) {throw 'Concurrent modification detected'}
  [IO.File]::Replace($stage,$file,$rollback,$true);$replaced=$true
  if ((Hash $file) -ne $expected) {throw 'Post-replace verification failed'}
  Write-Output "$($Action.ToUpperInvariant())_OK $Target $expected"
 } catch {
  if ($replaced) {
   $preserveRollback=$true
   Write-Warning "Attempting recovery; if recovery fails preserve snapshot at: $rollback"
   if ((Hash $rollback) -ne $current) {throw 'Rollback damaged; manual recovery required'}
   [IO.File]::Copy($rollback,$stage,$false)
   [IO.File]::Replace($stage,$file,$null,$true)
   if ((Hash $file) -ne $current) {throw "Rollback verification failed; recovery snapshot: $rollback"}
   $preserveRollback=$false
  }
  throw
 } finally {
  foreach ($temp in @($stage,$rollback)) {if ($temp -eq $rollback -and $preserveRollback) {Write-Warning "Preserved rollback snapshot: $rollback";continue};if (Test-Path -LiteralPath $temp) {Safe $temp;Remove-Item -LiteralPath $temp -Force}}
 }
} catch {Write-Error $_;exit 1}
