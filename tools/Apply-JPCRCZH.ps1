param(
    [ValidateSet('Menu','Apply','Restore','Verify','ValidatePayload')][string]$Action = 'Menu',
    [string]$Hint = '',
    [ValidateSet('vi','en','zhcn')][string]$Language = 'zhcn'
)
$ErrorActionPreference = 'Stop'
$script:HintExplicit = $PSBoundParameters.ContainsKey('Hint')
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false) } catch {}
$PackRoot = Split-Path $PSScriptRoot -Parent
$PlanFile=if ($Language -eq 'zhcn') { 'jp-deployment.json' } else { 'jp-deployment-'+$Language+'.json' }
$Plan = Get-Content -LiteralPath (Join-Path $PSScriptRoot $PlanFile) -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Plan.status -eq 'placeholder-no-payload') { throw "Payload $Language chua duoc build: chua co file dich thay the cho 日服. Xem README muc Trang thai ngon ngu." }
$PayloadDir=if ($Language -eq 'zhcn') { 'payload' } else { 'payload-'+$Language }
if (-not ('LocalizationCRC' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.IO;
public static class LocalizationCRC {
    private static readonly uint[] Table = MakeTable();
    private static uint[] MakeTable() {
        uint[] t = new uint[256];
        for (uint i=0; i<256; i++) {
            uint c=i;
            for (int j=0; j<8; j++) c=(c>>1)^((c&1)!=0?0xEDB88320u:0u);
            t[i]=c;
        }
        return t;
    }
    public static uint Range(string path, long offset, long length) {
        using (FileStream f=File.Open(path,FileMode.Open,FileAccess.Read,FileShare.Read)) {
            if(offset<0 || length<0 || offset>f.Length || length>f.Length-offset)
                throw new InvalidDataException("CRC range outside file");
            f.Position=offset; byte[] b=new byte[1048576]; uint c=0xFFFFFFFFu;
            while(length>0) {
                int n=f.Read(b,0,(int)Math.Min(b.Length,length));
                if(n==0)throw new EndOfStreamException();
                for(int i=0;i<n;i++)c=Table[(c^b[i])&255]^(c>>8);
                length-=n;
            }
            return c^0xFFFFFFFFu;
        }
    }
}
'@
}
function Assert-NoReparse([string]$Path) {
    $current=[IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "拒绝重解析点路径：$current" }
        }
        $parent=Split-Path $current -Parent
        if ($parent -eq $current) { break }
        $current=$parent
    }
}
function Resolve-Child([string]$Root,[string]$Relative) {
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $full = [IO.Path]::GetFullPath([IO.Path]::Combine($base,($Relative -replace '/','\')))
    if (-not $full.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)) { throw "路径越界：$Relative" }
    Assert-NoReparse $full
    return $full
}
function Get-Sha([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$alg=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($alg.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose();$alg.Dispose() }
}
function Assert-Allowed([string]$Relative) {
    if ($Relative -eq 'resources.assets') { return }
    if ($Relative -notmatch '^(?:\.res/(?:raw_base_package|raw_streaming_package|default_package)/BundleFiles|StreamingAssets/\.res/(?:default_package|static_package))/[a-z0-9]+\.r$') { throw "不允许写入：$Relative" }
}
function Assert-LauncherStopped([string]$Root) {
    $scope=[IO.Path]::GetFullPath((Split-Path $Root -Parent)).TrimEnd('\')+'\'
    foreach ($p in @([Diagnostics.Process]::GetProcessesByName('AZUPRO_JP_Gamelauncher'))) {
        try { $processPath=$p.MainModule.FileName } catch { throw '无法检查启动器进程路径，请先退出启动器。' }
        if ([string]::IsNullOrWhiteSpace($processPath)) { throw '无法检查启动器进程路径，请先退出启动器。' }
        if ([IO.Path]::GetFullPath($processPath).StartsWith($scope,[StringComparison]::OrdinalIgnoreCase)) { throw '请先完全退出关联启动器：AZUPRO_JP_Gamelauncher.exe' }
    }
}
function Find-GameRoot {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if ($script:HintExplicit) {
        if ([string]::IsNullOrWhiteSpace($Hint)) { throw '显式 Hint 不得为空。' }
        $h = [IO.Path]::GetFullPath($Hint.Trim().Trim('"'))
        if ([IO.File]::Exists($h)) { $h = Split-Path $h -Parent }
        $candidates.Add($h)
        if ((Split-Path $h -Leaf) -eq 'AzurPromiliaJP_Data') { $candidates.Add((Split-Path $h -Parent)) }
        $candidates.Add((Join-Path $h 'AZUPRO_JP'))
        $candidates.Add((Join-Path $h 'YostarGames\AZUPRO_JP'))
    } else {
        foreach ($drive in @(Get-PSDrive -PSProvider FileSystem)) {
            foreach ($rel in @('YostarGames\AZUPRO_JP','Games\YostarGames\AZUPRO_JP','AZUPRO_JP')) {
                $candidates.Add((Join-Path $drive.Root $rel))
            }
        }
    }
    foreach ($c in $candidates) {
        if ([IO.File]::Exists((Join-Path $c 'AzurPromiliaJP.exe')) -and [IO.Directory]::Exists((Join-Path $c 'AzurPromiliaJP_Data'))) { return [IO.Path]::GetFullPath($c) }
    }
    throw '没有找到日服游戏。请把游戏文件夹拖到 BAT 上，或使用 -Hint 指定安装目录。'
}
function Assert-Guards([string]$DataRoot) {
    foreach ($g in $Plan.readonly_files) {
        $p = Resolve-Child $DataRoot $g.relative_path
        if (-not [IO.File]::Exists($p) -or (Get-Sha $p) -ne $g.sha256) { throw "原版只读基线不匹配：$($g.relative_path)" }
    }
}
function Assert-Resource([string]$Path,$Entry,[bool]$Patched) {
    $expected = if ($Patched) { $Entry.target_sha256 } else { $Entry.source_sha256 }
    if (-not [IO.File]::Exists($Path)) { throw "文件缺失：$Path" }
    if ((Get-Item -LiteralPath $Path).Length -ne $Entry.size) { throw "文件大小不匹配：$Path" }
    if ((Get-Sha $Path) -ne $expected) { throw "SHA256 不匹配：$Path" }
    if ($Entry.relative_path.EndsWith('.r')) {
        if ([LocalizationCRC]::Range($Path,0,[long]$Entry.size) -ne [uint32]$Entry.crc32) { throw "整包 CRC 不匹配：$Path" }
        foreach ($s in $Entry.segments) {
            if ([LocalizationCRC]::Range($Path,[long]$s.offset,[long]$s.size) -ne [uint32]$s.crc32) { throw "段 CRC 不匹配：$Path，段 $($s.bundle_index)" }
        }
    }
}
function Replace-Verified([string]$Source,[string]$Target,[string]$Expected) {
    $temp=$Target+'.crc-'+$Language+'-stage-'+[Guid]::NewGuid().ToString('N')
    try {
        [IO.File]::Copy($Source,$temp,$false)
        if ((Get-Sha $temp) -ne $Expected) { throw "暂存文件校验失败：$Target" }
        [IO.File]::Replace($temp,$Target,[System.Management.Automation.Language.NullString]::Value)
    } finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
}
try {
    if ($Plan.region -ne 'jp') { throw '部署清单区域必须为 jp。' }
    $seen=@{}
    foreach ($e in $Plan.files) {
        Assert-Allowed $e.relative_path
        if ($seen.ContainsKey($e.relative_path)) { throw "重复资源路径：$($e.relative_path)" }
        $seen[$e.relative_path]=$true
    }
    foreach ($g in $Plan.readonly_files) {
        if ($seen.ContainsKey($g.relative_path)) { throw "只读路径与资源重叠：$($g.relative_path)" }
    }
    if ($Action -eq 'ValidatePayload') {
        foreach ($e in $Plan.files) {
            Assert-Resource (Resolve-Child (Join-Path $PackRoot "$PayloadDir/jp_game") $e.relative_path) $e $true
            Write-Host ('载荷通过：'+$e.relative_path)
        }
        Write-Host '全部载荷通过：大小、SHA256、整包 CRC、全部段 CRC。' -ForegroundColor Green
        exit 0
    }
    $root=Find-GameRoot
    Assert-NoReparse $root
    $data=Join-Path $root 'AzurPromiliaJP_Data'
    Assert-NoReparse $data
    if ($Language -eq 'zhcn') { $backup=Join-Path $root '.jp-crc-readonly-3219598-backup' } else { $backup=Join-Path $root ".$Language-jp-crc-readonly-3219598-backup" }
    if ($Action -eq 'Menu') {
        Write-Host "日服本地化 ($Language)（清单只读、等长、原 CRC）`n$root"
        Write-Host '1 本地化/Apply   2 还原/Restore   3 完整校验/Verify   其他退出'
        switch ((Read-Host '选择').Trim()) { '1' {$Action='Apply'} '2' {$Action='Restore'} '3' {$Action='Verify'} default {exit 0} }
    }
    Assert-Guards $data
    if ($Action -eq 'Verify') {
        foreach ($e in $Plan.files) {
            $p=Resolve-Child $data $e.relative_path
            $hash=Get-Sha $p
            if ($hash -eq $e.target_sha256) { Assert-Resource $p $e $true; $state='已本地化' }
            elseif ($hash -eq $e.source_sha256) { Assert-Resource $p $e $false; $state='原版' }
            else { throw "文件既非原版也非本版本地化：$($e.relative_path)" }
            Write-Host ("通过 [$state] "+$e.relative_path)
        }
        Write-Host '完整校验通过，所有只读基线保持原字节。' -ForegroundColor Green
        exit 0
    }
    foreach ($processName in @('AzurPromiliaJP','sdkbrowser')) {
        foreach ($p in @([Diagnostics.Process]::GetProcessesByName($processName))) {
            try { $processPath=$p.MainModule.FileName } catch { throw '无法检查游戏进程，请先退出游戏和登录窗口。' }
            if (-not $processPath -or $processPath.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) { throw '请先完全退出游戏和登录窗口。' }
        }
    }
    Assert-LauncherStopped $root
    $todo=New-Object 'System.Collections.Generic.List[object]'
    foreach ($e in $Plan.files) {
        $p=Resolve-Child $data $e.relative_path
        $h=Get-Sha $p
        $bk=Resolve-Child $backup $e.relative_path
        $hasValidBackup=[IO.File]::Exists($bk) -and ((Get-Sha $bk) -eq $e.source_sha256)
        if ($h -ne $e.source_sha256 -and $h -ne $e.target_sha256 -and -not $hasValidBackup) { throw "文件版本不匹配：$($e.relative_path)" }
        if ($Action -eq 'Apply') {
            $src=Resolve-Child (Join-Path $PackRoot "$PayloadDir/jp_game") $e.relative_path
            Assert-Resource $src $e $true
            if (-not [IO.File]::Exists($bk)) {
                if ($h -ne $e.source_sha256) { throw "缺少原版备份：$($e.relative_path)" }
                [IO.Directory]::CreateDirectory((Split-Path $bk -Parent)) | Out-Null
                [IO.File]::Copy($p,$bk,$false)
            }
            if ((Get-Sha $bk) -ne $e.source_sha256) { throw "原版备份不匹配：$bk" }
            if ($h -eq $e.target_sha256) { continue }
            $exp=$e.target_sha256
        } else {
            if ($h -eq $e.source_sha256) { continue }
            Assert-Resource $bk $e $false
            $src=$bk;$exp=$e.source_sha256
        }
        $todo.Add([PSCustomObject]@{Entry=$e;Target=$p;Source=$src;Expected=$exp;Before=$h;Snap=$null})
    }
    # Snapshot every target before the first replacement, so restore is also transactional.
    $snapdir=Join-Path $backup ('transactions\'+[Guid]::NewGuid().ToString('N'))
    foreach ($w in $todo) {
        $sp=Resolve-Child $snapdir $w.Entry.relative_path
        [IO.Directory]::CreateDirectory((Split-Path $sp -Parent)) | Out-Null
        [IO.File]::Copy($w.Target,$sp,$false)
        if ((Get-Sha $sp) -ne $w.Before) { throw '操作前快照验证失败。' }
        $w.Snap=$sp
    }
    $done=New-Object 'System.Collections.Generic.List[object]'
    try {
    Assert-LauncherStopped $root
        Assert-Guards $data
        foreach ($w in $todo) {
            if ((Get-Sha $w.Target) -ne $w.Before) { throw '操作期间目标文件发生变化。' }
            Replace-Verified $w.Source $w.Target $w.Expected
            $done.Add($w)
            Assert-Resource $w.Target $w.Entry ($Action -eq 'Apply')
            Write-Host ('已写入并校验：'+$w.Entry.relative_path)
        }
        Assert-Guards $data
    } catch {
        $reason=$_.Exception.Message
        $rollbackErrors=New-Object 'System.Collections.Generic.List[string]'
        for ($i=$done.Count-1;$i -ge 0;$i--) {
            $w=$done[$i]
            try {
                if ((Get-Sha $w.Target) -ne $w.Before) { Replace-Verified $w.Snap $w.Target $w.Before }
                if ((Get-Sha $w.Target) -ne $w.Before) { throw '回滚后哈希不匹配' }
            } catch { $rollbackErrors.Add(($w.Target+': '+$_.Exception.Message)) }
        }
        if ($rollbackErrors.Count -gt 0) { throw ("操作失败：$reason；以下文件回滚失败，请保留事务快照并手工恢复："+($rollbackErrors -join '；')) }
        throw "已回滚到操作前：$reason"
    }
    Write-Host "$Action 完成。资源大小、段 CRC、整包 CRC 和只读基线均通过。" -ForegroundColor Green
    exit 0
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
