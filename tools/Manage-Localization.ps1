# 汉化与还原菜单、项目选择和操作日志。
param(
    [ValidateSet('Menu','Apply','Restore','Verify','ValidatePayload','CheckPackage')][string]$Action='Menu',
    [ValidateSet('All','TW','JP','Launchers','Games','tw_game','jp_game','tw_launcher','jp_launcher')][string]$Target='All',
    [string]$Hint='',
    [string]$PathsFile='',
    [string[]]$ModuleIds,
    [switch]$OnlyHint,
    [switch]$Elevated,
    [switch]$Quiet
)
$ErrorActionPreference='Stop'
try { [Console]::OutputEncoding=New-Object Text.UTF8Encoding($false); $OutputEncoding=[Console]::OutputEncoding } catch {}
$PackRoot=Split-Path $PSScriptRoot -Parent
$Definitions=@(
    [pscustomobject]@{Id='tw_game';Label='台服游戏';Script='tools/Apply-CRCZH.ps1';Launcher=$false},
    [pscustomobject]@{Id='jp_game';Label='日服游戏';Script='tools/Apply-JPCRCZH.ps1';Launcher=$false},
    [pscustomobject]@{Id='tw_launcher';Label='台服启动器';Script='tools/Apply-Launchers.ps1';Launcher=$true},
    [pscustomobject]@{Id='jp_launcher';Label='日服启动器';Script='tools/Apply-Launchers.ps1';Launcher=$true}
)
function Assert-NoReparse([string]$Path) {
    $current=[IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "拒绝重解析点：$current" }
        }
        $parent=Split-Path $current -Parent
        if ($parent -eq $current) { break }
        $current=$parent
    }
}
function Child([string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':')) { throw "非法包内路径：$Relative" }
    $base=[IO.Path]::GetFullPath($PackRoot).TrimEnd('\')
    $full=[IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (-not $full.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)) { throw "包内路径越界：$Relative" }
    Assert-NoReparse $full
    return $full
}
function Sha([string]$Path) {
    $s=[IO.File]::OpenRead($Path); $a=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($a.ComputeHash($s)).Replace('-','').ToLowerInvariant() }
    finally { $s.Dispose(); $a.Dispose() }
}
function Assert-Package([bool]$Silent=$false) {
    $catalog=Get-Content -LiteralPath (Child 'tools/package-files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($catalog.format -ne 1 -or @($catalog.files).Count -lt 10) { throw '包校验清单格式无效。' }
    $seen=@{}
    foreach ($f in $catalog.files) {
        if ($seen.ContainsKey($f.path)) { throw "重复包路径：$($f.path)" }
        $seen[$f.path]=$true
        $p=Child $f.path
        if (-not [IO.File]::Exists($p) -or (Get-Item -LiteralPath $p).Length -ne $f.size -or (Sha $p) -ne $f.sha256) { throw "包文件损坏/缺失：$($f.path)" }
    }
    foreach ($d in $Definitions) {
        if (-not $seen.ContainsKey($d.Script)) { throw "未登记的模块入口：$($d.Script)" }
    }
    if (-not $Silent) { Write-Host ("整合包文件校验通过：{0} 个文件。" -f @($catalog.files).Count) -ForegroundColor Green }
}
function Selected([string]$Scope) {
    switch ($Scope) {
        'All' { return @($Definitions) }
        'TW' { return @($Definitions | Where-Object { $_.Id.StartsWith('tw_') }) }
        'JP' { return @($Definitions | Where-Object { $_.Id.StartsWith('jp_') }) }
        'Games' { return @($Definitions | Where-Object { -not $_.Launcher }) }
        'Launchers' { return @($Definitions | Where-Object { $_.Launcher }) }
        default { return @($Definitions | Where-Object { $_.Id -eq $Scope }) }
    }
}
function Read-ConfiguredPaths {
    $pathMap=@{}
    $config=if ($PathsFile) { [IO.Path]::GetFullPath($PathsFile) } else { Child 'tools/安装路径.json' }
    if ([IO.File]::Exists($config)) {
        Assert-NoReparse $config
        $paths=Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($prop in $paths.PSObject.Properties) {
            if ($prop.Name -notin @($Definitions.Id) -or $prop.Value -isnot [string]) { throw "安装路径配置无效：$($prop.Name)" }
            if ($prop.Value.Contains([char]0) -or $prop.Value -match '[\r\n]') { throw '目录不能包含控制字符。' }
            $pathMap[$prop.Name]=$prop.Value
        }
    } elseif ($PathsFile) { throw "安装路径配置不存在：$config" }
    return $pathMap
}
function Get-FriendlyFailure([string]$Detail) {
    switch -Regex ($Detail) {
        'Launcher\s*runni\s*ng|请先完全退出|正在运行|Close\s+it\s+first' {
            $process=[regex]::Match($Detail,'(?i)\b(?:launcher|AZUPRO_JP_Gamelauncher|AzurPromiliaJP|AzurPromilia)\.exe\b').Value
            if ($process) { return ('未处理：'+$process+' 未退出。') }
            if ($Detail -match 'Launcher\s*runni\s*ng|Close\s+it\s+first') { return '未处理：启动器未退出。' }
            return '未处理：启动器或游戏未退出。'
        }
        'rollback.*(damaged|verification failed)|未能回滚|回滚失败' { return '失败：自动回滚失败，请保留备份。' }
        'Unknown launcher version|版本不匹配|基线不匹配|版本不符' { return '未处理：文件版本与本补丁不匹配。' }
        'Bad canonical backup|Verified original backup required|Backup verification failed|原版备份|缺少原版备份' { return '失败：原版备份缺失或校验不通过。' }
        'Bad payload|包文件损坏|载荷|补丁包文件缺失' { return '未处理：补丁文件缺失或损坏，请完整解压后重试。' }
        'Access.*denied|UnauthorizedAccess|拒绝访问|权限' { return '未完成：没有写入权限，请以管理员身份重试。' }
        'CRC.*不匹配|SHA256.*不匹配|大小不匹配|verification failed' { return '失败：文件校验不通过。' }
        'Concurrent modification' { return '失败：文件被其他程序修改。' }
        default {
            $line=@($Detail -split '[\r\n]+' | Where-Object {
                $_.Trim() -and $_ -notmatch '^\s*(\+|~|At |所在位置|CategoryInfo|FullyQualifiedErrorId|PositionMessage|ScriptStackTrace)'
            } | Select-Object -Last 1)
            if ($line.Count) {
                $reason=($line[0] -replace '^.*?\.ps1\s*:\s*','').Trim()
                if ($reason.Length -gt 140) { $reason=$reason.Substring(0,140)+'…' }
                return ('失败：'+$reason)
            }
            return '失败：子任务未返回错误原因。'
        }
    }
}
function Run-Modules([string]$Operation,[string]$Scope,[string[]]$Ids,[hashtable]$MenuLocations,[bool]$Silent=$false) {
    Assert-Package $Silent
    if ($Operation -eq 'CheckPackage') { return 0 }
    $selected=@(Selected $Scope)
    if ($Ids) { $selected=@($selected | Where-Object { $_.Id -in $Ids }) }
    if (-not $selected.Count) { throw '没有可操作的项目。' }
    if ($Hint -and -not $MenuLocations -and $selected.Count -ne 1) { throw '-Hint 只适用于单个模块；多个目录请编辑安装路径.json 或使用 -PathsFile。' }
    $pathMap=Read-ConfiguredPaths
    $locations=$null
    if ($Operation -ne 'ValidatePayload') {
        if ($MenuLocations) { $locations=$MenuLocations }
        elseif (-not $Hint) { $locations=Find-InstallLocations $selected $pathMap }
    }
    $runId=[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
    $logDir=Child ('tools/logs/'+$runId)
    [IO.Directory]::CreateDirectory($logDir) | Out-Null
    $results=New-Object 'System.Collections.Generic.List[object]'
    $shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    foreach ($d in $selected) {
        if (-not $Silent) { Write-Host ("`n=== {0} / {1} ===" -f $d.Label,$Operation) -ForegroundColor Cyan }
        $started=[DateTime]::UtcNow.ToString('o'); $code=1; $errorText=$null
        $log=Join-Path $logDir ($d.Id+'.log')
        try {
            $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',(Child $d.Script),'-Action',$Operation)
            if ($d.Launcher) { $arguments+=@('-Target',$d.Id) }
            $moduleHint=''
            if ($Operation -ne 'ValidatePayload') {
                if ($Hint -and -not $MenuLocations) { $moduleHint=$Hint }
                else {
                    $location=$locations[$d.Id]
                    if ($location.State -ne 'found') { throw ($d.Label+'：'+$location.Problem) }
                    $moduleHint=$location.Path
                }
            }
            if ($moduleHint) { $arguments+=@('-Hint',$moduleHint) }
            $savedPreference=$ErrorActionPreference
            try {
                $ErrorActionPreference='Continue'
                $output=@(& $shell @arguments 2>&1)
                $code=$LASTEXITCODE
            } finally { $ErrorActionPreference=$savedPreference }
            $capturedText=(@($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine)
            $capturedText | Out-File -LiteralPath $log -Encoding UTF8
            if ($code -ne 0) { $errorText=$capturedText.Trim() }
            if (-not $Silent) { foreach ($line in $output) { Write-Host $line } }
        } catch {
            $errorText=$_.Exception.Message
            if (-not $Silent) { Write-Host $errorText -ForegroundColor Red }
            $errorText | Out-File -LiteralPath $log -Encoding UTF8
        }
        $results.Add([pscustomobject]@{module=$d.Id;label=$d.Label;action=$Operation;exit_code=$code;success=($code -eq 0);started_utc=$started;ended_utc=[DateTime]::UtcNow.ToString('o');log=$log;error=$errorText})
        if ($Silent) {
            if ($code -eq 0) {
                $verb=switch ($Operation) { 'Restore' {'还原完成'} 'Apply' {'汉化完成'} default {'校验通过'} }
                Write-Host ('  [{0}] {1}。' -f $d.Label,$verb) -ForegroundColor Green
            } else {
                Write-Host ('  [{0}] {1}' -f $d.Label,(Get-FriendlyFailure $errorText)) -ForegroundColor Yellow
            }
        }
    }
    $failed=@($results | Where-Object { -not $_.success })
    $report=[ordered]@{format=1;action=$Operation;scope=$Scope;success=($failed.Count -eq 0);cross_module_atomic=$false;results=@($results.ToArray());runtime_login_tested=$false}
    $report | ConvertTo-Json -Depth 8 | Out-File -LiteralPath (Join-Path $logDir 'result.json') -Encoding UTF8
    if ($Silent) {
        if ($failed.Count) { return 2 }
        return 0
    }
    Write-Host "`n=== 本次结果 ==="
    foreach ($r in $results) {
        $state=if($r.success){'通过'}else{'失败/未完成'}
        Write-Host ("{0}：{1}（退出码 {2}）" -f $r.label,$state,$r.exit_code)
    }
    Write-Host ("日志："+$logDir)
    if ($failed.Count) {
        Write-Host '存在失败模块；成功模块不会跨模块自动还原。请查看日志，修正后单独重试。' -ForegroundColor Yellow
        return 2
    }
    if ($Operation -eq 'Verify') { Write-Host '校验接受原版和本版汉化；请看逐文件状态，这不等于全部已经汉化。' }
    Write-Host '本地操作通过不代表服务端校验或登录已经验证。'
    return 0
}

function Install-Child([string]$Root,[string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':')) { throw '非法安装文件路径。' }
    $base=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    $full=[IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (-not $full.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)) { throw '安装文件路径越界。' }
    Assert-NoReparse $full
    return $full
}
function Get-ItemSummary($Definition,[string]$Root) {
    try {
        if ($Definition.Launcher) {
            $entry=@($launcherPlan.launchers | Where-Object { $_.id -eq $Definition.Id })[0]
            $file=Install-Child $Root $entry.relative_path
            if (-not [IO.File]::Exists($file)) { return '缺少文件' }
            $hash=Sha $file
            if ($hash -eq $entry.source_sha256) { return '原版' }
            if ($hash -eq $entry.target_sha256) { return '已汉化' }
            if ($hash -in @($entry.previous_sha256)) { return '旧版汉化' }
            return '版本不匹配'
        }
        $plan=$gamePlans[$Definition.Id]
        $dataName=if ($Definition.Id -eq 'tw_game') { 'AzurPromilia_Data' } else { 'AzurPromiliaJP_Data' }
        $dataRoot=Install-Child $Root $dataName
        foreach ($guard in $plan.readonly_files) {
            $file=Install-Child $dataRoot $guard.relative_path
            if (-not [IO.File]::Exists($file)) { return '缺少文件' }
            if ((Sha $file) -ne $guard.sha256) { return '版本不匹配' }
        }
        $original=0; $localized=0
        foreach ($entry in $plan.files) {
            $file=Install-Child $dataRoot $entry.relative_path
            if (-not [IO.File]::Exists($file)) { return '缺少文件' }
            if ((Get-Item -LiteralPath $file).Length -ne $entry.size) { return '版本不匹配' }
            $hash=Sha $file
            if ($hash -eq $entry.source_sha256) { $original++ }
            elseif ($hash -eq $entry.target_sha256) { $localized++ }
            else { return '版本不匹配' }
        }
        if ($original -eq @($plan.files).Count) { return '原版' }
        if ($localized -eq @($plan.files).Count) { return '已汉化' }
        return '部分汉化'
    } catch { return '无法读取' }
}
function Parse-Select([string]$Text,$Items) {
    $value=$Text.Trim()
    if ($value -in @('q','0')) { return @() }
    if (-not $value) { return @($Items.Id) }
    $ids=New-Object 'System.Collections.Generic.List[string]'
    foreach ($token in ($value -split '[,，\s]+')) {
        if (-not $token) { continue }
        $number=0
        if (-not [int]::TryParse($token,[ref]$number) -or $number -lt 1 -or $number -gt $Items.Count) {
            throw ('项目编号无效：'+$token)
        }
        $id=$Items[$number-1].Id
        if (-not $ids.Contains($id)) { $ids.Add($id) }
    }
    return $ids.ToArray()
}

function Find-MenuLocations([hashtable]$ConfiguredPaths,[string]$Folder) {
    $roots=New-Object 'System.Collections.Generic.List[string]'
    if ($Folder) {
        $p=[IO.Path]::GetFullPath($Folder.Trim().Trim('"'))
        Assert-NoReparse $p
        if ([IO.File]::Exists($p)) { $p=Split-Path $p -Parent }
        $roots.Add($p)
        $parent=Split-Path $p -Parent
        if ($parent) { $roots.Add($parent) }
        foreach ($base in @($p,$parent)) {
            if ($base -and [IO.Directory]::Exists($base)) {
                foreach ($child in @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue)) {
                    if (-not ($child.Attributes -band [IO.FileAttributes]::ReparsePoint)) { $roots.Add($child.FullName) }
                }
            }
        }
    }
    $resolved=@{}
    foreach ($d in $Definitions) {
        if ($ConfiguredPaths.ContainsKey($d.Id) -and $ConfiguredPaths[$d.Id]) {
            $single=Find-InstallLocations @($d) $ConfiguredPaths -SearchRoots @()
        } else {
            $probe=[pscustomobject]@{Id=$d.Id;Label=$d.Label}
            $single=Find-InstallLocations @($probe) @{} -SearchRoots @($roots.ToArray())
            if ($single[$d.Id].State -eq 'missing' -and -not $OnlyHint) {
                $single=Find-InstallLocations @($d) @{}
            }
        }
        $resolved[$d.Id]=$single[$d.Id]
    }
    return $resolved
}
function Show-FileStatus($Items,[hashtable]$Locations) {
    foreach ($d in $Items) {
        $root=$Locations[$d.Id].Path
        Write-Host ''
        Write-Host ('[{0}] {1}' -f $d.Label,$root) -ForegroundColor Cyan
        if ($d.Launcher) {
            Write-Host ('  {0}  resources/app.asar' -f (Get-ItemSummary $d $root))
            continue
        }
        $dataName=if ($d.Id -eq 'tw_game') { 'AzurPromilia_Data' } else { 'AzurPromiliaJP_Data' }
        $dataRoot=Install-Child $root $dataName
        $plan=$gamePlans[$d.Id]
        foreach ($e in $plan.files) {
            $state='无法读取'
            try {
                $file=Install-Child $dataRoot $e.relative_path
                if (-not [IO.File]::Exists($file)) { $state='缺少文件' }
                else {
                    $hash=Sha $file
                    if ($hash -eq $e.target_sha256) { $state='已汉化' }
                    elseif ($hash -eq $e.source_sha256) { $state='原版' }
                    else { $state='版本不匹配' }
                }
            } catch {}
            Write-Host ('  {0}  {1}' -f $state,$e.relative_path)
        }
        foreach ($e in $plan.readonly_files) {
            $state='无法读取'
            try {
                $file=Install-Child $dataRoot $e.relative_path
                if (-not [IO.File]::Exists($file)) { $state='缺少文件' }
                elseif ((Sha $file) -eq $e.sha256) { $state='原版（只读）' }
                else { $state='版本不匹配' }
            } catch {}
            Write-Host ('  {0}  {1}' -f $state,$e.relative_path)
        }
    }
}
function Test-MenuWritable([string]$Root) {
    $probe=Install-Child $Root ('.zhcn-write-test-'+[Guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($probe,'x'); [IO.File]::Delete($probe); return $true }
    catch { return $false }
    finally { if ([IO.File]::Exists($probe)) { [IO.File]::Delete($probe) } }
}
function Invoke-MenuOperation([string]$Operation,$Items,[hashtable]$Locations) {
    $needAdmin=$false
    foreach ($d in $Items) {
        $dir=$Locations[$d.Id].Path
        if ($d.Launcher) { $dir=Install-Child $dir 'resources' }
        if (-not (Test-MenuWritable $dir)) { $needAdmin=$true }
    }
    if ($needAdmin) {
        if ($Elevated) { throw '已使用管理员权限，仍无法写入目标目录。' }
        Write-Host '写入目标目录需要管理员权限，正在请求……' -ForegroundColor Yellow
        $dir=Child ('tools/logs/elevation-'+[Guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($dir) | Out-Null
        $paths=Join-Path $dir 'paths.json'
        $map=[ordered]@{}
        foreach ($d in $Items) { $map[$d.Id]=$Locations[$d.Id].Path }
        $map | ConvertTo-Json | Out-File -LiteralPath $paths -Encoding UTF8
        $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Action '+$Operation+' -Elevated -Quiet -PathsFile "'+$paths+'" -ModuleIds '+($Items.Id -join ',')
        $shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $process=Start-Process -FilePath $shell -Verb RunAs -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
        return $process.ExitCode
    }
    return (Run-Modules $Operation 'All' @($Items.Id) $Locations $true)
}
try {
    Assert-NoReparse $PackRoot
    . (Child 'tools/Locate-Installations.ps1')
    $launcherPlan=Get-Content -LiteralPath (Child 'tools/launcher-deployment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($d in $Definitions | Where-Object { $_.Launcher }) {
        $entry=@($launcherPlan.launchers | Where-Object { $_.id -eq $d.Id })
        if ($entry.Count -ne 1) { throw '启动器定位清单无效。' }
        $d | Add-Member -NotePropertyName AllowedHashes -NotePropertyValue (@($entry[0].source_sha256,$entry[0].target_sha256)+@($entry[0].previous_sha256))
    }
    if ($Action -ne 'Menu') {
        if ($ModuleIds.Count -eq 1 -and $ModuleIds[0].Contains(',')) { $ModuleIds=$ModuleIds[0].Split(',') }
        foreach ($id in $ModuleIds) { if ($id -notin @($Definitions.Id)) { throw ('无效模块：'+$id) } }
        exit (Run-Modules $Action $Target $ModuleIds $null $Quiet.IsPresent)
    }
    $gamePlans=@{}
    foreach ($id in @('tw_game','jp_game')) {
        $region=if ($id -eq 'tw_game') { 'tw' } else { 'jp' }
        $gamePlans[$id]=Get-Content -LiteralPath (Child ('tools/'+$region+'-deployment.json')) -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    Write-Host '=================================================='
    Write-Host '  蓝色星原：旅谣 简体汉化/尔安' -ForegroundColor Cyan
    Write-Host '  开服后若登录异常请还原文件，此脚本未进行反作弊验证' -ForegroundColor Red
    Write-Host '=================================================='
    Write-Host '正在查找游戏和启动器安装位置……'
    $configured=Read-ConfiguredPaths
    $menuLocations=Find-MenuLocations $configured $Hint
    $items=@($Definitions | Where-Object { $menuLocations[$_.Id].State -eq 'found' })
    while (-not $items.Count) {
        foreach ($d in $Definitions) {
            if ($menuLocations[$d.Id].State -in @('invalid','ambiguous')) { Write-Host ($d.Label+'：'+$menuLocations[$d.Id].Problem) -ForegroundColor Yellow }
        }
        Write-Host '没有自动找到游戏或启动器。' -ForegroundColor Yellow
        Write-Host '请输入安装文件夹路径（也可以把文件夹拖进本窗口），直接回车退出：'
        $folder=Read-Host '路径'
        if ([string]::IsNullOrWhiteSpace($folder)) { exit 0 }
        $menuLocations=Find-MenuLocations $configured $folder
        $items=@($Definitions | Where-Object { $menuLocations[$_.Id].State -eq 'found' })
    }
    Write-Host ''
    Write-Host '找到以下项目：'
    for ($i=0; $i -lt $items.Count; $i++) {
        $d=$items[$i]; $location=$menuLocations[$d.Id]
        Write-Host ('  {0}. [{1}] {2}   {3}' -f ($i+1),$d.Label,(Get-ItemSummary $d $location.Path),$location.Path)
    }
    foreach ($d in $Definitions | Where-Object { $menuLocations[$_.Id].State -ne 'found' }) {
        Write-Host ('     （未找到{0}）' -f $d.Label) -ForegroundColor DarkGray
        if ($menuLocations[$d.Id].State -in @('invalid','ambiguous')) { Write-Host ('     '+$menuLocations[$d.Id].Problem) -ForegroundColor Yellow }
    }
    Write-Host ''
    Write-Host '  1. 全部汉化'
    Write-Host '  2. 全部还原'
    Write-Host '  3. 选择项目汉化'
    Write-Host '  4. 选择项目还原'
    Write-Host '  5. 查看文件状态'
    Write-Host '  Q. 退出'
    $choice=([string](Read-Host '请输入选项并按回车')).Trim()
    $ids=@($items.Id)
    switch ($choice) {
        '1' { $op='Apply' }
        '2' { $op='Restore' }
        '3' { $op='Apply'; $ids=@(Parse-Select (Read-Host '请输入项目编号（多个用逗号分隔，例如 1,3）') $items) }
        '4' { $op='Restore'; $ids=@(Parse-Select (Read-Host '请输入项目编号（多个用逗号分隔，例如 1,3）') $items) }
        '5' { Show-FileStatus $items $menuLocations; exit 0 }
        default { exit 0 }
    }
    if (-not $ids.Count) { exit 0 }
    $selected=@($items | Where-Object { $_.Id -in $ids })
    $code=Invoke-MenuOperation $op $selected $menuLocations
    exit $code
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
