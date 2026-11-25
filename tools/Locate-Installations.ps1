# Read-only installation discovery. No game processes are started or stopped.
function Test-InstallRoot([string]$Id,[string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { return $false }
    Assert-NoReparse $Path
    switch ($Id) {
        'tw_game' { return ([IO.File]::Exists((Join-Path $Path 'AzurPromilia.exe')) -and [IO.Directory]::Exists((Join-Path $Path 'AzurPromilia_Data'))) }
        'jp_game' { return ([IO.File]::Exists((Join-Path $Path 'AzurPromiliaJP.exe')) -and [IO.Directory]::Exists((Join-Path $Path 'AzurPromiliaJP_Data'))) }
        'tw_launcher' { return ([IO.File]::Exists((Join-Path $Path 'launcher.exe')) -and [IO.File]::Exists((Join-Path $Path 'resources/app.asar'))) }
        'jp_launcher' { return ([IO.File]::Exists((Join-Path $Path 'AZUPRO_JP_Gamelauncher.exe')) -and [IO.File]::Exists((Join-Path $Path 'resources/app.asar'))) }
    }
    return $false
}
function Get-InstallSearchRoots {
    $roots=New-Object 'System.Collections.Generic.List[string]'
    foreach ($drive in [IO.DriveInfo]::GetDrives()) {
        if ($drive.IsReady -and $drive.DriveType -eq [IO.DriveType]::Fixed) { $roots.Add($drive.RootDirectory.FullName) }
    }
    foreach ($p in @($env:ProgramFiles,${env:ProgramFiles(x86)},$env:LOCALAPPDATA)) {
        if ($p -and [IO.Directory]::Exists($p)) { $roots.Add($p); $roots.Add((Join-Path $p 'Programs')) }
    }
    foreach ($name in @('AzurPromilia','AzurPromiliaJP','launcher','AZUPRO_JP_Gamelauncher')) {
        foreach ($proc in [Diagnostics.Process]::GetProcessesByName($name)) {
            try {
                $image=$proc.MainModule.FileName
                if ($image) {
                    $dir=Split-Path $image -Parent
                    $roots.Add($dir)
                    $parent=Split-Path $dir -Parent
                    if ($parent) { $roots.Add($parent) }
                }
            } catch {} finally { $proc.Dispose() }
        }
    }
    foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (-not (Test-Path -LiteralPath $key)) { continue }
        foreach ($item in @(Get-ChildItem -LiteralPath $key -ErrorAction SilentlyContinue)) {
            try {
                $record=Get-ItemProperty -LiteralPath $item.PSPath -ErrorAction Stop
                if ($record.DisplayName -match 'Azur.?Promilia|AZUPRO|蓝色星原|藍色星原|アズールプロミリア') {
                    if ($record.InstallLocation -and [IO.Directory]::Exists($record.InstallLocation)) { $roots.Add($record.InstallLocation) }
                    if ($record.DisplayIcon -match '^"?([^",]+?\.exe)') {
                        $iconRoot=Split-Path $Matches[1] -Parent
                        if ($iconRoot -and [IO.Directory]::Exists($iconRoot)) { $roots.Add($iconRoot) }
                    }
                }
            } catch {}
        }
    }
    return @($roots | Select-Object -Unique)
}
function Find-InstallLocations($Definitions,[hashtable]$ConfiguredPaths,[string[]]$SearchRoots) {
    $relative=@{
        tw_game=@('','AzurPromilia_TC_game','AzurPromilia_TC/AzurPromilia_TC_game','Games/AzurPromilia_TC/AzurPromilia_TC_game','Games/AzurPromilia_TC_game')
        jp_game=@('','AZUPRO_JP','YostarGames/AZUPRO_JP','Games/YostarGames/AZUPRO_JP')
        tw_launcher=@('','1.0.1.4','AzurPromilia_TC/1.0.1.4','Games/AzurPromilia_TC/1.0.1.4')
        jp_launcher=@('','AZUPRO_JP_Gamelauncher','YostarGames/AZUPRO_JP_Gamelauncher','Games/YostarGames/AZUPRO_JP_Gamelauncher')
    }
    $needSearch=@($Definitions | Where-Object { -not $ConfiguredPaths.ContainsKey($_.Id) -or [string]::IsNullOrWhiteSpace($ConfiguredPaths[$_.Id]) })
    if ($needSearch.Count -and -not $PSBoundParameters.ContainsKey('SearchRoots')) { $SearchRoots=@(Get-InstallSearchRoots) }
    $result=@{}
    foreach ($d in $Definitions) {
        $configured=if ($ConfiguredPaths.ContainsKey($d.Id)) { $ConfiguredPaths[$d.Id] } else { '' }
        $matchesFound=New-Object 'System.Collections.Generic.List[string]'
        $problem=$null
        if (-not [string]::IsNullOrWhiteSpace($configured)) {
            try {
                $p=$configured.Trim().Trim('"')
                if (-not [IO.Path]::IsPathRooted($p)) { throw '请使用绝对路径。' }
                $p=[IO.Path]::GetFullPath($p).TrimEnd('\')
                if (-not (Test-InstallRoot $d.Id $p)) { throw '该目录缺少对应游戏或启动器文件。' }
                $matchesFound.Add($p)
            } catch { $problem='已配置目录无效：'+$_.Exception.Message }
        } else {
            foreach ($base in $SearchRoots) {
                foreach ($rel in $relative[$d.Id]) {
                    try {
                        $p=if ($rel) { Join-Path $base $rel } else { $base }
                        if (-not [IO.Directory]::Exists($p)) { continue }
                        $p=[IO.Path]::GetFullPath($p).TrimEnd('\')
                        if (-not (Test-InstallRoot $d.Id $p)) { continue }
                        if ($d.Id.EndsWith('_launcher') -and $d.AllowedHashes -and (Sha (Join-Path $p 'resources/app.asar')) -notin $d.AllowedHashes) { continue }
                        if (-not $matchesFound.Contains($p)) { $matchesFound.Add($p) }
                    } catch {}
                }
            }
        }
        $found=@($matchesFound | Sort-Object -Unique)
        $path=''; $state='missing'
        if ($problem) { $state='invalid' }
        elseif ($found.Count -eq 1) { $state='found'; $path=$found[0] }
        elseif ($found.Count -gt 1) { $state='ambiguous'; $problem='找到多个安装，请在安装路径.json 中指定：'+($found -join '；') }
        else { $problem='未找到，请在安装路径.json 中填写实际安装目录。' }
        $result[$d.Id]=[pscustomobject]@{Id=$d.Id;Label=$d.Label;State=$state;Path=$path;Candidates=$found;Problem=$problem;Configured=(-not [string]::IsNullOrWhiteSpace($configured))}
    }
    return $result
}
function Show-InstallLocations([hashtable]$Locations,$Definitions) {
    Write-Host '安装目录（自动定位）' -ForegroundColor Cyan
    foreach ($d in $Definitions) {
        $item=$Locations[$d.Id]
        if ($item.State -eq 'found') { Write-Host ($d.Label+'：'+$item.Path) -ForegroundColor Green }
        else { Write-Host ($d.Label+'：'+$item.Problem) -ForegroundColor Yellow }
    }
    Write-Host ''
}
