using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: AssemblyTitle("Azur Promilia VI Installer & Auto-Updater")]
[assembly: AssemblyDescription("Bo cai dat & tu dong cap nhat Viet hoa Azur Promilia (JP)")]
[assembly: AssemblyCompany("shimakazevn")]
[assembly: AssemblyProduct("AzurPromilia-VI-Setup")]
[assembly: AssemblyVersion("1.0.2.0")]
[assembly: AssemblyFileVersion("1.0.2.0")]

namespace AzurPromiliaVIInstaller
{
    internal static class Config
    {
        public const string RepoSlug = "shimakazevn/Azur-Promilia-Vietnamese-Translation-Script";
        public const string LatestJsonUrl = "https://raw.githubusercontent.com/" + RepoSlug + "/main/latest-vi.json";
        public const string ReleasesApiUrl = "https://api.github.com/repos/" + RepoSlug + "/releases/latest";
        public const string CurrentInstallerVersion = "v1.0.2";
        public static readonly string AppDataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AzurPromiliaVI"
        );
        public static readonly string StatePath = Path.Combine(AppDataDir, "state.json");
        public static readonly string CacheRoot = Path.Combine(AppDataDir, "cache");
    }

    internal class InstallerState
    {
        public string installed_version = "";
        public string jp_game_path = "";
        public string jp_launcher_path = "";
        public bool auto_update_on_launch = true;
        public string last_checked_utc = "";
    }

    internal class RemoteRelease
    {
        public string version = "";
        public string published_at = "";
        public string jp_resource_version = "";
        public string jp_launcher_version = "";
        public string full_zip_name = "";
        public string full_zip_url = "";
        public string full_zip_sha256 = "";
        public long full_zip_size = 0;
        public string installer_url = "";
        public string installer_sha256 = "";
        public string notes = "";
        public string source = "";
    }

    internal static class Helpers
    {
        public static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024 };

        public static void InitTls()
        {
            try
            {
                ServicePointManager.SecurityProtocol =
                    SecurityProtocolType.Tls12 | (SecurityProtocolType)3072 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
            }
            catch { }
        }

        public static string Sha256File(string path)
        {
            using (FileStream fs = File.OpenRead(path))
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(fs);
                StringBuilder sb = new StringBuilder(64);
                for (int i = 0; i < hash.Length; i++)
                    sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }

        public static bool IsAdmin()
        {
            try
            {
                using (WindowsIdentity id = WindowsIdentity.GetCurrent())
                {
                    WindowsPrincipal p = new WindowsPrincipal(id);
                    return p.IsInRole(WindowsBuiltInRole.Administrator);
                }
            }
            catch { return false; }
        }

        public static bool CanWriteDir(string dir)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return false;
            string probe = Path.Combine(dir, ".vi-write-probe-" + Guid.NewGuid().ToString("N") + ".tmp");
            try
            {
                File.WriteAllText(probe, "1");
                File.Delete(probe);
                return true;
            }
            catch { return false; }
            finally
            {
                try { if (File.Exists(probe)) File.Delete(probe); } catch { }
            }
        }

        public static InstallerState LoadState()
        {
            try
            {
                if (File.Exists(Config.StatePath))
                {
                    string raw = File.ReadAllText(Config.StatePath, Encoding.UTF8);
                    InstallerState st = Json.Deserialize<InstallerState>(raw);
                    if (st != null) return st;
                }
            }
            catch { }
            return new InstallerState();
        }

        public static void SaveState(InstallerState st)
        {
            Directory.CreateDirectory(Config.AppDataDir);
            string json = Json.Serialize(st);
            File.WriteAllText(Config.StatePath, json, new UTF8Encoding(false));
        }

        public static string FindJpGameRoot(string hint)
        {
            List<string> candidates = new List<string>();
            if (!string.IsNullOrWhiteSpace(hint))
            {
                try
                {
                    string h = Path.GetFullPath(hint.Trim().Trim('"'));
                    if (File.Exists(h)) h = Path.GetDirectoryName(h);
                    candidates.Add(h);
                    if (string.Equals(Path.GetFileName(h), "AzurPromiliaJP_Data", StringComparison.OrdinalIgnoreCase))
                        candidates.Add(Path.GetDirectoryName(h));
                    candidates.Add(Path.Combine(h, "AZUPRO_JP"));
                    candidates.Add(Path.Combine(h, "YostarGames", "AZUPRO_JP"));
                }
                catch { }
            }
            foreach (DriveInfo d in DriveInfo.GetDrives())
            {
                if (d.DriveType != DriveType.Fixed && d.DriveType != DriveType.Removable) continue;
                string root = d.RootDirectory.FullName;
                candidates.Add(Path.Combine(root, "YostarGames", "AZUPRO_JP"));
                candidates.Add(Path.Combine(root, "Games", "YostarGames", "AZUPRO_JP"));
                candidates.Add(Path.Combine(root, "AZUPRO_JP"));
                candidates.Add(Path.Combine(root, "Program Files", "YostarGames", "AZUPRO_JP"));
                candidates.Add(Path.Combine(root, "Program Files (x86)", "YostarGames", "AZUPRO_JP"));
            }
            foreach (string c in candidates)
            {
                try
                {
                    if (File.Exists(Path.Combine(c, "AzurPromiliaJP.exe")) &&
                        Directory.Exists(Path.Combine(c, "AzurPromiliaJP_Data")))
                        return Path.GetFullPath(c);
                }
                catch { }
            }
            return "";
        }

        public static string FindJpLauncherRoot(string hint, string gameRoot)
        {
            List<string> candidates = new List<string>();
            if (!string.IsNullOrWhiteSpace(hint))
            {
                try
                {
                    string h = Path.GetFullPath(hint.Trim().Trim('"'));
                    if (File.Exists(h)) h = Path.GetDirectoryName(h);
                    candidates.Add(h);
                    candidates.Add(Path.Combine(h, "AZUPRO_JP_Gamelauncher"));
                }
                catch { }
            }
            if (!string.IsNullOrWhiteSpace(gameRoot))
            {
                try
                {
                    string parent = Path.GetDirectoryName(gameRoot);
                    if (!string.IsNullOrEmpty(parent))
                        candidates.Add(Path.Combine(parent, "AZUPRO_JP_Gamelauncher"));
                }
                catch { }
            }
            foreach (DriveInfo d in DriveInfo.GetDrives())
            {
                if (d.DriveType != DriveType.Fixed && d.DriveType != DriveType.Removable) continue;
                string root = d.RootDirectory.FullName;
                candidates.Add(Path.Combine(root, "YostarGames", "AZUPRO_JP_Gamelauncher"));
                candidates.Add(Path.Combine(root, "Games", "YostarGames", "AZUPRO_JP_Gamelauncher"));
                candidates.Add(Path.Combine(root, "AZUPRO_JP_Gamelauncher"));
                candidates.Add(Path.Combine(root, "Program Files", "YostarGames", "AZUPRO_JP_Gamelauncher"));
            }
            foreach (string c in candidates)
            {
                try
                {
                    if (File.Exists(Path.Combine(c, "AZUPRO_JP_Gamelauncher.exe")) &&
                        File.Exists(Path.Combine(c, "resources", "app.asar")))
                        return Path.GetFullPath(c);
                }
                catch { }
            }
            return "";
        }

        public static string FindPayloadPackRoot(out string detectedVersion)
        {
            detectedVersion = "";
            string exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            List<string> candidates = new List<string>
            {
                exeDir,
                Path.GetDirectoryName(exeDir),
                Path.Combine(Config.AppDataDir, "active")
            };
            if (Directory.Exists(Config.CacheRoot))
            {
                string[] dirs = Directory.GetDirectories(Config.CacheRoot);
                Array.Sort(dirs, StringComparer.OrdinalIgnoreCase);
                Array.Reverse(dirs);
                foreach (string d in dirs) candidates.Add(d);
            }
            foreach (string c in candidates)
            {
                if (string.IsNullOrEmpty(c)) continue;
                if (File.Exists(Path.Combine(c, "tools", "Apply-JPCRCZH.ps1")) &&
                    File.Exists(Path.Combine(c, "tools", "jp-deployment-vi.json")) &&
                    File.Exists(Path.Combine(c, "payload-vi", "jp_game", "resources.assets")))
                {
                    string verFile = Path.Combine(c, "VERSION.txt");
                    if (File.Exists(verFile))
                        detectedVersion = File.ReadAllText(verFile, Encoding.UTF8).Trim();
                    return Path.GetFullPath(c);
                }
                // Check one nested folder (from Zip extraction prefix)
                try
                {
                    foreach (string sub in Directory.GetDirectories(c))
                    {
                        if (File.Exists(Path.Combine(sub, "tools", "Apply-JPCRCZH.ps1")) &&
                            File.Exists(Path.Combine(sub, "payload-vi", "jp_game", "resources.assets")))
                        {
                            string verFile = Path.Combine(sub, "VERSION.txt");
                            if (File.Exists(verFile))
                                detectedVersion = File.ReadAllText(verFile, Encoding.UTF8).Trim();
                            return Path.GetFullPath(sub);
                        }
                    }
                }
                catch { }
            }
            return "";
        }

        public static string CheckGameStatus(string packRoot, string gameRoot)
        {
            if (string.IsNullOrEmpty(gameRoot) || !Directory.Exists(Path.Combine(gameRoot, "AzurPromiliaJP_Data")))
                return "Chưa tìm thấy";
            if (string.IsNullOrEmpty(packRoot) || !File.Exists(Path.Combine(packRoot, "tools", "jp-deployment-vi.json")))
                return "Đã nhận diện thư mục (chưa có gói kiểm tra)";
            try
            {
                var plan = Json.Deserialize<Dictionary<string, object>>(
                    File.ReadAllText(Path.Combine(packRoot, "tools", "jp-deployment-vi.json"), Encoding.UTF8)
                );
                string dataRoot = Path.Combine(gameRoot, "AzurPromiliaJP_Data");
                var guards = (IEnumerable)plan["readonly_files"];
                foreach (Dictionary<string, object> g in guards)
                {
                    string p = Path.Combine(dataRoot, ((string)g["relative_path"]).Replace('/', '\\'));
                    if (!File.Exists(p)) return "Thiếu file dữ liệu gốc";
                    if (!string.Equals(Sha256File(p), (string)g["sha256"], StringComparison.OrdinalIgnoreCase))
                        return "Game đã cập nhật phiên bản mới (chờ patch mới)";
                }
                var files = (ICollection)plan["files"];
                int loc = 0, orig = 0;
                foreach (Dictionary<string, object> f in files)
                {
                    string p = Path.Combine(dataRoot, ((string)f["relative_path"]).Replace('/', '\\'));
                    if (!File.Exists(p)) return "Thiếu file " + (string)f["relative_path"];
                    string h = Sha256File(p);
                    if (string.Equals(h, (string)f["target_sha256"], StringComparison.OrdinalIgnoreCase)) loc++;
                    else if (string.Equals(h, (string)f["source_sha256"], StringComparison.OrdinalIgnoreCase)) orig++;
                    else return "File không khớp (" + Path.GetFileName(p) + ")";
                }
                if (loc == files.Count) return "Đã cài Việt hóa (11/11)";
                if (orig == files.Count) return "Bản gốc Nhật (Chưa cài)";
                return string.Format("Cài dở dang ({0}/{1})", loc, files.Count);
            }
            catch (Exception ex)
            {
                return "Lỗi kiểm tra: " + ex.Message;
            }
        }

        public static string CheckLauncherStatus(string packRoot, string launcherRoot)
        {
            if (string.IsNullOrEmpty(launcherRoot) || !File.Exists(Path.Combine(launcherRoot, "resources", "app.asar")))
                return "Chưa tìm thấy";
            if (string.IsNullOrEmpty(packRoot) || !File.Exists(Path.Combine(packRoot, "tools", "launcher-deployment-vi.json")))
                return "Đã nhận diện thư mục";
            try
            {
                var plan = Json.Deserialize<Dictionary<string, object>>(
                    File.ReadAllText(Path.Combine(packRoot, "tools", "launcher-deployment-vi.json"), Encoding.UTF8)
                );
                foreach (Dictionary<string, object> item in (IEnumerable)plan["launchers"])
                {
                    if ((string)item["id"] != "jp_launcher") continue;
                    string asar = Path.Combine(launcherRoot, "resources", "app.asar");
                    string h = Sha256File(asar);
                    if (string.Equals(h, (string)item["target_sha256"], StringComparison.OrdinalIgnoreCase))
                        return "Đã cài Việt hóa";
                    if (string.Equals(h, (string)item["source_sha256"], StringComparison.OrdinalIgnoreCase))
                        return "Bản gốc Nhật (Chưa cài)";
                    return "Phiên bản Launcher khác";
                }
            }
            catch { }
            return "Không rõ";
        }

        public static RemoteRelease FetchLatestRelease(int timeoutMs)
        {
            InitTls();
            // 1. Try raw latest-vi.json first (has exact sha256, size, jp_resource_version, changelog)
            try
            {
                string raw = DownloadString(Config.LatestJsonUrl + "?t=" + DateTimeOffset.UtcNow.ToUnixTimeSeconds(), timeoutMs);
                var doc = Json.Deserialize<Dictionary<string, object>>(raw);
                var full = (Dictionary<string, object>)doc["full_package"];
                RemoteRelease rr = new RemoteRelease
                {
                    version = Convert.ToString(doc["version"]),
                    published_at = doc.ContainsKey("published_at") ? Convert.ToString(doc["published_at"]) : "",
                    jp_resource_version = doc.ContainsKey("jp_resource_version") ? Convert.ToString(doc["jp_resource_version"]) : "",
                    jp_launcher_version = doc.ContainsKey("jp_launcher_version") ? Convert.ToString(doc["jp_launcher_version"]) : "",
                    full_zip_name = Convert.ToString(full["filename"]),
                    full_zip_url = Convert.ToString(full["url"]),
                    full_zip_sha256 = Convert.ToString(full["sha256"]),
                    full_zip_size = Convert.ToInt64(full["size"]),
                    notes = doc.ContainsKey("notes") ? Convert.ToString(doc["notes"]) : "",
                    source = "latest-vi.json"
                };
                if (doc.ContainsKey("installer") && doc["installer"] is Dictionary<string, object>)
                {
                    var inst = (Dictionary<string, object>)doc["installer"];
                    rr.installer_url = inst.ContainsKey("url") ? Convert.ToString(inst["url"]) : "";
                    rr.installer_sha256 = inst.ContainsKey("sha256") ? Convert.ToString(inst["sha256"]) : "";
                }
                return rr;
            }
            catch { }

            // 2. Fallback to GitHub Releases API
            string apiRaw = DownloadString(Config.ReleasesApiUrl, timeoutMs);
            var rel = Json.Deserialize<Dictionary<string, object>>(apiRaw);
            RemoteRelease res = new RemoteRelease
            {
                version = Convert.ToString(rel["tag_name"]),
                published_at = rel.ContainsKey("published_at") ? Convert.ToString(rel["published_at"]) : "",
                notes = rel.ContainsKey("body") ? Convert.ToString(rel["body"]) : "",
                source = "GitHub Releases API"
            };
            object assetsObj;
            if (rel.TryGetValue("assets", out assetsObj) && assetsObj is IEnumerable)
            {
                foreach (Dictionary<string, object> a in (IEnumerable)assetsObj)
                {
                    string name = Convert.ToString(a["name"]);
                    string url = Convert.ToString(a["browser_download_url"]);
                    if (name.IndexOf("-Full-vi-", StringComparison.OrdinalIgnoreCase) >= 0 && name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
                    {
                        res.full_zip_name = name;
                        res.full_zip_url = url;
                        res.full_zip_size = Convert.ToInt64(a["size"]);
                    }
                    else if (string.Equals(name, "AzurPromilia-VI-Setup.exe", StringComparison.OrdinalIgnoreCase))
                    {
                        res.installer_url = url;
                    }
                    else if (string.Equals(name, "SHA256SUMS.txt", StringComparison.OrdinalIgnoreCase))
                    {
                        try
                        {
                            string sums = DownloadString(url, timeoutMs);
                            foreach (string line in sums.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                            {
                                string[] parts = line.Trim().Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                                if (parts.Length >= 2 && parts[1].IndexOf("-Full-vi-", StringComparison.OrdinalIgnoreCase) >= 0)
                                    res.full_zip_sha256 = parts[0].ToLowerInvariant();
                            }
                        }
                        catch { }
                    }
                }
            }
            return res;
        }

        private static string DownloadString(string url, int timeoutMs)
        {
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.Method = "GET";
            req.UserAgent = "AzurPromilia-VI-Setup/1.0";
            req.Timeout = timeoutMs;
            req.ReadWriteTimeout = timeoutMs;
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                return sr.ReadToEnd();
        }

        public static void DownloadFileWithProgress(string url, string destPath, Action<long, long> onProgress)
        {
            InitTls();
            string temp = destPath + ".part";
            Directory.CreateDirectory(Path.GetDirectoryName(destPath));
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.Method = "GET";
            req.UserAgent = "AzurPromilia-VI-Setup/1.0";
            req.Timeout = 30000;
            req.ReadWriteTimeout = 60000;
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream input = resp.GetResponseStream())
            using (FileStream output = File.Create(temp))
            {
                long total = resp.ContentLength;
                byte[] buf = new byte[1024 * 128];
                long received = 0;
                int read;
                while ((read = input.Read(buf, 0, buf.Length)) > 0)
                {
                    output.Write(buf, 0, read);
                    received += read;
                    if (onProgress != null) onProgress(received, total);
                }
            }
            if (File.Exists(destPath)) File.Delete(destPath);
            File.Move(temp, destPath);
        }

        public static string ExtractPackageZip(string zipPath, string versionTag)
        {
            string safeTag = string.IsNullOrWhiteSpace(versionTag) ? "latest" : versionTag.Replace('/', '_').Replace('\\', '_');
            string dest = Path.Combine(Config.CacheRoot, safeTag);
            if (Directory.Exists(dest)) Directory.Delete(dest, true);
            Directory.CreateDirectory(dest);
            ZipFile.ExtractToDirectory(zipPath, dest);
            // Locate extracted root containing tools/Apply-JPCRCZH.ps1
            if (File.Exists(Path.Combine(dest, "tools", "Apply-JPCRCZH.ps1")))
            {
                File.WriteAllText(Path.Combine(dest, "VERSION.txt"), safeTag, Encoding.UTF8);
                return dest;
            }
            foreach (string sub in Directory.GetDirectories(dest))
            {
                if (File.Exists(Path.Combine(sub, "tools", "Apply-JPCRCZH.ps1")))
                {
                    File.WriteAllText(Path.Combine(sub, "VERSION.txt"), safeTag, Encoding.UTF8);
                    return sub;
                }
            }
            throw new InvalidDataException("Goi tai ve khong dung cau truc payload-vi/tools.");
        }

        public static int RunPsScript(string scriptPath, string args, Action<string> onLog, bool elevateIfNeeded)
        {
            string ps = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = ps,
                Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + scriptPath + "\" " + args,
                UseShellExecute = elevateIfNeeded,
                CreateNoWindow = !elevateIfNeeded
            };
            if (!elevateIfNeeded)
            {
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.StandardOutputEncoding = Encoding.UTF8;
                psi.StandardErrorEncoding = Encoding.UTF8;
                using (Process p = Process.Start(psi))
                {
                    p.OutputDataReceived += (s, e) => { if (e.Data != null && onLog != null) onLog(e.Data); };
                    p.ErrorDataReceived += (s, e) => { if (e.Data != null && onLog != null) onLog("[ERR] " + e.Data); };
                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();
                    p.WaitForExit();
                    return p.ExitCode;
                }
            }
            else
            {
                psi.Verb = "runas";
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit();
                    return p.ExitCode;
                }
            }
        }

        public static void CreateDesktopShortcut(string setupExePath)
        {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string lnk = Path.Combine(desktop, "Azur Promilia (Việt Hóa).lnk");
            string icon = "";
            string exeDir = Path.GetDirectoryName(setupExePath);
            string psScript =
                "$ws = New-Object -ComObject WScript.Shell; " +
                "$sc = $ws.CreateShortcut('" + lnk.Replace("'", "''") + "'); " +
                "$sc.TargetPath = '" + setupExePath.Replace("'", "''") + "'; " +
                "$sc.Arguments = '--auto-launch'; " +
                "$sc.WorkingDirectory = '" + exeDir.Replace("'", "''") + "'; " +
                "$sc.Description = 'Azur Promilia - Kiem tra cap nhat Viet hoa & Mo game'; " +
                (string.IsNullOrEmpty(icon) ? "" : "") +
                "$sc.Save()";
            string ps = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
            Process.Start(new ProcessStartInfo
            {
                FileName = ps,
                Arguments = "-NoProfile -ExecutionPolicy Bypass -Command \"" + psScript + "\"",
                UseShellExecute = false,
                CreateNoWindow = true
            }).WaitForExit();
        }
    }

    internal class MainForm : Form
    {
        private TextBox txtGamePath;
        private TextBox txtLauncherPath;
        private Label lblGameStatus;
        private Label lblLauncherStatus;
        private Label lblVersionInfo;
        private CheckBox chkShortcut;
        private CheckBox chkAutoLaunch;
        private ProgressBar progressBar;
        private Label lblProgress;
        private TextBox txtLog;
        private Button btnInstall;
        private Button btnCheckUpdate;
        private Button btnRestore;
        private Button btnVerify;
        private Button btnLaunch;

        private InstallerState _state;
        private string _packRoot = "";
        private string _localVersion = "";
        private RemoteRelease _remote;
        private bool _busy = false;

        public MainForm()
        {
            _state = Helpers.LoadState();
            InitializeUi();
            Shown += (s, e) => RefreshStateAndCheckAsync(true);
        }

        private void InitializeUi()
        {
            Text = "Azur Promilia — Cài đặt & Tự động cập nhật Việt hóa";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            ClientSize = new Size(760, 620);
            BackColor = Color.FromArgb(20, 23, 31);
            ForeColor = Color.FromArgb(236, 240, 248);
            Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);

            Label lblTitle = new Label
            {
                Text = "AZUR PROMILIA — VIỆT HÓA TIẾNG VIỆT (JP CLIENT)",
                Font = new Font("Segoe UI", 13.5f, FontStyle.Bold),
                ForeColor = Color.FromArgb(110, 200, 255),
                Location = new Point(22, 16),
                Size = new Size(716, 28)
            };
            Controls.Add(lblTitle);

            lblVersionInfo = new Label
            {
                Text = "Đang kiểm tra trạng thái gói Việt hóa & GitHub Releases...",
                ForeColor = Color.FromArgb(190, 200, 220),
                Location = new Point(22, 48),
                Size = new Size(560, 22)
            };
            Controls.Add(lblVersionInfo);

            btnCheckUpdate = MakeButton("Kiểm tra cập nhật", new Point(590, 42), new Size(148, 30), Color.FromArgb(46, 56, 78));
            btnCheckUpdate.Click += (s, e) => RefreshStateAndCheckAsync(true);
            Controls.Add(btnCheckUpdate);

            // Paths Panel
            Panel pnlPaths = new Panel
            {
                BackColor = Color.FromArgb(28, 33, 45),
                Location = new Point(22, 82),
                Size = new Size(716, 152)
            };
            Controls.Add(pnlPaths);

            Label l1 = new Label { Text = "Thư mục Game JP (AZUPRO_JP):", Location = new Point(14, 12), Size = new Size(250, 20), ForeColor = Color.FromArgb(180, 192, 214) };
            lblGameStatus = new Label { Text = "...", Location = new Point(280, 12), Size = new Size(420, 20), TextAlign = ContentAlignment.MiddleRight, ForeColor = Color.FromArgb(120, 230, 160) };
            txtGamePath = new TextBox { Location = new Point(14, 34), Size = new Size(600, 25), BackColor = Color.FromArgb(18, 21, 29), ForeColor = Color.White, BorderStyle = BorderStyle.FixedSingle };
            Button btnBrowseGame = MakeButton("Chọn...", new Point(622, 33), new Size(80, 26), Color.FromArgb(52, 62, 84));
            btnBrowseGame.Click += (s, e) => BrowseFolder(txtGamePath, true);

            Label l2 = new Label { Text = "Thư mục Launcher JP (AZUPRO_JP_Gamelauncher):", Location = new Point(14, 72), Size = new Size(320, 20), ForeColor = Color.FromArgb(180, 192, 214) };
            lblLauncherStatus = new Label { Text = "...", Location = new Point(350, 72), Size = new Size(350, 20), TextAlign = ContentAlignment.MiddleRight, ForeColor = Color.FromArgb(120, 230, 160) };
            txtLauncherPath = new TextBox { Location = new Point(14, 94), Size = new Size(600, 25), BackColor = Color.FromArgb(18, 21, 29), ForeColor = Color.White, BorderStyle = BorderStyle.FixedSingle };
            Button btnBrowseLauncher = MakeButton("Chọn...", new Point(622, 93), new Size(80, 26), Color.FromArgb(52, 62, 84));
            btnBrowseLauncher.Click += (s, e) => BrowseFolder(txtLauncherPath, false);

            chkShortcut = new CheckBox
            {
                Text = "Tạo shortcut Desktop \"Azur Promilia (Việt Hóa)\"",
                Checked = true,
                Location = new Point(14, 124),
                Size = new Size(340, 22),
                ForeColor = Color.FromArgb(200, 210, 230)
            };
            chkAutoLaunch = new CheckBox
            {
                Text = "Tự kiểm tra & cập nhật khi mở Launcher",
                Checked = _state.auto_update_on_launch,
                Location = new Point(365, 124),
                Size = new Size(335, 22),
                ForeColor = Color.FromArgb(200, 210, 230)
            };

            pnlPaths.Controls.AddRange(new Control[] { l1, lblGameStatus, txtGamePath, btnBrowseGame, l2, lblLauncherStatus, txtLauncherPath, btnBrowseLauncher, chkShortcut, chkAutoLaunch });

            // Action Buttons
            btnInstall = MakeButton("Cài đặt / Cập nhật Việt hóa", new Point(22, 248), new Size(250, 42), Color.FromArgb(35, 122, 220));
            btnInstall.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            btnInstall.Click += (s, e) => StartInstallOrUpdate();

            btnRestore = MakeButton("Khôi phục bản gốc", new Point(282, 248), new Size(155, 42), Color.FromArgb(135, 62, 62));
            btnRestore.Click += (s, e) => StartRestore();

            btnVerify = MakeButton("Kiểm tra CRC", new Point(447, 248), new Size(125, 42), Color.FromArgb(55, 68, 92));
            btnVerify.Click += (s, e) => StartVerify();

            btnLaunch = MakeButton("Mở Launcher", new Point(582, 248), new Size(156, 42), Color.FromArgb(38, 138, 96));
            btnLaunch.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            btnLaunch.Click += (s, e) => LaunchGame();

            Controls.AddRange(new Control[] { btnInstall, btnRestore, btnVerify, btnLaunch });

            progressBar = new ProgressBar { Location = new Point(22, 302), Size = new Size(716, 18), Style = ProgressBarStyle.Continuous };
            lblProgress = new Label { Text = "Sẵn sàng.", Location = new Point(22, 323), Size = new Size(716, 20), ForeColor = Color.FromArgb(170, 185, 210) };
            Controls.Add(progressBar);
            Controls.Add(lblProgress);

            txtLog = new TextBox
            {
                Location = new Point(22, 348),
                Size = new Size(716, 250),
                Multiline = true,
                ReadOnly = true,
                ScrollBars = ScrollBars.Vertical,
                BackColor = Color.FromArgb(14, 16, 22),
                ForeColor = Color.FromArgb(215, 224, 240),
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Consolas", 9f)
            };
            Controls.Add(txtLog);
        }

        private Button MakeButton(string text, Point loc, Size size, Color bg)
        {
            Button b = new Button
            {
                Text = text,
                Location = loc,
                Size = size,
                BackColor = bg,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            b.FlatAppearance.BorderSize = 0;
            return b;
        }

        private void BrowseFolder(TextBox target, bool isGame)
        {
            using (FolderBrowserDialog dlg = new FolderBrowserDialog())
            {
                dlg.Description = isGame ? "Chọn thư mục AZUPRO_JP" : "Chọn thư mục AZUPRO_JP_Gamelauncher";
                if (Directory.Exists(target.Text)) dlg.SelectedPath = target.Text;
                if (dlg.ShowDialog() == DialogResult.OK)
                {
                    target.Text = isGame
                        ? (Helpers.FindJpGameRoot(dlg.SelectedPath) != "" ? Helpers.FindJpGameRoot(dlg.SelectedPath) : dlg.SelectedPath)
                        : (Helpers.FindJpLauncherRoot(dlg.SelectedPath, txtGamePath.Text) != "" ? Helpers.FindJpLauncherRoot(dlg.SelectedPath, txtGamePath.Text) : dlg.SelectedPath);
                    RefreshLocalStatuses();
                }
            }
        }

        private void Log(string line)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(Log), line); return; }
            txtLog.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + line + Environment.NewLine);
        }

        private void SetBusy(bool busy, string status)
        {
            if (InvokeRequired) { BeginInvoke(new Action<bool, string>(SetBusy), busy, status); return; }
            _busy = busy;
            btnInstall.Enabled = !busy;
            btnRestore.Enabled = !busy;
            btnVerify.Enabled = !busy;
            btnCheckUpdate.Enabled = !busy;
            btnLaunch.Enabled = !busy;
            if (!string.IsNullOrEmpty(status)) lblProgress.Text = status;
        }

        private void RefreshLocalStatuses()
        {
            string g = txtGamePath.Text.Trim();
            string l = txtLauncherPath.Text.Trim();
            string gs = Helpers.CheckGameStatus(_packRoot, g);
            string ls = Helpers.CheckLauncherStatus(_packRoot, l);
            lblGameStatus.Text = gs;
            lblGameStatus.ForeColor = gs.IndexOf("Đã cài") >= 0 ? Color.FromArgb(110, 235, 160) :
                                      gs.IndexOf("Chưa tìm") >= 0 || gs.IndexOf("chờ patch") >= 0 ? Color.FromArgb(255, 195, 95) :
                                      Color.FromArgb(160, 210, 255);
            lblLauncherStatus.Text = ls;
            lblLauncherStatus.ForeColor = ls.IndexOf("Đã cài") >= 0 ? Color.FromArgb(110, 235, 160) : Color.FromArgb(160, 210, 255);
        }

        private void RefreshStateAndCheckAsync(bool fetchOnline)
        {
            string detectedVer;
            _packRoot = Helpers.FindPayloadPackRoot(out detectedVer);
            _localVersion = string.IsNullOrEmpty(detectedVer) ? _state.installed_version : detectedVer;
            if (string.IsNullOrEmpty(txtGamePath.Text))
                txtGamePath.Text = Helpers.FindJpGameRoot(_state.jp_game_path);
            if (string.IsNullOrEmpty(txtLauncherPath.Text))
                txtLauncherPath.Text = Helpers.FindJpLauncherRoot(_state.jp_launcher_path, txtGamePath.Text);
            RefreshLocalStatuses();

            if (!fetchOnline) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    RemoteRelease rr = Helpers.FetchLatestRelease(8000);
                    _remote = rr;
                    BeginInvoke(new Action(() =>
                    {
                        string localTxt = string.IsNullOrEmpty(_localVersion) ? "chưa ghi nhận" : _localVersion;
                        string updateNote = (!string.IsNullOrEmpty(rr.version) && rr.version != _localVersion)
                            ? " (CÓ BẢN MỚI!)" : " (Đã mới nhất)";
                        lblVersionInfo.Text = string.Format("Bản đang có: {0}  |  GitHub mới nhất: {1}{2}",
                            localTxt, string.IsNullOrEmpty(rr.version) ? "?" : rr.version, updateNote);
                        Log("Đã kiểm tra GitHub (" + rr.source + "): bản mới nhất = " + rr.version +
                            (string.IsNullOrEmpty(rr.jp_resource_version) ? "" : " (Client JP #" + rr.jp_resource_version + ")"));
                    }));
                }
                catch (Exception ex)
                {
                    BeginInvoke(new Action(() =>
                    {
                        string localTxt = string.IsNullOrEmpty(_packRoot) ? "Chưa có payload" : "Payload cục bộ sẵn sàng";
                        lblVersionInfo.Text = localTxt + "  |  Không kết nối được GitHub (Offline mode)";
                        Log("Không kiểm tra được GitHub (sẽ dùng gói cục bộ nếu có): " + ex.Message);
                    }));
                }
            });
        }

        private string EnsurePackageAvailable()
        {
            string localVer;
            string localRoot = Helpers.FindPayloadPackRoot(out localVer);
            bool needDownload = string.IsNullOrEmpty(localRoot);

            if (_remote != null && !string.IsNullOrEmpty(_remote.full_zip_url) && !string.IsNullOrEmpty(_remote.version))
            {
                if (string.IsNullOrEmpty(localRoot) || (!string.IsNullOrEmpty(localVer) && localVer != _remote.version))
                {
                    needDownload = true;
                }
            }

            if (!needDownload && !string.IsNullOrEmpty(localRoot))
            {
                Log("Sử dụng bộ cài Việt hóa sẵn có tại: " + localRoot);
                return localRoot;
            }

            if (_remote == null)
            {
                try { _remote = Helpers.FetchLatestRelease(12000); }
                catch (Exception ex)
                {
                    if (!string.IsNullOrEmpty(localRoot))
                    {
                        Log("Lỗi tải online (" + ex.Message + "), quay lại dùng gói cục bộ.");
                        return localRoot;
                    }
                    throw new Exception("Không tìm thấy gói payload-vi cục bộ và không tải được từ GitHub: " + ex.Message);
                }
            }

            if (string.IsNullOrEmpty(_remote.full_zip_url))
            {
                if (!string.IsNullOrEmpty(localRoot)) return localRoot;
                throw new Exception("GitHub Release chưa có asset gói Full-vi-*.zip.");
            }

            string zipPath = Path.Combine(Config.CacheRoot, _remote.full_zip_name);
            Log("Đang tải " + _remote.full_zip_name + " (" + (_remote.full_zip_size / 1048576.0).ToString("0.0") + " MB)...");
            Helpers.DownloadFileWithProgress(_remote.full_zip_url, zipPath, (rec, tot) =>
            {
                int pct = tot > 0 ? (int)Math.Min(100, rec * 100 / tot) : 0;
                BeginInvoke(new Action(() =>
                {
                    progressBar.Value = pct;
                    lblProgress.Text = string.Format("Đang tải gói Việt hóa... {0}% ({1:0.0} / {2:0.0} MB)",
                        pct, rec / 1048576.0, Math.Max(tot, rec) / 1048576.0);
                }));
            });

            if (!string.IsNullOrEmpty(_remote.full_zip_sha256))
            {
                Log("Đang kiểm tra SHA256 file tải về...");
                string got = Helpers.Sha256File(zipPath);
                if (!string.Equals(got, _remote.full_zip_sha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("File tải về bị hỏng SHA256! Mong đợi " + _remote.full_zip_sha256 + ", nhận được " + got);
                Log("SHA256 khớp 100%.");
            }

            BeginInvoke(new Action(() => lblProgress.Text = "Đang giải nén gói Việt hóa..."));
            string extracted = Helpers.ExtractPackageZip(zipPath, _remote.version);
            _packRoot = extracted;
            _localVersion = _remote.version;
            return extracted;
        }

        private void StartInstallOrUpdate()
        {
            if (_busy) return;
            string gameDir = txtGamePath.Text.Trim();
            string launcherDir = txtLauncherPath.Text.Trim();
            if (string.IsNullOrEmpty(gameDir) && string.IsNullOrEmpty(launcherDir))
            {
                MessageBox.Show("Chưa chọn thư mục AZUPRO_JP hoặc AZUPRO_JP_Gamelauncher!", "Thiếu đường dẫn", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            SetBusy(true, "Đang chuẩn bị cài đặt...");
            progressBar.Value = 0;

            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string packRoot = EnsurePackageAvailable();
                    bool needAdmin = (!string.IsNullOrEmpty(gameDir) && !Helpers.CanWriteDir(Path.Combine(gameDir, "AzurPromiliaJP_Data"))) ||
                                     (!string.IsNullOrEmpty(launcherDir) && !Helpers.CanWriteDir(Path.Combine(launcherDir, "resources")));
                    if (needAdmin && !Helpers.IsAdmin())
                        Log("Thư mục game cần quyền Quản trị viên (UAC), hệ thống sẽ hỏi xác nhận...");

                    if (!string.IsNullOrEmpty(gameDir))
                    {
                        Log("Đang áp dụng bản Việt hóa cho JP Game (kiểm tra size + SHA256 + CRC32)...");
                        int rc = Helpers.RunPsScript(
                            Path.Combine(packRoot, "tools", "Apply-JPCRCZH.ps1"),
                            "-Action Apply -Language vi -Hint \"" + gameDir + "\"",
                            Log, needAdmin && !Helpers.IsAdmin()
                        );
                        if (rc != 0) throw new Exception("Apply-JPCRCZH.ps1 thất bại với mã " + rc);
                    }
                    if (!string.IsNullOrEmpty(launcherDir))
                    {
                        Log("Đang áp dụng bản Việt hóa cho JP Launcher...");
                        int rc = Helpers.RunPsScript(
                            Path.Combine(packRoot, "tools", "Apply-Launchers.ps1"),
                            "-Action Apply -Target jp_launcher -Language vi -Hint \"" + launcherDir + "\"",
                            Log, needAdmin && !Helpers.IsAdmin()
                        );
                        if (rc != 0) throw new Exception("Apply-Launchers.ps1 thất bại với mã " + rc);
                    }

                    // Copy self to AppData so desktop shortcut & auto-updater persist cleanly
                    Directory.CreateDirectory(Config.AppDataDir);
                    string selfExe = Assembly.GetExecutingAssembly().Location;
                    string installedExe = Path.Combine(Config.AppDataDir, "AzurPromilia-VI-Setup.exe");
                    if (!string.Equals(Path.GetFullPath(selfExe), Path.GetFullPath(installedExe), StringComparison.OrdinalIgnoreCase))
                        File.Copy(selfExe, installedExe, true);

                    _state.installed_version = !string.IsNullOrEmpty(_localVersion) ? _localVersion : Config.CurrentInstallerVersion;
                    _state.jp_game_path = gameDir;
                    _state.jp_launcher_path = launcherDir;
                    _state.auto_update_on_launch = chkAutoLaunch.Checked;
                    _state.last_checked_utc = DateTime.UtcNow.ToString("o");
                    Helpers.SaveState(_state);

                    if (chkShortcut.Checked)
                    {
                        Helpers.CreateDesktopShortcut(installedExe);
                        Log("Đã tạo shortcut Desktop: \"Azur Promilia (Việt Hóa)\".");
                    }

                    BeginInvoke(new Action(() =>
                    {
                        progressBar.Value = 100;
                        RefreshLocalStatuses();
                        SetBusy(false, "Cài đặt Việt hóa thành công!");
                        MessageBox.Show("Cài đặt / Cập nhật Việt hóa hoàn tất!", "Thành công", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }));
                }
                catch (Exception ex)
                {
                    Log("[LỖI] " + ex.Message);
                    BeginInvoke(new Action(() =>
                    {
                        SetBusy(false, "Cài đặt thất bại.");
                        MessageBox.Show("Lỗi: " + ex.Message, "Thất bại", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }));
                }
            });
        }

        private void StartRestore()
        {
            if (_busy || string.IsNullOrEmpty(_packRoot))
            {
                MessageBox.Show("Cần có thư mục tools/ hoặc gói Việt hóa để chạy Khôi phục an toàn.", "Thông báo", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            string gameDir = txtGamePath.Text.Trim();
            string launcherDir = txtLauncherPath.Text.Trim();
            SetBusy(true, "Đang khôi phục bản gốc...");
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    bool needAdmin = (!string.IsNullOrEmpty(gameDir) && !Helpers.CanWriteDir(Path.Combine(gameDir, "AzurPromiliaJP_Data"))) ||
                                     (!string.IsNullOrEmpty(launcherDir) && !Helpers.CanWriteDir(Path.Combine(launcherDir, "resources")));
                    if (!string.IsNullOrEmpty(gameDir))
                    {
                        int rc = Helpers.RunPsScript(Path.Combine(_packRoot, "tools", "Apply-JPCRCZH.ps1"),
                            "-Action Restore -Language vi -Hint \"" + gameDir + "\"", Log, needAdmin && !Helpers.IsAdmin());
                        if (rc != 0) throw new Exception("Restore JP Game lỗi mã " + rc);
                    }
                    if (!string.IsNullOrEmpty(launcherDir))
                    {
                        int rc = Helpers.RunPsScript(Path.Combine(_packRoot, "tools", "Apply-Launchers.ps1"),
                            "-Action Restore -Target jp_launcher -Language vi -Hint \"" + launcherDir + "\"", Log, needAdmin && !Helpers.IsAdmin());
                        if (rc != 0) throw new Exception("Restore JP Launcher lỗi mã " + rc);
                    }
                    BeginInvoke(new Action(() =>
                    {
                        RefreshLocalStatuses();
                        SetBusy(false, "Đã khôi phục nguyên bản!");
                    }));
                }
                catch (Exception ex)
                {
                    Log("[LỖI] " + ex.Message);
                    BeginInvoke(new Action(() => SetBusy(false, "Khôi phục lỗi.")));
                }
            });
        }

        private void StartVerify()
        {
            if (_busy || string.IsNullOrEmpty(_packRoot))
            {
                RefreshLocalStatuses();
                return;
            }
            string gameDir = txtGamePath.Text.Trim();
            string launcherDir = txtLauncherPath.Text.Trim();
            SetBusy(true, "Đang kiểm tra toàn bộ CRC32 & SHA256...");
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    if (!string.IsNullOrEmpty(gameDir))
                        Helpers.RunPsScript(Path.Combine(_packRoot, "tools", "Apply-JPCRCZH.ps1"),
                            "-Action Verify -Language vi -Hint \"" + gameDir + "\"", Log, false);
                    if (!string.IsNullOrEmpty(launcherDir))
                        Helpers.RunPsScript(Path.Combine(_packRoot, "tools", "Apply-Launchers.ps1"),
                            "-Action Verify -Target jp_launcher -Language vi -Hint \"" + launcherDir + "\"", Log, false);
                    BeginInvoke(new Action(() =>
                    {
                        RefreshLocalStatuses();
                        SetBusy(false, "Kiểm tra hoàn tất.");
                    }));
                }
                catch (Exception ex)
                {
                    Log("[LỖI] " + ex.Message);
                    BeginInvoke(new Action(() => SetBusy(false, "Kiểm tra gặp lỗi.")));
                }
            });
        }

        private void LaunchGame()
        {
            string launcherDir = txtLauncherPath.Text.Trim();
            if (string.IsNullOrEmpty(launcherDir) || !File.Exists(Path.Combine(launcherDir, "AZUPRO_JP_Gamelauncher.exe")))
            {
                MessageBox.Show("Không tìm thấy AZUPRO_JP_Gamelauncher.exe!", "Lỗi", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            _state.auto_update_on_launch = chkAutoLaunch.Checked;
            _state.jp_game_path = txtGamePath.Text.Trim();
            _state.jp_launcher_path = launcherDir;
            Helpers.SaveState(_state);

            if (chkAutoLaunch.Checked && _remote != null && !string.IsNullOrEmpty(_remote.version) && _remote.version != _localVersion)
            {
                if (MessageBox.Show("Có bản cập nhật Việt hóa mới (" + _remote.version + "). Cập nhật ngay trước khi mở Launcher?",
                    "Cập nhật Việt hóa", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                {
                    StartInstallOrUpdate();
                    return;
                }
            }
            Process.Start(new ProcessStartInfo
            {
                FileName = Path.Combine(launcherDir, "AZUPRO_JP_Gamelauncher.exe"),
                WorkingDirectory = launcherDir,
                UseShellExecute = true
            });
        }
    }

    internal static class Program
    {
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        private static int Main(string[] args)
        {
            try { SetProcessDPIAware(); } catch { }
            try { Console.OutputEncoding = Encoding.UTF8; } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            List<string> argList = new List<string>(args);
            if (argList.Contains("--check"))
            {
                InstallerState st = Helpers.LoadState();
                string ver;
                string pr = Helpers.FindPayloadPackRoot(out ver);
                string g = Helpers.FindJpGameRoot(st.jp_game_path);
                string l = Helpers.FindJpLauncherRoot(st.jp_launcher_path, g);
                Console.WriteLine("PACK_ROOT=" + pr);
                Console.WriteLine("PACK_VER=" + ver);
                Console.WriteLine("JP_GAME=" + g + " | " + Helpers.CheckGameStatus(pr, g));
                Console.WriteLine("JP_LAUNCHER=" + l + " | " + Helpers.CheckLauncherStatus(pr, l));
                return 0;
            }

            if (argList.Contains("--auto-launch"))
            {
                RunAutoUpdateThenLaunch();
                return 0;
            }

            Application.Run(new MainForm());
            return 0;
        }

        private static void RunAutoUpdateThenLaunch()
        {
            InstallerState st = Helpers.LoadState();
            string ver;
            string pr = Helpers.FindPayloadPackRoot(out ver);
            string g = Helpers.FindJpGameRoot(st.jp_game_path);
            string l = Helpers.FindJpLauncherRoot(st.jp_launcher_path, g);

            try
            {
                if (st.auto_update_on_launch)
                {
                    RemoteRelease rr = Helpers.FetchLatestRelease(3500);
                    string cur = string.IsNullOrEmpty(ver) ? st.installed_version : ver;
                    if (!string.IsNullOrEmpty(rr.version) && rr.version != cur && !string.IsNullOrEmpty(rr.full_zip_url))
                    {
                        string zipPath = Path.Combine(Config.CacheRoot, rr.full_zip_name);
                        Helpers.DownloadFileWithProgress(rr.full_zip_url, zipPath, null);
                        if (string.IsNullOrEmpty(rr.full_zip_sha256) ||
                            string.Equals(Helpers.Sha256File(zipPath), rr.full_zip_sha256, StringComparison.OrdinalIgnoreCase))
                        {
                            string newPack = Helpers.ExtractPackageZip(zipPath, rr.version);
                            bool needAdmin = (!string.IsNullOrEmpty(g) && !Helpers.CanWriteDir(Path.Combine(g, "AzurPromiliaJP_Data"))) ||
                                             (!string.IsNullOrEmpty(l) && !Helpers.CanWriteDir(Path.Combine(l, "resources")));
                            if (!string.IsNullOrEmpty(g))
                                Helpers.RunPsScript(Path.Combine(newPack, "tools", "Apply-JPCRCZH.ps1"),
                                    "-Action Apply -Language vi -Hint \"" + g + "\"", null, needAdmin && !Helpers.IsAdmin());
                            if (!string.IsNullOrEmpty(l))
                                Helpers.RunPsScript(Path.Combine(newPack, "tools", "Apply-Launchers.ps1"),
                                    "-Action Apply -Target jp_launcher -Language vi -Hint \"" + l + "\"", null, needAdmin && !Helpers.IsAdmin());
                            st.installed_version = rr.version;
                            st.last_checked_utc = DateTime.UtcNow.ToString("o");
                            Helpers.SaveState(st);
                        }
                    }
                }
            }
            catch { /* Never block launching the game when offline */ }

            if (!string.IsNullOrEmpty(l) && File.Exists(Path.Combine(l, "AZUPRO_JP_Gamelauncher.exe")))
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = Path.Combine(l, "AZUPRO_JP_Gamelauncher.exe"),
                    WorkingDirectory = l,
                    UseShellExecute = true
                });
            }
            else
            {
                Application.Run(new MainForm());
            }
        }
    }
}
