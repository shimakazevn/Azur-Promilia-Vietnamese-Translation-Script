# Shared PowerShell 5.1 core helpers and C# native acceleration for Azur Promilia localization.

if (-not ('LocalizationCRC' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;

public static class LocalizationCRC {
    private static readonly uint[][] Tables = MakeTables();

    private static uint[][] MakeTables() {
        uint[][] t = new uint[8][];
        for (int s = 0; s < 8; s++) t[s] = new uint[256];
        for (uint i = 0; i < 256; i++) {
            uint c = i;
            for (int j = 0; j < 8; j++) c = (c >> 1) ^ ((c & 1) != 0 ? 0xEDB88320u : 0u);
            t[0][i] = c;
        }
        for (int s = 1; s < 8; s++) {
            for (int i = 0; i < 256; i++) {
                uint prev = t[s - 1][i];
                t[s][i] = (prev >> 8) ^ t[0][prev & 0xFFu];
            }
        }
        return t;
    }

    public static uint UpdateSlicing8(uint crc, byte[] buf, int offset, int count) {
        int end = offset + count;
        int p = offset;
        uint[][] t = Tables;
        while (p + 8 <= end) {
            uint lo = (uint)(buf[p] | (buf[p + 1] << 8) | (buf[p + 2] << 16) | (buf[p + 3] << 24));
            uint hi = (uint)(buf[p + 4] | (buf[p + 5] << 8) | (buf[p + 6] << 16) | (buf[p + 7] << 24));
            crc ^= lo;
            crc = t[7][crc & 0xFFu] ^
                  t[6][(crc >> 8) & 0xFFu] ^
                  t[5][(crc >> 16) & 0xFFu] ^
                  t[4][(crc >> 24) & 0xFFu] ^
                  t[3][hi & 0xFFu] ^
                  t[2][(hi >> 8) & 0xFFu] ^
                  t[1][(hi >> 16) & 0xFFu] ^
                  t[0][(hi >> 24) & 0xFFu];
            p += 8;
        }
        uint[] t0 = t[0];
        while (p < end) {
            crc = t0[(crc ^ buf[p]) & 0xFFu] ^ (crc >> 8);
            p++;
        }
        return crc;
    }

    public static uint Range(string path, long offset, long length) {
        using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1048576, FileOptions.SequentialScan)) {
            if (offset < 0 || length < 0 || offset > f.Length || length > f.Length - offset)
                throw new InvalidDataException("CRC range outside file");
            f.Position = offset;
            byte[] b = new byte[1048576];
            uint c = 0xFFFFFFFFu;
            while (length > 0) {
                int n = f.Read(b, 0, (int)Math.Min(b.Length, length));
                if (n == 0) throw new EndOfStreamException();
                c = UpdateSlicing8(c, b, 0, n);
                length -= n;
            }
            return c ^ 0xFFFFFFFFu;
        }
    }
}
'@
}

if (-not ('LocalizationNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

public static class LocalizationNative {
    private const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
    private static readonly uint[][] Tables = MakeTables();

    private static uint[][] MakeTables() {
        uint[][] t = new uint[8][];
        for (int s = 0; s < 8; s++) t[s] = new uint[256];
        for (uint i = 0; i < 256; i++) {
            uint c = i;
            for (int j = 0; j < 8; j++) c = (c >> 1) ^ ((c & 1) != 0 ? 0xEDB88320u : 0u);
            t[0][i] = c;
        }
        for (int s = 1; s < 8; s++) {
            for (int i = 0; i < 256; i++) {
                uint prev = t[s - 1][i];
                t[s][i] = (prev >> 8) ^ t[0][prev & 0xFFu];
            }
        }
        return t;
    }

    private static uint UpdateSlicing8(uint crc, byte[] buf, int offset, int count) {
        int end = offset + count;
        int p = offset;
        uint[][] t = Tables;
        while (p + 8 <= end) {
            uint lo = (uint)(buf[p] | (buf[p + 1] << 8) | (buf[p + 2] << 16) | (buf[p + 3] << 24));
            uint hi = (uint)(buf[p + 4] | (buf[p + 5] << 8) | (buf[p + 6] << 16) | (buf[p + 7] << 24));
            crc ^= lo;
            crc = t[7][crc & 0xFFu] ^
                  t[6][(crc >> 8) & 0xFFu] ^
                  t[5][(crc >> 16) & 0xFFu] ^
                  t[4][(crc >> 24) & 0xFFu] ^
                  t[3][hi & 0xFFu] ^
                  t[2][(hi >> 8) & 0xFFu] ^
                  t[1][(hi >> 16) & 0xFFu] ^
                  t[0][(hi >> 24) & 0xFFu];
            p += 8;
        }
        uint[] t0 = t[0];
        while (p < end) {
            crc = t0[(crc ^ buf[p]) & 0xFFu] ^ (crc >> 8);
            p++;
        }
        return crc;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool QueryFullProcessImageNameW(IntPtr hProcess, int dwFlags, StringBuilder lpExeName, ref int lpdwSize);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    public static string TryGetProcessImagePath(int pid) {
        IntPtr h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
        if (h == IntPtr.Zero) return null;
        try {
            int cap = 1024;
            StringBuilder sb = new StringBuilder(cap);
            if (QueryFullProcessImageNameW(h, 0, sb, ref cap)) {
                return sb.ToString();
            }
            return null;
        } finally {
            CloseHandle(h);
        }
    }

    private static string BytesToLowerHex(byte[] bytes) {
        char[] c = new char[bytes.Length * 2];
        const string hex = "0123456789abcdef";
        for (int i = 0; i < bytes.Length; i++) {
            int b = bytes[i];
            c[i * 2] = hex[b >> 4];
            c[i * 2 + 1] = hex[b & 0x0F];
        }
        return new string(c);
    }

    public static string ComputeSha256(string path) {
        using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1048576, FileOptions.SequentialScan))
        using (SHA256 sha = SHA256.Create()) {
            byte[] buf = new byte[1048576];
            int n;
            while ((n = f.Read(buf, 0, buf.Length)) > 0) {
                sha.TransformBlock(buf, 0, n, null, 0);
            }
            sha.TransformFinalBlock(new byte[0], 0, 0);
            return BytesToLowerHex(sha.Hash);
        }
    }

    public static void VerifyFile(
        string path,
        long expectedSize,
        string expectedSha256,
        bool checkCrc,
        uint expectedFullCrc,
        long[] segOffsets,
        long[] segSizes,
        uint[] segCrcs,
        int[] segIds
    ) {
        if (!File.Exists(path)) {
            throw new FileNotFoundException("文件缺失：" + path);
        }
        using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1048576, FileOptions.SequentialScan)) {
            if (f.Length != expectedSize) {
                throw new InvalidDataException("文件大小不匹配：" + path);
            }

            int segCount = 0;
            int[] order = null;
            uint[] segStates = null;

            if (checkCrc && segOffsets != null && segOffsets.Length > 0) {
                segCount = segOffsets.Length;
                if (segSizes == null || segCrcs == null || segIds == null ||
                    segSizes.Length != segCount || segCrcs.Length != segCount || segIds.Length != segCount) {
                    throw new ArgumentException("Segment array lengths mismatch");
                }
                order = new int[segCount];
                segStates = new uint[segCount];
                for (int i = 0; i < segCount; i++) {
                    if (segOffsets[i] < 0 || segSizes[i] < 0 || segOffsets[i] > expectedSize || segSizes[i] > expectedSize - segOffsets[i]) {
                        throw new InvalidDataException("CRC range outside file");
                    }
                    order[i] = i;
                    segStates[i] = 0xFFFFFFFFu;
                }
                Array.Sort(order, (a, b) => segOffsets[a].CompareTo(segOffsets[b]));
            }

            using (SHA256 sha = SHA256.Create()) {
                byte[] buf = new byte[1048576];
                uint fullCrc = 0xFFFFFFFFu;
                long pos = 0;
                int nextSeg = 0;
                List<int> active = checkCrc && segCount > 0 ? new List<int>() : null;

                int n;
                while ((n = f.Read(buf, 0, buf.Length)) > 0) {
                    sha.TransformBlock(buf, 0, n, null, 0);
                    if (checkCrc) {
                        fullCrc = UpdateSlicing8(fullCrc, buf, 0, n);
                        if (active != null) {
                            long chunkEnd = pos + n;
                            while (nextSeg < segCount) {
                                int idx = order[nextSeg];
                                if (segOffsets[idx] >= chunkEnd) break;
                                if (segSizes[idx] > 0) active.Add(idx);
                                nextSeg++;
                            }
                            for (int a = active.Count - 1; a >= 0; a--) {
                                int idx = active[a];
                                long segStart = segOffsets[idx];
                                long segEnd = segStart + segSizes[idx];
                                long overlapStart = pos > segStart ? pos : segStart;
                                long overlapEnd = chunkEnd < segEnd ? chunkEnd : segEnd;
                                if (overlapEnd > overlapStart) {
                                    segStates[idx] = UpdateSlicing8(
                                        segStates[idx],
                                        buf,
                                        (int)(overlapStart - pos),
                                        (int)(overlapEnd - overlapStart)
                                    );
                                }
                                if (overlapEnd >= segEnd) {
                                    active.RemoveAt(a);
                                }
                            }
                        }
                    }
                    pos += n;
                }

                sha.TransformFinalBlock(new byte[0], 0, 0);
                string actualSha = BytesToLowerHex(sha.Hash);
                if (!string.Equals(actualSha, expectedSha256, StringComparison.OrdinalIgnoreCase)) {
                    throw new InvalidDataException("SHA256 不匹配：" + path);
                }

                if (checkCrc) {
                    if ((fullCrc ^ 0xFFFFFFFFu) != expectedFullCrc) {
                        throw new InvalidDataException("整包 CRC 不匹配：" + path);
                    }
                    for (int i = 0; i < segCount; i++) {
                        if ((segStates[i] ^ 0xFFFFFFFFu) != segCrcs[i]) {
                            throw new InvalidDataException("段 CRC 不匹配：" + path + "，段 " + segIds[i]);
                        }
                    }
                }
            }
        }
    }
}
'@
}

function Assert-NoReparse([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw '路径不能为空。' }
    $current = [IO.Path]::GetFullPath($Path)
    if ($current.StartsWith('\\')) { throw "拒绝网络路径：$current" }
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "拒绝重解析点路径：$current"
            }
        }
        $parent = Split-Path $current -Parent
        if ([string]::IsNullOrEmpty($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
}

function Resolve-SafeChild([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':')) {
        throw "非法相对路径：$Relative"
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $full = [IO.Path]::GetFullPath([IO.Path]::Combine($base, ($Relative -replace '/', '\')))
    if (-not $full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "路径越界：$Relative"
    }
    Assert-NoReparse $full
    return $full
}

function Get-FileSha256([string]$Path) {
    Assert-NoReparse $Path
    return [LocalizationNative]::ComputeSha256($Path)
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $dir = Split-Path $Path -Parent
    if ($dir -and -not [IO.Directory]::Exists($dir)) {
        [IO.Directory]::CreateDirectory($dir) | Out-Null
    }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $enc)
}

function Assert-FreeDiskSpace([string]$TargetDir, [long]$RequiredBytes) {
    if ($RequiredBytes -le 0) { return }
    $full = [IO.Path]::GetFullPath($TargetDir)
    $root = [IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrEmpty($root) -or $root.StartsWith('\\')) { return }
    $drive = New-Object System.IO.DriveInfo($root)
    $headroom = [long]67108864 # 64 MB safety headroom
    $needed = $RequiredBytes + $headroom
    if ($drive.AvailableFreeSpace -lt $needed) {
        $needMb = [Math]::Ceiling($needed / 1MB)
        $availMb = [Math]::Floor($drive.AvailableFreeSpace / 1MB)
        throw ("目标磁盘剩余空间不足（$($drive.Name)）：需要约 $needMb MB，当前仅剩 $availMb MB。")
    }
}

function Get-ProcessImagePathSafe([Diagnostics.Process]$Process) {
    $image = [LocalizationNative]::TryGetProcessImagePath($Process.Id)
    if (-not [string]::IsNullOrWhiteSpace($image)) { return $image }
    try {
        return $Process.MainModule.FileName
    } catch {
        return $null
    }
}

function Assert-ProcessesStopped(
    [string[]]$ProcessNames,
    [string[]]$PathScopes,
    [string]$FriendlyError,
    [string[]]$AlwaysRefuseNames = @()
) {
    $normalizedScopes = New-Object 'System.Collections.Generic.List[string]'
    foreach ($s in $PathScopes) {
        if ([string]::IsNullOrWhiteSpace($s)) { continue }
        $fullScope = [IO.Path]::GetFullPath($s).TrimEnd('\')
        $rootOnly = [IO.Path]::GetPathRoot($fullScope).TrimEnd('\')
        # Never treat a bare drive root like D:\ as a wildcard process scope.
        if ([string]::Equals($fullScope, $rootOnly, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $normalizedScopes.Add($fullScope + '\')
    }

    foreach ($name in $ProcessNames) {
        $isAlwaysRefuse = ($AlwaysRefuseNames -contains $name)
        foreach ($proc in @([Diagnostics.Process]::GetProcessesByName($name))) {
            try {
                try {
                    if ($proc.HasExited) { continue }
                } catch {}

                $image = Get-ProcessImagePathSafe $proc
                if ([string]::IsNullOrWhiteSpace($image)) {
                    $stillAlive = $true
                    try {
                        $check = [Diagnostics.Process]::GetProcessById($proc.Id)
                        $check.Dispose()
                    } catch {
                        $stillAlive = $false
                    }
                    if (-not $stillAlive) { continue }
                    if ($isAlwaysRefuse) {
                        throw "$FriendlyError（无法读取进程路径：$name.exe，PID $($proc.Id)）"
                    }
                    Write-Warning "检测到同名进程 $name.exe (PID $($proc.Id)) 但无法读取其路径，将继续执行；若文件被占用将自动回滚。"
                    continue
                }

                $fullImage = [IO.Path]::GetFullPath($image)
                foreach ($scope in $normalizedScopes) {
                    if ($fullImage.StartsWith($scope, [StringComparison]::OrdinalIgnoreCase)) {
                        throw "$FriendlyError（$name.exe，PID $($proc.Id)）"
                    }
                }
            } finally {
                $proc.Dispose()
            }
        }
    }
}

function Assert-AllowedGameRelative([string]$Relative) {
    if ($Relative -eq 'resources.assets') { return }
    if ($Relative -notmatch '^(?:\.res/(?:raw_base_package|raw_streaming_package|default_package)/BundleFiles|StreamingAssets/\.res/(?:default_package|static_package))/[a-z0-9]+\.r$') {
        throw "不允许写入：$Relative"
    }
}

function Assert-GameResource([string]$Path, $Entry, [bool]$Patched) {
    $expected = if ($Patched) { $Entry.target_sha256 } else { $Entry.source_sha256 }
    $checkCrc = $Entry.relative_path.EndsWith('.r')
    $fullCrc = [uint32]0
    $segOffsets = $null
    $segSizes = $null
    $segCrcs = $null
    $segIds = $null

    if ($checkCrc) {
        $fullCrc = [uint32]$Entry.crc32
        $segs = @($Entry.segments)
        $segOffsets = New-Object 'long[]' $segs.Count
        $segSizes = New-Object 'long[]' $segs.Count
        $segCrcs = New-Object 'uint32[]' $segs.Count
        $segIds = New-Object 'int[]' $segs.Count
        for ($i = 0; $i -lt $segs.Count; $i++) {
            $segOffsets[$i] = [long]$segs[$i].offset
            $segSizes[$i] = [long]$segs[$i].size
            $segCrcs[$i] = [uint32]$segs[$i].crc32
            $segIds[$i] = [int]$segs[$i].bundle_index
        }
    }

    [LocalizationNative]::VerifyFile(
        $Path,
        [long]$Entry.size,
        [string]$expected,
        $checkCrc,
        $fullCrc,
        $segOffsets,
        $segSizes,
        $segCrcs,
        $segIds
    )
}

function Replace-FileVerified([string]$Source, [string]$Target, [string]$ExpectedSha) {
    $temp = $Target + '.crc-zhcn-stage-' + [Guid]::NewGuid().ToString('N')
    try {
        [IO.File]::Copy($Source, $temp, $false)
        if ((Get-FileSha256 $temp) -ne $ExpectedSha) {
            throw "暂存文件校验失败：$Target"
        }
        [IO.File]::Replace($temp, $Target, [System.Management.Automation.Language.NullString]::Value)
    } finally {
        if ([IO.File]::Exists($temp)) {
            try { [IO.File]::Delete($temp) } catch {}
        }
    }
}

function Invoke-GameCRCZH {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Config,
        [Parameter(Mandatory = $true)][string]$Action,
        [string]$Hint = '',
        [bool]$HintExplicit = $false,
        [string]$ToolsDir,
        [string]$PackRoot
    )

    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}

    $planPath = Join-Path $ToolsDir $Config.DeploymentFile
    if (-not [IO.File]::Exists($planPath) -and $Config.FallbackDeploymentFile) {
        $fallbackPlan = Join-Path $ToolsDir $Config.FallbackDeploymentFile
        if ([IO.File]::Exists($fallbackPlan)) { $planPath = $fallbackPlan }
    }
    Assert-NoReparse $planPath
    $plan = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json

    if ($plan.region -ne $Config.Region) {
        throw "部署清单区域必须为 $($Config.Region)。"
    }

    $seen = New-Object 'System.Collections.Hashtable' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($e in $plan.files) {
        Assert-AllowedGameRelative $e.relative_path
        if ($seen.ContainsKey($e.relative_path)) { throw "重复资源路径：$($e.relative_path)" }
        $seen[$e.relative_path] = $true
    }
    foreach ($g in $plan.readonly_files) {
        if ($seen.ContainsKey($g.relative_path)) { throw "只读路径与资源重叠或重复：$($g.relative_path)" }
        $seen[$g.relative_path] = $true
    }

    if ($Action -eq 'ValidatePayload') {
        $payloadRoot = Join-Path $PackRoot $Config.PayloadSubdir
        if (-not [IO.Directory]::Exists($payloadRoot)) {
            throw "补丁载荷目录不存在：$payloadRoot（请下载 Releases 完整包，勿直接下载源码 ZIP）"
        }
        foreach ($e in $plan.files) {
            Assert-GameResource (Resolve-SafeChild $payloadRoot $e.relative_path) $e $true
            Write-Host ('载荷通过：' + $e.relative_path)
        }
        Write-Host '全部载荷通过：大小、SHA256、整包 CRC、全部段 CRC。' -ForegroundColor Green
        return 0
    }

    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if ($HintExplicit) {
        if ([string]::IsNullOrWhiteSpace($Hint)) { throw '显式 Hint 不得为空。' }
        $h = [IO.Path]::GetFullPath($Hint.Trim().Trim('"'))
        if ([IO.File]::Exists($h)) { $h = Split-Path $h -Parent }
        $candidates.Add($h)
        if ((Split-Path $h -Leaf) -eq $Config.DataDirName) { $candidates.Add((Split-Path $h -Parent)) }
        foreach ($rel in $Config.HintRelatives) {
            $candidates.Add((Join-Path $h $rel))
        }
    } else {
        foreach ($drive in [IO.DriveInfo]::GetDrives()) {
            if (-not $drive.IsReady -or $drive.DriveType -ne [IO.DriveType]::Fixed) { continue }
            foreach ($rel in $Config.SearchRelatives) {
                $candidates.Add((Join-Path $drive.RootDirectory.FullName $rel))
            }
        }
    }

    $root = $null
    foreach ($c in $candidates) {
        try {
            if ([IO.File]::Exists((Join-Path $c $Config.ExeName)) -and [IO.Directory]::Exists((Join-Path $c $Config.DataDirName))) {
                $root = [IO.Path]::GetFullPath($c)
                break
            }
        } catch {}
    }
    if (-not $root) { throw $Config.NotFoundMsg }

    Assert-NoReparse $root
    $data = Join-Path $root $Config.DataDirName
    Assert-NoReparse $data
    $backup = Join-Path $root $Config.BackupDirName

    if ($Action -eq 'Menu') {
        Write-Host "$($Config.MenuTitle)`n$root"
        Write-Host '1 汉化   2 还原   3 完整校验   其他退出'
        switch ((Read-Host '选择').Trim()) {
            '1' { $Action = 'Apply' }
            '2' { $Action = 'Restore' }
            '3' { $Action = 'Verify' }
            default { return 0 }
        }
    }

    $assertGuards = {
        foreach ($g in $plan.readonly_files) {
            $gp = Resolve-SafeChild $data $g.relative_path
            if (-not [IO.File]::Exists($gp) -or (Get-FileSha256 $gp) -ne $g.sha256) {
                throw "原版只读基线不匹配：$($g.relative_path)"
            }
        }
    }

    & $assertGuards

    if ($Action -eq 'Verify') {
        foreach ($e in $plan.files) {
            $p = Resolve-SafeChild $data $e.relative_path
            if (-not [IO.File]::Exists($p)) { throw "文件缺失：$($e.relative_path)" }
            $hash = Get-FileSha256 $p
            if ($hash -eq $e.target_sha256) { Assert-GameResource $p $e $true; $state = '汉化' }
            elseif ($hash -eq $e.source_sha256) { Assert-GameResource $p $e $false; $state = '原版' }
            else { throw "文件既非原版也非本版汉化：$($e.relative_path)" }
            Write-Host ("通过 [$state] " + $e.relative_path)
        }
        Write-Host '完整校验通过，所有只读基线保持原字节。' -ForegroundColor Green
        return 0
    }

    $parentDir = Split-Path $root -Parent
    $launcherScopes = @($root)
    $parentRoot = if ($parentDir) { [IO.Path]::GetPathRoot($parentDir).TrimEnd('\') } else { '' }
    if ($parentDir -and -not [string]::Equals($parentDir.TrimEnd('\'), $parentRoot, [StringComparison]::OrdinalIgnoreCase)) {
        $launcherScopes += $parentDir
    } elseif ($parentDir -and $Config.LauncherSiblingDirs) {
        foreach ($sib in $Config.LauncherSiblingDirs) {
            $launcherScopes += (Join-Path $parentDir $sib)
        }
    }

    $launcherAlwaysRefuse = if ($Config.LauncherProcName -ne 'launcher') { @($Config.LauncherProcName) } else { @() }
    $assertAllStopped = {
        Assert-ProcessesStopped -ProcessNames @($Config.GameProcName, 'sdkbrowser') -PathScopes @($root) -FriendlyError '请先完全退出游戏和登录窗口' -AlwaysRefuseNames @($Config.GameProcName)
        Assert-ProcessesStopped -ProcessNames @($Config.LauncherProcName) -PathScopes $launcherScopes -FriendlyError "请先完全退出关联启动器：$($Config.LauncherProcName).exe" -AlwaysRefuseNames $launcherAlwaysRefuse
    }

    & $assertAllStopped

    $payloadRoot = if ($Action -eq 'Apply') { Join-Path $PackRoot $Config.PayloadSubdir } else { $null }
    if ($Action -eq 'Apply' -and -not [IO.Directory]::Exists($payloadRoot)) {
        throw "补丁载荷目录不存在：$payloadRoot（请下载 Releases 完整包，勿直接下载源码 ZIP）"
    }

    $todo = New-Object 'System.Collections.Generic.List[object]'
    $needBackupBytes = [long]0
    $maxSingleStageBytes = [long]0
    $needSnapBytes = [long]0

    foreach ($e in $plan.files) {
        $p = Resolve-SafeChild $data $e.relative_path
        if (-not [IO.File]::Exists($p)) { throw "游戏文件缺失：$($e.relative_path)" }
        $h = Get-FileSha256 $p
        if ($h -ne $e.source_sha256 -and $h -ne $e.target_sha256) {
            throw "文件版本不匹配：$($e.relative_path)"
        }
        $bk = Resolve-SafeChild $backup $e.relative_path
        $needsNewBackup = $false
        if ($Action -eq 'Apply') {
            $src = Resolve-SafeChild $payloadRoot $e.relative_path
            Assert-GameResource $src $e $true
            if (-not [IO.File]::Exists($bk)) {
                if ($h -ne $e.source_sha256) { throw "缺少原版备份：$($e.relative_path)" }
                $needsNewBackup = $true
                $needBackupBytes += [long]$e.size
            } else {
                if ((Get-FileSha256 $bk) -ne $e.source_sha256) { throw "原版备份不匹配：$bk" }
            }
            if ($h -eq $e.target_sha256) { continue }
            $exp = $e.target_sha256
        } else {
            if ($h -eq $e.source_sha256) { continue }
            Assert-GameResource $bk $e $false
            $src = $bk
            $exp = $e.source_sha256
        }

        if ([long]$e.size -gt $maxSingleStageBytes) { $maxSingleStageBytes = [long]$e.size }
        $reuseBackupAsSnap = ($Action -eq 'Apply' -and $h -eq $e.source_sha256)
        if (-not $reuseBackupAsSnap) { $needSnapBytes += [long]$e.size }
        $todo.Add([PSCustomObject]@{
            Entry = $e
            Target = $p
            Source = $src
            Expected = $exp
            Before = $h
            Backup = $bk
            NeedsNewBackup = $needsNewBackup
            ReuseBackupAsSnap = $reuseBackupAsSnap
            Snap = $null
        })
    }

    if ($todo.Count -eq 0) {
        Write-Host '所有文件均已处于目标状态，无需修改。' -ForegroundColor Green
        return 0
    }

    Assert-FreeDiskSpace $root ($needBackupBytes + $needSnapBytes + $maxSingleStageBytes)

    # Clean up any leftover staging files on target paths before beginning.
    foreach ($w in $todo) {
        $tDir = Split-Path $w.Target -Parent
        $tLeaf = Split-Path $w.Target -Leaf
        foreach ($stale in @(Get-ChildItem -LiteralPath $tDir -Filter ($tLeaf + '.crc-zhcn-stage-*') -Force -ErrorAction SilentlyContinue)) {
            if (-not ($stale.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                try { [IO.File]::Delete($stale.FullName) } catch {}
            }
        }
    }

    # Create verified original backups only for entries being touched (or missing backups).
    foreach ($w in $todo) {
        if ($w.NeedsNewBackup) {
            [IO.Directory]::CreateDirectory((Split-Path $w.Backup -Parent)) | Out-Null
            [IO.File]::Copy($w.Target, $w.Backup, $false)
            if ((Get-FileSha256 $w.Backup) -ne $w.Entry.source_sha256) {
                throw "原版备份校验失败：$($w.Backup)"
            }
        }
    }

    $txParent = Join-Path $backup 'transactions'
    $snapdir = $null
    $preserveSnap = $false
    foreach ($w in $todo) {
        if ($w.ReuseBackupAsSnap) {
            $w.Snap = $w.Backup
        } else {
            if (-not $snapdir) {
                $snapdir = Join-Path $txParent ([Guid]::NewGuid().ToString('N'))
            }
            $sp = Resolve-SafeChild $snapdir $w.Entry.relative_path
            [IO.Directory]::CreateDirectory((Split-Path $sp -Parent)) | Out-Null
            [IO.File]::Copy($w.Target, $sp, $false)
            if ((Get-FileSha256 $sp) -ne $w.Before) { throw '操作前快照验证失败。' }
            $w.Snap = $sp
        }
    }

    $done = New-Object 'System.Collections.Generic.List[object]'
    try {
        try {
            & $assertAllStopped
            & $assertGuards
            foreach ($w in $todo) {
                if ((Get-FileSha256 $w.Target) -ne $w.Before) { throw '操作期间目标文件发生变化。' }
                Replace-FileVerified $w.Source $w.Target $w.Expected
                $done.Add($w)
                Assert-GameResource $w.Target $w.Entry ($Action -eq 'Apply')
                Write-Host ('已写入并校验：' + $w.Entry.relative_path)
            }
            & $assertGuards
        } catch {
            $reason = $_.Exception.Message
            $rollbackErrors = New-Object 'System.Collections.Generic.List[string]'
            for ($i = $done.Count - 1; $i -ge 0; $i--) {
                $w = $done[$i]
                try {
                    if ((Get-FileSha256 $w.Target) -ne $w.Before) {
                        Replace-FileVerified $w.Snap $w.Target $w.Before
                    }
                    if ((Get-FileSha256 $w.Target) -ne $w.Before) {
                        throw '回滚后哈希不匹配'
                    }
                } catch {
                    $rollbackErrors.Add(($w.Target + ': ' + $_.Exception.Message))
                }
            }
            if ($rollbackErrors.Count -gt 0) {
                $preserveSnap = $true
                $snapHint = if ($snapdir) { "（恢复快照位于：$snapdir）" } else { '' }
                throw ("操作失败：$reason；以下文件回滚失败，请保留原版备份与事务快照并手工恢复${snapHint}：" + ($rollbackErrors -join '；'))
            }
            throw "已回滚到操作前：$reason"
        }
    } finally {
        if (-not $preserveSnap -and $snapdir -and [IO.Directory]::Exists($snapdir)) {
            try {
                [IO.Directory]::Delete($snapdir, $true)
                if ([IO.Directory]::Exists($txParent) -and @(Get-ChildItem -LiteralPath $txParent -Force -ErrorAction SilentlyContinue).Count -eq 0) {
                    [IO.Directory]::Delete($txParent, $false)
                }
            } catch {}
        }
    }

    Write-Host "$Action 完成。资源大小、段 CRC、整包 CRC 和只读基线均通过。" -ForegroundColor Green
    return 0
}
