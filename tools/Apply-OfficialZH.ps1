# 自动定位、备份、汉化与还原。
param(
    [ValidateSet('Menu','Apply','Restore','Verify')][string]$Action = 'Menu',
    [string]$Select = '',
    [string]$Hint = '',
    [switch]$OnlyHint,
    [switch]$Elevated
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false) } catch {}
$PackRoot = Split-Path $PSScriptRoot -Parent
$plan = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'deployment-plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$UninstallKeys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
$script:hashCache = @{}
$script:commonDirs = $null

# 文件校验与权限处理
function Get-Sha([string]$Path, [switch]$NoCache) {
    $fi = New-Object IO.FileInfo($Path)
    $key = $fi.FullName.ToLowerInvariant() + '|' + $fi.Length + '|' + $fi.LastWriteTimeUtc.Ticks
    if (-not $NoCache -and $script:hashCache.ContainsKey($key)) { return $script:hashCache[$key] }
    $stream = [IO.File]::OpenRead($Path); $alg = [Security.Cryptography.SHA256]::Create()
    try { $h = [BitConverter]::ToString($alg.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $alg.Dispose(); $stream.Dispose() }
    $script:hashCache[$key] = $h
    return $h
}
function To-Full([string]$p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return $null }
    try { $f = [IO.Path]::GetFullPath($p.Trim().Trim('"')); if ($f.Length -gt 3) { $f = $f.TrimEnd('\') }; return $f } catch { return $null }
}
function To-Win([string]$r) { return ($r -replace '/','\') }
function Combine([string]$a, [string]$b) { try { return [IO.Path]::Combine($a, (To-Win $b)) } catch { return $null } }
function Get-ChildDirs([string]$p) {
    if (-not $p) { return @() }
    try { return @(Get-ChildItem -LiteralPath $p -Directory -Force -ErrorAction SilentlyContinue | Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | ForEach-Object { $_.FullName }) } catch { return @() }
}
function Test-Writable([string]$Dir) {
    $probe = Combine $Dir ('.zhcn-write-test-' + [Guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($probe,'x'); [IO.File]::Delete($probe); return $true } catch { return $false }
}
function Replace-Checked([string]$Source, [string]$Target, [string]$Expected) {
    $temp = $Target + '.zhcn-stage-' + [Guid]::NewGuid().ToString('N')
    try {
        [IO.File]::Copy($Source, $temp, $false)
        if ((Get-Sha $temp -NoCache) -ne $Expected) { throw "暂存文件校验失败：$Target" }
        [IO.File]::Replace($temp, $Target, [System.Management.Automation.Language.NullString]::Value)
        if ((Get-Sha $Target -NoCache) -ne $Expected) { throw "写入后校验失败：$Target" }
    } finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
}

# 查找安装目录
function Get-HintDirs {
    $l = @()
    if ($Hint) {
        $h = To-Full $Hint
        if ($h) {
            if ([IO.File]::Exists($h)) { $h = Split-Path $h -Parent }
            $l += $h
            $par = Split-Path $h -Parent; if ($par) { $l += $par }
            foreach ($c in (Get-ChildDirs $h)) { $l += $c; $l += @(Get-ChildDirs $c) }
        }
    }
    return $l
}
function Get-CommonDirs {
    if ($null -ne $script:commonDirs) { return $script:commonDirs }
    $l = New-Object 'System.Collections.Generic.List[string]'
    $d = $PackRoot
    for ($i = 0; $i -lt 4 -and $d; $i++) { $l.Add($d); $d = Split-Path $d -Parent }
    foreach ($drive in @(Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
        $r = $drive.Root
        if (-not $r -or -not [IO.Directory]::Exists($r)) { continue }
        $l.Add($r)
        foreach ($s in @('Program Files','Program Files (x86)','Games','Game','游戏','遊戲')) { $l.Add((Combine $r $s)) }
        foreach ($c in (Get-ChildDirs $r)) { $l.Add($c) }
    }
    $script:commonDirs = @($l)
    return $script:commonDirs
}
function Get-RegistryDirs($patterns) {
    $l = @()
    foreach ($k in @(Get-ItemProperty $UninstallKeys -ErrorAction SilentlyContinue)) {
        $hit = $false
        foreach ($p in @($patterns)) { if (([string]$k.PSChildName) -like $p -or ([string]$k.DisplayName) -like $p) { $hit = $true } }
        if (-not $hit) { continue }
        $loc = [string]$k.InstallLocation; if ($loc) { $l += $loc }
        $icon = (([string]$k.DisplayIcon) -replace ',\s*-?\d+$','').Trim().Trim('"')
        if ($icon) { $d = Split-Path $icon -Parent; if ($d) { $l += $d; $pp = Split-Path $d -Parent; if ($pp) { $l += $pp } } }
    }
    return $l
}
function Get-ProcessDirs($names) {
    $l = @()
    foreach ($n in @($names)) {
        foreach ($p in @(Get-CimInstance Win32_Process -Filter ("Name='{0}'" -f $n) -ErrorAction SilentlyContinue)) {
            if ($p.ExecutablePath) { $d = Split-Path $p.ExecutablePath -Parent; $l += $d; $pp = Split-Path $d -Parent; if ($pp) { $l += $pp } }
        }
    }
    return $l
}
function Test-GameRoot($g, [string]$root) {
    try {
        if (-not [IO.File]::Exists((Combine $root $g.exe))) { return $false }
        $md = Combine (Combine $root $g.data_dir) $g.marker_dir
        if (-not [IO.Directory]::Exists($md)) { return $false }
        return [bool](Get-ChildItem -LiteralPath $md -Filter $g.marker_filter -File -ErrorAction SilentlyContinue | Select-Object -First 1)
    } catch { return $false }
}
function New-GameItem($g, [string]$root) {
    $data = Combine $root $g.data_dir
    $bk = Combine $root $g.backup_folder_name
    $entries = @(foreach ($f in @($g.files)) {
        [PSCustomObject]@{
            Name = $f.relative_path; Target = (Combine $data $f.relative_path)
            Payload = (Combine (Combine (Combine $PackRoot 'payload') $g.payload_dir) $f.relative_path)
            Backup = (Combine $bk $f.relative_path); Source = $f.source_sha256; TargetSha = $f.target_sha256; Previous = @($f.previous_sha256)
        }
    })
    return [PSCustomObject]@{ Kind='game'; Label=$g.label; Root=$root; WriteDir=$data; SnapRoot=(Combine $bk 'rollback'); Entries=$entries; ProcNames=@($g.process_names); ProcExe=$null }
}
function New-LauncherItem($L, [string]$dir) {
    $t = Combine $dir $L.relative_path
    $e = [PSCustomObject]@{
        Name = $L.relative_path; Target = $t
        Payload = (Combine (Combine (Combine $PackRoot 'payload') $L.payload_dir) $L.relative_path)
        Backup = ($t + $L.backup_suffix); Source = $L.source_sha256; TargetSha = $L.target_sha256; Previous = @($L.previous_sha256)
    }
    $wd = Split-Path $t -Parent
    return [PSCustomObject]@{ Kind='launcher'; Label=$L.label; Root=$dir; WriteDir=$wd; SnapRoot=(Combine $wd '.zhcn-rollback'); Entries=@($e); ProcNames=@($L.exe); ProcExe=(Combine $dir $L.exe) }
}
function Find-Items {
    $items = New-Object 'System.Collections.Generic.List[object]'
    $hintDirs = @(Get-HintDirs)
    $common = if ($OnlyHint) { @() } else { @(Get-CommonDirs) }
    foreach ($g in @($plan.games)) {
        $specific = $hintDirs
        if (-not $OnlyHint) { $specific = @($specific) + @(Get-RegistryDirs $g.registry_patterns) + @(Get-ProcessDirs @($g.exe)) }
        $seen = @{}; $roots = @()
        foreach ($b in (@($specific) + @($common))) {
            if (-not $b) { continue }
            $cands = @($b) + @(foreach ($s in @($g.search_subpaths)) { Combine $b $s })
            foreach ($c in $cands) {
                $f = To-Full $c; if (-not $f) { continue }
                $k = $f.ToLowerInvariant(); if ($seen.ContainsKey($k)) { continue }; $seen[$k] = 1
                if (Test-GameRoot $g $f) { $roots += $f }
            }
        }
        foreach ($r in @($roots | Sort-Object)) { $items.Add((New-GameItem $g $r)) }
    }
    foreach ($L in @($plan.launchers)) {
        $specific = $hintDirs
        if (-not $OnlyHint) { $specific = @($specific) + @(Get-RegistryDirs $L.registry_patterns) + @(Get-ProcessDirs @($L.exe)) }
        $cands = New-Object 'System.Collections.Generic.List[string]'
        foreach ($b in @($specific)) { if ($b) { $cands.Add($b); foreach ($c in (Get-ChildDirs $b)) { $cands.Add($c) } } }
        foreach ($b in (@($specific) + @($common))) {
            if (-not $b) { continue }
            foreach ($s in @($L.search_subpaths)) { $p = Combine $b $s; if ($p) { $cands.Add($p); foreach ($c in (Get-ChildDirs $p)) { $cands.Add($c) } } }
        }
        $seen = @{}; $known = @(); $mismatch = $null
        foreach ($c in $cands) {
            $f = To-Full $c; if (-not $f) { continue }
            $k = $f.ToLowerInvariant(); if ($seen.ContainsKey($k)) { continue }; $seen[$k] = 1
            if (-not ([IO.File]::Exists((Combine $f $L.exe)) -and [IO.File]::Exists((Combine $f $L.relative_path)))) { continue }
            $it = New-LauncherItem $L $f
            if ((Get-EntryState $it.Entries[0]) -eq '版本不匹配') { if (-not $mismatch) { $mismatch = $it } } else { $known += $it }
        }
        if ($known.Count) { foreach ($it in @($known | Sort-Object Root)) { $items.Add($it) } } elseif ($mismatch) { $items.Add($mismatch) }
    }
    return $items.ToArray()
}

# 检查文件状态
function Get-EntryState($e) {
    if (-not [IO.File]::Exists($e.Target)) { return '缺少文件' }
    $h = Get-Sha $e.Target
    if ($h -eq $e.TargetSha) { return '已汉化' }
    if ($h -eq $e.Source) { return '原版' }
    if ($h -in @($e.Previous)) { return '旧版汉化' }
    return '版本不匹配'
}
function Get-ItemSummary($it) {
    $st = @($it.Entries | ForEach-Object { Get-EntryState $_ })
    $p = @($st | Where-Object { $_ -eq '已汉化' }).Count
    $o = @($st | Where-Object { $_ -eq '原版' }).Count
    if ($p -eq $st.Count) { return '已汉化' }
    if ($o -eq $st.Count) { return '原版' }
    if (@($st | Where-Object { $_ -in @('版本不匹配','缺少文件') }).Count) { return '版本不匹配' }
    return "部分汉化 $p/$($st.Count)"
}
function Test-ItemRunning($it) {
    foreach ($n in @($it.ProcNames)) {
        foreach ($p in @(Get-CimInstance Win32_Process -Filter ("Name='{0}'" -f $n) -ErrorAction SilentlyContinue)) {
            $ep = To-Full ([string]$p.ExecutablePath)
            if (-not $ep) { return $true }
            if ($it.Kind -eq 'launcher') { if ($ep -ieq $it.ProcExe) { return $true } }
            elseif ($ep.StartsWith($it.Root + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
        }
    }
    return $false
}
function Ensure-Backup($e) {
    if ([IO.File]::Exists($e.Backup)) {
        if ((Get-Sha $e.Backup) -ne $e.Source) { throw "原版备份不匹配：$($e.Backup)" }
        return
    }
    $from = $null
    if ([IO.File]::Exists($e.Target) -and (Get-Sha $e.Target) -eq $e.Source) { $from = $e.Target }
    else {
        $leaf = Split-Path $e.Target -Leaf
        foreach ($f in @(Get-ChildItem -LiteralPath (Split-Path $e.Target -Parent) -Filter ($leaf + '.*.bak') -File -Force -ErrorAction SilentlyContinue)) {
            if ((Get-Sha $f.FullName) -eq $e.Source) { $from = $f.FullName; break }
        }
    }
    if (-not $from) { throw "找不到原版文件，无法安全继续：$($e.Target)" }
    [IO.Directory]::CreateDirectory((Split-Path $e.Backup -Parent)) | Out-Null
    [IO.File]::Copy($from, $e.Backup, $false)
    if ((Get-Sha $e.Backup -NoCache) -ne $e.Source) { throw "备份校验失败：$($e.Backup)" }
}

# 汉化与还原⁠​‌​​​​​‌​‌​​‌​​‌​​‌​‌‌​‌​‌​​​‌‌‌​‌​​​‌​‌​‌​​‌‌‌​​‌​​​‌​‌​‌​‌​​‌​​‌​​​​​‌​‌​‌​‌​​​‌​​​‌​‌​‌​​​‌​​​‌‌‌‌‌​​‌‌‌​​‌​‌‌​‌‌​​​​‌​​‌​‌​​‌‌‌​​‌​‌‌​‌​‌‌‌​‌​​​‌​​‌​‌‌‌‌‌​​​​‌‌​​‌​​​‌‌​​​​​​‌‌​​‌​​​‌‌​‌‌​​​‌​‌‌​‌​​‌‌​​​‌​​‌‌​​​‌​​‌​‌‌​‌​​‌‌​​‌​​​‌‌​‌​‌⁠
function Invoke-Operation($items, [bool]$restore) {
    $want = if ($restore) { '原版' } else { '已汉化' }
    $verb = if ($restore) { '还原' } else { '汉化' }
    $work = New-Object 'System.Collections.Generic.List[object]'
    $workItems = New-Object 'System.Collections.Generic.List[object]'
    $skipped = 0
    foreach ($it in $items) {
        try {
            Write-Host ("正在检查 [{0}] {1} ……" -f $it.Label, $it.Root)
            $states = @($it.Entries | ForEach-Object { Get-EntryState $_ })
            $bad = @(); $todo = @()
            for ($i = 0; $i -lt $states.Count; $i++) {
                if ($states[$i] -in @('版本不匹配','缺少文件')) { $bad += ($it.Entries[$i].Name + '（' + $states[$i] + '）') }
                elseif ($states[$i] -ne $want) { $todo += $it.Entries[$i] }
            }
            if ($bad.Count) { throw ('文件与本补丁对应的版本不符（游戏或启动器可能已更新），未修改：' + ($bad -join '；')) }
            if ($todo.Count -eq 0) { Write-Host ("  [{0}] 已经是{1}，无需处理。" -f $it.Label, $want) -ForegroundColor Green; continue }
            if (Test-ItemRunning $it) { throw '正在运行，请完全退出（包括右下角托盘图标）后再执行。' }
            if (-not $restore) {
                foreach ($e in $todo) { if (-not [IO.File]::Exists($e.Payload) -or (Get-Sha $e.Payload) -ne $e.TargetSha) { throw "补丁包文件缺失或损坏，请重新下载并完整解压：$($e.Name)" } }
            }
            $bset = if ($restore) { $todo } else { $it.Entries }
            foreach ($e in $bset) { Ensure-Backup $e }
            foreach ($e in $todo) {
                $src = if ($restore) { $e.Backup } else { $e.Payload }
                $exp = if ($restore) { $e.Source } else { $e.TargetSha }
                $work.Add([PSCustomObject]@{ Item=$it; Entry=$e; Source=$src; Expected=$exp; Snap=$null; Before=$null })
            }
            $workItems.Add($it)
        } catch {
            $skipped++
            Write-Host ("  [{0}] 已跳过：{1}" -f $it.Label, $_.Exception.Message) -ForegroundColor Yellow
        }
    }
    if ($work.Count -eq 0) { return $skipped }
    Write-Host '正在创建回滚快照……'
    foreach ($w in $work) {
        $dir = Combine $w.Item.SnapRoot ([Guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($dir) | Out-Null
        $sp = Combine $dir (Split-Path $w.Entry.Target -Leaf)
        $h = Get-Sha $w.Entry.Target
        [IO.File]::Copy($w.Entry.Target, $sp, $false)
        if ((Get-Sha $sp -NoCache) -ne $h) { throw '回滚快照校验失败，尚未修改任何文件。' }
        $w.Snap = $sp; $w.Before = $h
    }
    foreach ($it in $workItems) { if (Test-ItemRunning $it) { throw "[$($it.Label)] 正在运行，已停止，未修改任何文件。" } }
    $done = New-Object 'System.Collections.Generic.List[object]'
    try {
        $i = 0
        foreach ($w in $work) {
            $i++
            Write-Host ("  [{0}/{1}] {2}：{3}" -f $i, $work.Count, $w.Item.Label, $w.Entry.Name)
            $done.Add($w)
            Replace-Checked $w.Source $w.Entry.Target $w.Expected
        }
    } catch {
        $problem = $_.Exception.Message; $errs = @()
        for ($j = $done.Count - 1; $j -ge 0; $j--) {
            $w = $done[$j]
            try { if ((Get-Sha $w.Entry.Target -NoCache) -ne $w.Before) { Replace-Checked $w.Snap $w.Entry.Target $w.Before } }
            catch { $errs += ($w.Entry.Name + '：' + $_.Exception.Message) }
        }
        if ($errs.Count) { throw ("${verb}失败，部分文件未能回滚，请保留备份目录：$problem；" + ($errs -join '；')) }
        throw "${verb}失败，已恢复到操作前状态：$problem"
    }
    foreach ($w in $work) { try { Remove-Item -LiteralPath (Split-Path $w.Snap -Parent) -Recurse -Force -ErrorAction SilentlyContinue } catch {} }
    foreach ($it in $workItems) { Write-Host ("  [{0}] {1}完成。" -f $it.Label, $verb) -ForegroundColor Green }
    return $skipped
}
function Show-Verify($items) {
    foreach ($it in $items) {
        Write-Host ''
        Write-Host ("[{0}] {1}" -f $it.Label, $it.Root) -ForegroundColor Cyan
        foreach ($e in $it.Entries) { Write-Host ("  {0}  {1}" -f (Get-EntryState $e), $e.Name) }
    }
}
function Parse-Select([string]$text, $items) {
    if ([string]::IsNullOrWhiteSpace($text)) { return @($items) }
    $sel = @()
    foreach ($part in ($text -split '[,，\s]+')) {
        if (-not $part) { continue }
        $n = 0
        if (-not [int]::TryParse($part, [ref]$n) -or $n -lt 1 -or $n -gt $items.Count) { throw "项目编号无效：$part" }
        if ($sel -notcontains $items[$n-1]) { $sel += $items[$n-1] }
    }
    return $sel
}

# 菜单与执行入口⁠​‌​​​​​‌​‌​​‌​​‌​​‌​‌‌​‌​‌​​​‌‌‌​‌​​​‌​‌​‌​​‌‌‌​​‌​​​‌​‌​‌​‌​​‌​​‌​​​​​‌​‌​‌​‌​​​‌​​​‌​‌​‌​​​‌​​​‌‌‌‌‌​​‌‌‌​​‌​‌‌​‌‌​​​​‌​​‌​‌​​‌‌‌​​‌​‌‌​‌​‌‌‌​‌​​​‌​​‌​‌‌‌‌‌​​​​‌‌​​‌​​​‌‌​​​​​​‌‌​​‌​​​‌‌​‌‌​​​‌​‌‌​‌​​‌‌​​​‌​​‌‌​​​‌​​‌​‌‌​‌​​‌‌​​‌​​​‌‌​‌​‌⁠
$exitCode = 0
try {
    Write-Host '=================================================='
    if ($plan.author) { Write-Host ("  {0}/{1}" -f $plan.pack_title, $plan.author) } else { Write-Host ("  {0}" -f $plan.pack_title) }
    Write-Host '  开服后若登录异常请还原文件，此脚本未进行反作弊验证' -ForegroundColor Red
    Write-Host '=================================================='
    if (-not [IO.Directory]::Exists((Combine $PackRoot 'payload'))) { throw '没有找到补丁文件。请先把压缩包完整解压到一个文件夹，再双击其中的 BAT。' }
    Write-Host '正在查找游戏和启动器安装位置……'
    $items = @(Find-Items)
    while ($items.Count -eq 0) {
        if ($Elevated -or $Action -ne 'Menu') { throw '没有找到支持的游戏或启动器。' }
        Write-Host '没有自动找到游戏或启动器。' -ForegroundColor Yellow
        Write-Host '请输入安装文件夹路径（也可以把文件夹拖进本窗口），直接回车退出：'
        $h = Read-Host '路径'
        if ([string]::IsNullOrWhiteSpace($h)) { exit 0 }
        $Hint = $h
        $items = @(Find-Items)
    }
    Write-Host ''
    Write-Host '找到以下项目：'
    for ($i = 0; $i -lt $items.Count; $i++) {
        Write-Host ("  {0}. [{1}] {2}   {3}" -f ($i+1), $items[$i].Label, (Get-ItemSummary $items[$i]), $items[$i].Root)
    }
    foreach ($g in @($plan.games)) { if (-not ($items | Where-Object { $_.Kind -eq 'game' -and $_.Label -eq $g.label })) { Write-Host ("     （未找到{0}）" -f $g.label) -ForegroundColor DarkGray } }
    foreach ($L in @($plan.launchers)) { if (-not ($items | Where-Object { $_.Kind -eq 'launcher' -and $_.Label -eq $L.label })) { Write-Host ("     （未找到{0}）" -f $L.label) -ForegroundColor DarkGray } }
    if ($Action -eq 'Menu') {
        Write-Host ''
        Write-Host '  1. 全部汉化'
        Write-Host '  2. 全部还原'
        Write-Host '  3. 选择项目汉化'
        Write-Host '  4. 选择项目还原'
        Write-Host '  5. 查看文件状态'
        Write-Host '  Q. 退出'
        $choice = ([string](Read-Host '请输入选项并按回车')).Trim()
        switch ($choice) {
            '1' { $Action = 'Apply'; $Select = '' }
            '2' { $Action = 'Restore'; $Select = '' }
            '3' { $Action = 'Apply'; $Select = Read-Host '请输入项目编号（多个用逗号分隔，例如 1,3）' }
            '4' { $Action = 'Restore'; $Select = Read-Host '请输入项目编号（多个用逗号分隔，例如 1,3）' }
            '5' { $Action = 'Verify'; $Select = '' }
            default { exit 0 }
        }
    }
    $selected = @(Parse-Select $Select $items)
    if ($Action -eq 'Verify') { Show-Verify $selected }
    else {
        $needAdmin = @($selected | Where-Object { -not (Test-Writable $_.WriteDir) }).Count -gt 0
        if ($needAdmin) {
            if ($Elevated) { throw '已使用管理员权限，仍无法写入目标目录。' }
            Write-Host '写入目标目录需要管理员权限，正在请求……' -ForegroundColor Yellow
            $argsList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action $Action -Elevated"
            if ($Select) { $argsList += " -Select `"$Select`"" }
            if ($Hint) { $argsList += " -Hint `"$Hint`"" }
            if ($OnlyHint) { $argsList += ' -OnlyHint' }
            Start-Process powershell.exe -Verb RunAs -ArgumentList $argsList -Wait
            exit 0
        }
        Write-Host ''
        $skipped = Invoke-Operation $selected ($Action -eq 'Restore')
        Write-Host ''
        if ($skipped -gt 0) { Write-Host "处理结束，有 $skipped 个项目被跳过，原因见上方提示。" -ForegroundColor Yellow; $exitCode = 2 }
        else { Write-Host '全部完成。' -ForegroundColor Green }
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; $exitCode = 1 }
if ($Elevated) { Read-Host '按回车键关闭' | Out-Null }
exit $exitCode
