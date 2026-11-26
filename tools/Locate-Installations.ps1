# Read-only installation discovery. No game processes are started or stopped.
if (-not (Get-Command Assert-NoReparse -ErrorAction SilentlyContinue)) {
    . (Join-Path $PSScriptRoot 'Localization-Common.ps1')
}

function Test-InstallRoot([string]$Id, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not [IO.Path]::IsPathRooted($Path)) { return $false }
    Assert-NoReparse $Path
    switch ($Id) {
        'tw_game' { return ([IO.File]::Exists((Join-Path $Path 'AzurPromilia.exe')) -and [IO.Directory]::Exists((Join-Path $Path 'AzurPromilia_Data'))) }
        'jp_game' { return ([IO.File]::Exists((Join-Path $Path 'AzurPromiliaJP.exe')) -and [IO.Directory]::Exists((Join-Path $Path 'AzurPromiliaJP_Data'))) }
        'tw_launcher' { return ([IO.File]::Exists((Join-Path $Path 'launcher.exe')) -and [IO.File]::Exists((Join-Path $Path 'resources/app.asar'))) }
        'jp_launcher' { return ([IO.File]::Exists((Join-Path $Path 'AZUPRO_JP_Gamelauncher.exe')) -and [IO.File]::Exists((Join-Path $Path 'resources/app.asar'))) }
    }
    return $false
}

function Add-UniqueRoot([System.Collections.Generic.List[string]]$List, [System.Collections.Generic.HashSet[string]]$Seen, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    try {
        $p = [IO.Path]::GetFullPath($Path.Trim().Trim('"'))
        if ($p.StartsWith('\\')) { return }
        if ([IO.Directory]::Exists($p) -and $Seen.Add($p)) {
            $List.Add($p)
        }
    } catch {}
}

function Get-InstallSearchRoots {
    $roots = New-Object 'System.Collections.Generic.List[string]'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)

    foreach ($drive in [IO.DriveInfo]::GetDrives()) {
        if ($drive.IsReady -and $drive.DriveType -eq [IO.DriveType]::Fixed) {
            Add-UniqueRoot $roots $seen $drive.RootDirectory.FullName
        }
    }
    foreach ($p in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ($p -and [IO.Directory]::Exists($p)) {
            Add-UniqueRoot $roots $seen $p
            Add-UniqueRoot $roots $seen (Join-Path $p 'Programs')
        }
    }
    foreach ($name in @('AzurPromilia', 'AzurPromiliaJP', 'launcher', 'AZUPRO_JP_Gamelauncher')) {
        foreach ($proc in @([Diagnostics.Process]::GetProcessesByName($name))) {
            try {
                $image = Get-ProcessImagePathSafe $proc
                if ($image) {
                    $dir = Split-Path $image -Parent
                    Add-UniqueRoot $roots $seen $dir
                    $parent = Split-Path $dir -Parent
                    Add-UniqueRoot $roots $seen $parent
                }
            } catch {} finally { $proc.Dispose() }
        }
    }
    foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (-not (Test-Path -LiteralPath $key)) { continue }
        foreach ($item in @(Get-ChildItem -LiteralPath $key -ErrorAction SilentlyContinue)) {
            try {
                $record = Get-ItemProperty -LiteralPath $item.PSPath -ErrorAction Stop
                if ($record.DisplayName -match 'Azur.?Promilia|AZUPRO|蓝色星原|藍色星原|アズールプロミリア') {
                    if ($record.InstallLocation) { Add-UniqueRoot $roots $seen $record.InstallLocation }
                    if ($record.DisplayIcon -match '^"?([^",]+?\.exe)') {
                        Add-UniqueRoot $roots $seen (Split-Path $Matches[1] -Parent)
                    }
                }
            } catch {}
        }
    }

    # Read-only shortcut (.lnk) inspection on Desktop and Start Menu for custom install folders.
    $shortcutDirs = @(
        [Environment]::GetFolderPath('Desktop'),
        [Environment]::GetFolderPath('CommonDesktopDirectory'),
        [Environment]::GetFolderPath('Programs'),
        [Environment]::GetFolderPath('CommonPrograms')
    )
    $pattern = 'Azur.?Promilia|AZUPRO|蓝色星原|藍色星原|アズールプロミリア|YostarGames'
    $shell = $null
    try {
        $shell = New-Object -ComObject WScript.Shell
        foreach ($sd in $shortcutDirs) {
            if ([string]::IsNullOrWhiteSpace($sd) -or -not [IO.Directory]::Exists($sd)) { continue }
            foreach ($lnk in @(Get-ChildItem -LiteralPath $sd -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue)) {
                try {
                    if ($lnk.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
                    $sc = $shell.CreateShortcut($lnk.FullName)
                    $target = $sc.TargetPath
                    if ([string]::IsNullOrWhiteSpace($target)) { continue }
                    if ($lnk.Name -match $pattern -or $target -match $pattern) {
                        $tDir = if ([IO.File]::Exists($target)) { Split-Path $target -Parent } else { $target }
                        Add-UniqueRoot $roots $seen $tDir
                        if ($tDir) { Add-UniqueRoot $roots $seen (Split-Path $tDir -Parent) }
                    }
                } catch {}
            }
        }
    } catch {} finally {
        if ($shell) {
            try { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null } catch {}
        }
    }

    return @($roots.ToArray())
}

function Get-RelativeCandidates($Definition) {
    switch ($Definition.Id) {
        'tw_game' {
            return @('', 'AzurPromilia_TC_game', 'AzurPromilia_TC/AzurPromilia_TC_game', 'Games/AzurPromilia_TC/AzurPromilia_TC_game', 'Game/AzurPromilia_TC/AzurPromilia_TC_game', 'Games/AzurPromilia_TC_game', 'Game/AzurPromilia_TC_game')
        }
        'jp_game' {
            return @('', 'AZUPRO_JP', 'YostarGames/AZUPRO_JP', 'Games/YostarGames/AZUPRO_JP', 'Game/YostarGames/AZUPRO_JP')
        }
        default {
            $list = New-Object 'System.Collections.Generic.List[string]'
            $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
            foreach ($x in @('')) { if ($seen.Add($x)) { $list.Add($x) } }

            $version = if ($Definition.PSObject.Properties['Version']) { [string]$Definition.Version } else { '' }
            $subpaths = if ($Definition.PSObject.Properties['SearchSubpaths'] -and $Definition.SearchSubpaths) { @($Definition.SearchSubpaths) } else { @() }
            if (-not $subpaths.Count) {
                $subpaths = if ($Definition.Id -eq 'tw_launcher') { @('AzurPromilia_TC', 'Games/AzurPromilia_TC') } else { @('YostarGames/AZUPRO_JP_Gamelauncher', 'AZUPRO_JP_Gamelauncher', 'YostarGames') }
            }
            if ($version -and $seen.Add($version)) { $list.Add($version) }
            foreach ($sub in $subpaths) {
                $norm = ($sub -replace '\\', '/').Trim('/')
                if ($norm -and $seen.Add($norm)) { $list.Add($norm) }
                if ($norm -and $version) {
                    $withVer = "$norm/$version"
                    if ($seen.Add($withVer)) { $list.Add($withVer) }
                }
            }
            return @($list.ToArray())
        }
    }
}

function Find-InstallLocations($Definitions, [hashtable]$ConfiguredPaths, [string[]]$SearchRoots) {
    $needSearch = @($Definitions | Where-Object { -not $ConfiguredPaths.ContainsKey($_.Id) -or [string]::IsNullOrWhiteSpace($ConfiguredPaths[$_.Id]) })
    if ($needSearch.Count -and -not $PSBoundParameters.ContainsKey('SearchRoots')) {
        $SearchRoots = @(Get-InstallSearchRoots)
    }
    $result = @{}
    foreach ($d in $Definitions) {
        $configured = if ($ConfiguredPaths.ContainsKey($d.Id)) { $ConfiguredPaths[$d.Id] } else { '' }
        $matchesFound = New-Object 'System.Collections.Generic.List[string]'
        $seenMatches = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $problem = $null
        $allowedHashes = if ($d.PSObject.Properties['AllowedHashes']) { $d.AllowedHashes } else { $null }

        if (-not [string]::IsNullOrWhiteSpace($configured)) {
            try {
                $p = $configured.Trim().Trim('"')
                if (-not [IO.Path]::IsPathRooted($p)) { throw '请使用绝对路径。' }
                $p = [IO.Path]::GetFullPath($p).TrimEnd('\')
                if (-not (Test-InstallRoot $d.Id $p)) { throw '该目录缺少对应游戏或启动器文件。' }
                if ($seenMatches.Add($p)) { $matchesFound.Add($p) }
            } catch {
                $problem = '已配置目录无效：' + $_.Exception.Message
            }
        } else {
            $relList = Get-RelativeCandidates $d
            foreach ($base in $SearchRoots) {
                foreach ($rel in $relList) {
                    try {
                        $p = if ($rel) { Join-Path $base ($rel -replace '/', '\') } else { $base }
                        if (-not [IO.Directory]::Exists($p)) { continue }
                        $p = [IO.Path]::GetFullPath($p).TrimEnd('\')
                        if ($seenMatches.Contains($p)) { continue }
                        if (-not (Test-InstallRoot $d.Id $p)) { continue }
                        if ($d.Id.EndsWith('_launcher') -and $allowedHashes) {
                            $asarHash = Get-FileSha256 (Join-Path $p 'resources\app.asar')
                            if ($asarHash -notin $allowedHashes) { continue }
                        }
                        if ($seenMatches.Add($p)) { $matchesFound.Add($p) }
                    } catch {}
                }
            }
        }

        $found = @($matchesFound | Sort-Object)
        $path = ''
        $state = 'missing'
        if ($problem) { $state = 'invalid' }
        elseif ($found.Count -eq 1) { $state = 'found'; $path = $found[0] }
        elseif ($found.Count -gt 1) { $state = 'ambiguous'; $problem = '找到多个安装，请在安装路径.json 中指定：' + ($found -join '；') }
        else { $problem = '未找到，请在安装路径.json 中填写实际安装目录。' }
        $result[$d.Id] = [pscustomobject]@{
            Id         = $d.Id
            Label      = $d.Label
            State      = $state
            Path       = $path
            Candidates = $found
            Problem    = $problem
            Configured = (-not [string]::IsNullOrWhiteSpace($configured))
        }
    }
    return $result
}

function Show-InstallLocations([hashtable]$Locations, $Definitions) {
    Write-Host '安装目录（自动定位）' -ForegroundColor Cyan
    foreach ($d in $Definitions) {
        $item = $Locations[$d.Id]
        if ($item.State -eq 'found') { Write-Host ($d.Label + '：' + $item.Path) -ForegroundColor Green }
        else { Write-Host ($d.Label + '：' + $item.Problem) -ForegroundColor Yellow }
    }
    Write-Host ''
}
