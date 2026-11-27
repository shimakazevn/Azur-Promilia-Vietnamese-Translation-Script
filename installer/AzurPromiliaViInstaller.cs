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
[assembly: AssemblyVersion("1.0.6.0")]
[assembly: AssemblyFileVersion("1.0.6.0")]

namespace AzurPromiliaVIInstaller
{
    internal static class Config
    {
        public const string RepoSlug = "shimakazevn/Azur-Promilia-Vietnamese-Translation-Script";
        public const string LatestJsonUrl = "https://raw.githubusercontent.com/" + RepoSlug + "/main/latest-vi.json";
        public const string ReleasesApiUrl = "https://api.github.com/repos/" + RepoSlug + "/releases/latest";
        public const string CurrentInstallerVersion = "v1.0.6";
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

        public static string DetectVersionInDir(string dir, string exeDir)
        {
            if (string.IsNullOrEmpty(dir)) return "";
            string verFile = Path.Combine(dir, "VERSION.txt");
            if (File.Exists(verFile))
                return File.ReadAllText(verFile, Encoding.UTF8).Trim();
            string latestFile = Path.Combine(dir, "latest-vi.json");
            if (File.Exists(latestFile))
            {
                try
                {
                    var doc = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(latestFile, Encoding.UTF8));
                    if (doc != null && doc.ContainsKey("version"))
                    {
                        string v = Convert.ToString(doc["version"]);
                        if (!string.IsNullOrWhiteSpace(v)) return v.Trim();
                    }
                }
                catch { }
            }
            if (!string.IsNullOrEmpty(exeDir) && string.Equals(Path.GetFullPath(dir), Path.GetFullPath(exeDir), StringComparison.OrdinalIgnoreCase))
                return Config.CurrentInstallerVersion;
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
                    detectedVersion = DetectVersionInDir(c, exeDir);
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
                            detectedVersion = DetectVersionInDir(sub, exeDir);
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

        private static readonly string[][] FallbackDeblurEntries = new[]
        {
            new[] { @".res\default_package\BundleFiles\vcnqp22wy61m2n1z1kyxrg.r", "2873efc3e3e4ea8bb31c166761ebf6c59aa454aa2b390d1f50fb297a1a366296", "ec89daae74c4615b4770428b34822aa0bb7d3dc088e4be45bed02d8be6a42bc3" },
            new[] { @"StreamingAssets\.res\default_package\6ffhq8vxxcxhajv2smenba.r", "a6d16f6bf54574079699057abe500a394cd6d7f8cfef70c8a7ca9978ed07d5d6", "8f1e44219c451af2d16ac7aa14b5c1fb98d693bbe07e5b3668ad601523c516f1" },
            new[] { @"StreamingAssets\.res\default_package\f4izs5z5g3dowxewfbsww.r", "dfca7050aa65e6370ff22b2edb7005e28328d50b400b0854cd91032a8220cda1", "1773f99f4a9861f6fa412622664192c158b461242bacfd4c5d83c21da6e5673f" },
            new[] { @"StreamingAssets\.res\default_package\vrvljtvqpritdz11tc6eg.r", "d0a8b601a4ea6d59c04e288ae66be25de533e8c65b97ce9c7398fe6ff9a934b1", "0114ad665f64052168c7e5a733179cb80976aafb86f6f520f130773dc4232fac" }
        };

        public static bool HasDeblurPayload(string packRoot)
        {
            if (string.IsNullOrEmpty(packRoot)) return false;
            if (!File.Exists(Path.Combine(packRoot, "tools", "Apply-JPDeblur.ps1"))) return false;
            if (!File.Exists(Path.Combine(packRoot, "tools", "jp-deblur-deployment.json"))) return false;
            return File.Exists(Path.Combine(packRoot, "payload-vi", "jp_deblur", ".res", "default_package", "BundleFiles", "vcnqp22wy61m2n1z1kyxrg.r"))
                || File.Exists(Path.Combine(packRoot, "payload", "jp_deblur", ".res", "default_package", "BundleFiles", "vcnqp22wy61m2n1z1kyxrg.r"));
        }

        public static string CheckDeblurStatus(string packRoot, string gameRoot)
        {
            if (string.IsNullOrEmpty(gameRoot) || !Directory.Exists(Path.Combine(gameRoot, "AzurPromiliaJP_Data")))
                return "Chưa tìm thấy";
            try
            {
                string dataRoot = Path.Combine(gameRoot, "AzurPromiliaJP_Data");
                var entries = new List<string[]>();
                string planPath = !string.IsNullOrEmpty(packRoot) ? Path.Combine(packRoot, "tools", "jp-deblur-deployment.json") : "";
                if (!string.IsNullOrEmpty(planPath) && File.Exists(planPath))
                {
                    var plan = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(planPath, Encoding.UTF8));
                    foreach (Dictionary<string, object> f in (IEnumerable)plan["files"])
                    {
                        entries.Add(new[] {
                            ((string)f["relative_path"]).Replace('/', '\\'),
                            (string)f["source_sha256"],
                            (string)f["target_sha256"]
                        });
                    }
                }
                else
                {
                    entries.AddRange(FallbackDeblurEntries);
                }
                int on = 0, off = 0;
                foreach (string[] e in entries)
                {
                    string p = Path.Combine(dataRoot, e[0]);
                    if (!File.Exists(p)) return "Thiếu file " + Path.GetFileName(p);
                    string h = Sha256File(p);
                    if (string.Equals(h, e[2], StringComparison.OrdinalIgnoreCase)) on++;
                    else if (string.Equals(h, e[1], StringComparison.OrdinalIgnoreCase)) off++;
                    else return "File khác (" + Path.GetFileName(p) + ")";
                }
                if (on == entries.Count) return string.Format("Đang BẬT ({0}/{1})", on, entries.Count);
                if (off == entries.Count) return string.Format("Đang TẮT ({0}/{1})", off, entries.Count);
                return string.Format("Bật dở dang ({0}/{1})", on, entries.Count);
            }
            catch (Exception ex)
            {
                return "Lỗi kiểm tra: " + ex.Message;
            }
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

        public static string SyncInstalledExe(string packRoot)
        {
            Directory.CreateDirectory(Config.AppDataDir);
            string installedExe = Path.Combine(Config.AppDataDir, "AzurPromilia-VI-Setup.exe");
            string selfExe = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
            string preferred = selfExe;
            if (!string.IsNullOrEmpty(packRoot))
            {
                string cand = Path.Combine(packRoot, "AzurPromilia-VI-Setup.exe");
                if (File.Exists(cand)) preferred = Path.GetFullPath(cand);
            }
            string destFull = Path.GetFullPath(installedExe);
            if (!string.Equals(selfExe, destFull, StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    if (!File.Exists(destFull) || !string.Equals(Sha256File(preferred), Sha256File(destFull), StringComparison.OrdinalIgnoreCase))
                        File.Copy(preferred, destFull, true);
                }
                catch { }
            }
            else if (!string.Equals(preferred, selfExe, StringComparison.OrdinalIgnoreCase) && File.Exists(preferred))
            {
                try
                {
                    if (!string.Equals(Sha256File(preferred), Sha256File(selfExe), StringComparison.OrdinalIgnoreCase))
                    {
                        string staged = destFull + ".new";
                        File.Copy(preferred, staged, true);
                        string cmd = "/c ping -n 2 127.0.0.1 >nul & move /y \"" + staged + "\" \"" + destFull + "\"";
                        Process.Start(new ProcessStartInfo { FileName = "cmd.exe", Arguments = cmd, UseShellExecute = false, CreateNoWindow = true });
                    }
                }
                catch { }
            }
            return installedExe;
        }
    }

    internal class MainForm : Form
    {
        private TextBox txtGamePath;
        private TextBox txtLauncherPath;
        private Label lblGameStatus;
        private Label lblLauncherStatus;
        private Label lblDeblurStatus;
        private Label lblVersionInfo;
        private CheckBox chkShortcut;
        private CheckBox chkAutoLaunch;
        private CheckBox chkDeblur;
        private ProgressBar progressBar;
        private Label lblProgress;
        private TextBox txtLog;
        private Button btnInstall;
        private Button btnCheckUpdate;
        private Button btnRestore;
        private Button btnVerify;
        private Button btnLaunch;
        private Button btnDeblurToggle;

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
            Text = "Azur Promilia — Cài đặt & Tự động cập nhật Việt hóa (" + Config.CurrentInstallerVersion + ")";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            ClientSize = new Size(760, 666);
            BackColor = Color.FromArgb(20, 23, 31);
            ForeColor = Color.FromArgb(236, 240, 248);
            Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);

            Label lblTitle = new Label
            {
                Text = "AZUR PROMILIA — VIỆT HÓA TIẾNG VIỆT (JP CLIENT) · " + Config.CurrentInstallerVersion,
                Font = new Font("Segoe UI", 13.5f, FontStyle.Bold),
                ForeColor = Color.FromArgb(110, 200, 255),
                Location = new Point(22, 16),
                Size = new Size(716, 28)
            };
            Controls.Add(lblTitle);

            lblVersionInfo = new Label
            {
                Text = "App Setup: " + Config.CurrentInstallerVersion + "  |  Đang kiểm tra trạng thái & GitHub...",
                ForeColor = Color.FromArgb(190, 200, 220),
                Location = new Point(22, 48),
                Size = new Size(560, 22)
            };
            Controls.Add(lblVersionInfo);

            btnCheckUpdate = MakeButton("Kiểm tra cập nhật", new Point(590, 42), new Size(148, 30), Color.FromArgb(46, 56, 78));
            btnCheckUpdate.Click += (s, e) => RefreshStateAndCheckAsync(true);
            Controls.Add(btnCheckUpdate);

            // Paths & Options Panel
            Panel pnlPaths = new Panel
            {
                BackColor = Color.FromArgb(28, 33, 45),
                Location = new Point(22, 82),
                Size = new Size(716, 198)
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

            Panel pnlDivider = new Panel
            {
                BackColor = Color.FromArgb(46, 54, 72),
                Location = new Point(14, 152),
                Size = new Size(688, 1)
            };

            chkDeblur = new CheckBox
            {
                Text = "Kèm Bỏ làm mờ khi cài (Mặc định Tắt)",
                Checked = false,
                Location = new Point(14, 163),
                Size = new Size(310, 22),
                ForeColor = Color.FromArgb(200, 210, 230)
            };
            lblDeblurStatus = new Label
            {
                Text = "Bỏ làm mờ: ...",
                Location = new Point(328, 163),
                Size = new Size(220, 22),
                TextAlign = ContentAlignment.MiddleRight,
                ForeColor = Color.FromArgb(160, 175, 200)
            };
            btnDeblurToggle = MakeButton("Bật Bỏ làm mờ", new Point(558, 159), new Size(144, 28), Color.FromArgb(52, 62, 84));
            btnDeblurToggle.Click += (s, e) => ToggleDeblurAsync();

            pnlPaths.Controls.AddRange(new Control[] {
                l1, lblGameStatus, txtGamePath, btnBrowseGame,
                l2, lblLauncherStatus, txtLauncherPath, btnBrowseLauncher,
                chkShortcut, chkAutoLaunch, pnlDivider, chkDeblur, lblDeblurStatus, btnDeblurToggle
            });

            // Action Buttons
            btnInstall = MakeButton("Cài đặt / Cập nhật Việt hóa", new Point(22, 290), new Size(250, 42), Color.FromArgb(35, 122, 220));
            btnInstall.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            btnInstall.Click += (s, e) => StartInstallOrUpdate();

            btnRestore = MakeButton("Khôi phục bản gốc", new Point(282, 290), new Size(155, 42), Color.FromArgb(135, 62, 62));
            btnRestore.Click += (s, e) => StartRestore();

            btnVerify = MakeButton("Kiểm tra CRC", new Point(447, 290), new Size(125, 42), Color.FromArgb(55, 68, 92));
            btnVerify.Click += (s, e) => StartVerify();

            btnLaunch = MakeButton("Mở Launcher", new Point(582, 290), new Size(156, 42), Color.FromArgb(38, 138, 96));
            btnLaunch.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            btnLaunch.Click += (s, e) => LaunchGame();

            Controls.AddRange(new Control[] { btnInstall, btnRestore, btnVerify, btnLaunch });

            progressBar = new ProgressBar { Location = new Point(22, 344), Size = new Size(716, 18), Style = ProgressBarStyle.Continuous };
            lblProgress = new Label { Text = "Sẵn sàng.", Location = new Point(22, 365), Size = new Size(716, 20), ForeColor = Color.FromArgb(170, 185, 210) };
            Controls.Add(progressBar);
            Controls.Add(lblProgress);

            txtLog = new TextBox
            {
                Location = new Point(22, 390),
                Size = new Size(716, 256),
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
            btnDeblurToggle.Enabled = !busy;
            chkDeblur.Enabled = !busy;
            if (!string.IsNullOrEmpty(status)) lblProgress.Text = status;
        }

        private void RefreshLocalStatuses()
        {
            string g = txtGamePath.Text.Trim();
            string l = txtLauncherPath.Text.Trim();
            string gs = Helpers.CheckGameStatus(_packRoot, g);
            string ls = Helpers.CheckLauncherStatus(_packRoot, l);
            string ds = Helpers.CheckDeblurStatus(_packRoot, g);
            lblGameStatus.Text = gs;
            lblGameStatus.ForeColor = gs.IndexOf("Đã cài") >= 0 ? Color.FromArgb(110, 235, 160) :
                                      gs.IndexOf("Chưa tìm") >= 0 || gs.IndexOf("chờ patch") >= 0 ? Color.FromArgb(255, 195, 95) :
                                      Color.FromArgb(160, 210, 255);
            lblLauncherStatus.Text = ls;
            lblLauncherStatus.ForeColor = ls.IndexOf("Đã cài") >= 0 ? Color.FromArgb(110, 235, 160) : Color.FromArgb(160, 210, 255);

            bool deblurOn = ds.IndexOf("Đang BẬT") >= 0;
            lblDeblurStatus.Text = "Bỏ làm mờ: " + ds;
            lblDeblurStatus.ForeColor = deblurOn ? Color.FromArgb(255, 200, 100) :
                                        ds.IndexOf("Đang TẮT") >= 0 ? Color.FromArgb(145, 215, 175) :
                                        Color.FromArgb(170, 185, 210);
            btnDeblurToggle.Text = deblurOn ? "Tắt Bỏ làm mờ" : "Bật Bỏ làm mờ";
            btnDeblurToggle.BackColor = deblurOn ? Color.FromArgb(175, 98, 38) : Color.FromArgb(52, 62, 84);
        }

        private void UpdateHeaderLabel(string gameStatus)
        {
            string gameVerDesc;
            if (!string.IsNullOrEmpty(gameStatus) && gameStatus.IndexOf("Đã cài") >= 0)
            {
                gameVerDesc = !string.IsNullOrEmpty(_localVersion) ? _localVersion : Config.CurrentInstallerVersion;
            }
            else if (!string.IsNullOrEmpty(gameStatus) && (gameStatus.IndexOf("File không khớp") >= 0 || gameStatus.IndexOf("Cài dở dang") >= 0))
            {
                gameVerDesc = string.IsNullOrEmpty(_state.installed_version)
                    ? "bản cũ (cần cập nhật)"
                    : (_state.installed_version + " (cần cập nhật)");
            }
            else
            {
                gameVerDesc = "chưa cài";
            }

            if (_remote != null && !string.IsNullOrEmpty(_remote.version))
            {
                bool upToDate = (!string.IsNullOrEmpty(gameStatus) && gameStatus.IndexOf("Đã cài") >= 0)
                                && _localVersion == _remote.version
                                && Config.CurrentInstallerVersion == _remote.version;
                string updateNote = upToDate ? " (Đã mới nhất)" : " (CÓ BẢN MỚI!)";
                lblVersionInfo.Text = string.Format("App: {0}  |  Trong game: {1}  |  GitHub: {2}{3}",
                    Config.CurrentInstallerVersion, gameVerDesc, _remote.version, updateNote);
            }
            else
            {
                lblVersionInfo.Text = string.Format("App: {0}  |  Trong game: {1}  |  Đang check GitHub...",
                    Config.CurrentInstallerVersion, gameVerDesc);
            }
        }

        private void RefreshStateAndCheckAsync(bool fetchOnline)
        {
            string detectedVer;
            _packRoot = Helpers.FindPayloadPackRoot(out detectedVer);
            Helpers.SyncInstalledExe(_packRoot);
            if (string.IsNullOrEmpty(txtGamePath.Text))
                txtGamePath.Text = Helpers.FindJpGameRoot(_state.jp_game_path);
            if (string.IsNullOrEmpty(txtLauncherPath.Text))
                txtLauncherPath.Text = Helpers.FindJpLauncherRoot(_state.jp_launcher_path, txtGamePath.Text);
            RefreshLocalStatuses();

            if (lblGameStatus.Text.IndexOf("Đã cài") >= 0)
            {
                _localVersion = !string.IsNullOrEmpty(detectedVer) ? detectedVer : Config.CurrentInstallerVersion;
                if (_state.installed_version != _localVersion)
                {
                    _state.installed_version = _localVersion;
                    Helpers.SaveState(_state);
                }
            }
            else
            {
                _localVersion = "";
            }
            UpdateHeaderLabel(lblGameStatus.Text);

            if (!fetchOnline) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    RemoteRelease rr = Helpers.FetchLatestRelease(8000);
                    _remote = rr;
                    BeginInvoke(new Action(() =>
                    {
                        UpdateHeaderLabel(lblGameStatus.Text);
                        Log("Đã kiểm tra GitHub (" + rr.source + "): bản mới nhất = " + rr.version +
                            (string.IsNullOrEmpty(rr.jp_resource_version) ? "" : " (Client JP #" + rr.jp_resource_version + ")"));
                    }));
                }
                catch (Exception ex)
                {
                    BeginInvoke(new Action(() =>
                    {
                        string localTxt = string.IsNullOrEmpty(_packRoot) ? "Chưa có payload" : "Payload cục bộ sẵn sàng";
                        lblVersionInfo.Text = string.Format("App: {0}  |  {1} (Offline)", Config.CurrentInstallerVersion, localTxt);
                        Log("Không kiểm tra được GitHub (sẽ dùng gói cục bộ nếu có): " + ex.Message);
                    }));
                }
            });
        }

        private string EnsurePackageAvailable()
        {
            return EnsurePackageAvailable(false);
        }

        private string EnsurePackageAvailable(bool requireDeblur)
        {
            string localVer;
            string localRoot = Helpers.FindPayloadPackRoot(out localVer);
            bool needDownload = string.IsNullOrEmpty(localRoot);

            if (requireDeblur && !string.IsNullOrEmpty(localRoot) && !Helpers.HasDeblurPayload(localRoot))
            {
                needDownload = true;
            }

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
                    if (!string.IsNullOrEmpty(localRoot) && (!requireDeblur || Helpers.HasDeblurPayload(localRoot)))
                    {
                        Log("Lỗi tải online (" + ex.Message + "), quay lại dùng gói cục bộ.");
                        return localRoot;
                    }
                    throw new Exception("Không tìm thấy gói payload-vi cục bộ và không tải được từ GitHub: " + ex.Message);
                }
            }

            if (string.IsNullOrEmpty(_remote.full_zip_url))
            {
                if (!string.IsNullOrEmpty(localRoot) && (!requireDeblur || Helpers.HasDeblurPayload(localRoot))) return localRoot;
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

        private void ToggleDeblurAsync()
        {
            if (_busy) return;
            string gameDir = txtGamePath.Text.Trim();
            if (string.IsNullOrEmpty(gameDir) || !Directory.Exists(Path.Combine(gameDir, "AzurPromiliaJP_Data")))
            {
                MessageBox.Show("Chưa tìm thấy thư mục AZUPRO_JP để bật/tắt Bỏ làm mờ!", "Thiếu đường dẫn", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            string curStatus = Helpers.CheckDeblurStatus(_packRoot, gameDir);
            bool currentlyOn = curStatus.IndexOf("Đang BẬT") >= 0;

            if (!currentlyOn)
            {
                if (MessageBox.Show(
                    "Bật tính năng Bỏ làm mờ (Deblur) cho Azur Promilia JP?\n\n" +
                    "• Tắt hiệu ứng làm mờ/ẩn nhân vật khi zoom sát hoặc xoay góc camera từ dưới lên (4 file .r, giữ nguyên dung lượng & CRC32).\n" +
                    "• Tính năng này mặc định TẮT để an toàn tối đa; bạn có thể bấm nút 'Tắt Bỏ làm mờ' bất kỳ lúc nào để khôi phục 4 file gốc.",
                    "Xác nhận Bật Bỏ làm mờ (Deblur)", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                {
                    return;
                }
            }
            else
            {
                if (MessageBox.Show(
                    "Tắt Bỏ làm mờ (Deblur) và khôi phục lại 4 file gốc của JP Game?",
                    "Xác nhận Tắt Bỏ làm mờ", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                {
                    return;
                }
            }

            SetBusy(true, currentlyOn ? "Đang tắt Bỏ làm mờ (khôi phục 4 file gốc)..." : "Đang bật Bỏ làm mờ (Deblur)...");
            progressBar.Value = 0;

            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    bool hasScriptOnly = !string.IsNullOrEmpty(_packRoot)
                        && File.Exists(Path.Combine(_packRoot, "tools", "Apply-JPDeblur.ps1"))
                        && File.Exists(Path.Combine(_packRoot, "tools", "jp-deblur-deployment.json"));
                    string packRoot = (currentlyOn && hasScriptOnly) ? _packRoot : EnsurePackageAvailable(true);
                    string deblurScript = Path.Combine(packRoot, "tools", "Apply-JPDeblur.ps1");
                    if (!File.Exists(deblurScript))
                        throw new Exception("Gói Việt hóa hiện tại không chứa Apply-JPDeblur.ps1. Vui lòng cập nhật lên bản mới nhất.");

                    bool needAdmin = !Helpers.CanWriteDir(Path.Combine(gameDir, "AzurPromiliaJP_Data"));
                    if (needAdmin && !Helpers.IsAdmin())
                        Log("Thư mục game cần quyền Quản trị viên (UAC)...");

                    string act = currentlyOn ? "Restore" : "Apply";
                    Log((currentlyOn ? "Đang TẮT" : "Đang BẬT") + " Bỏ làm mờ (Apply-JPDeblur.ps1 -Action " + act + ")...");
                    int rc = Helpers.RunPsScript(
                        deblurScript,
                        "-Action " + act + " -Language vi -Hint \"" + gameDir + "\"",
                        Log, needAdmin && !Helpers.IsAdmin()
                    );
                    if (rc != 0) throw new Exception("Apply-JPDeblur.ps1 thất bại với mã " + rc);

                    BeginInvoke(new Action(() =>
                    {
                        progressBar.Value = 100;
                        RefreshLocalStatuses();
                        string msg = currentlyOn ? "Đã TẮT Bỏ làm mờ (khôi phục 4 file gốc)!" : "Đã BẬT Bỏ làm mờ (Deblur) thành công!";
                        SetBusy(false, msg);
                        MessageBox.Show(msg, "Hoàn tất", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }));
                }
                catch (Exception ex)
                {
                    Log("[LỖI Deblur] " + ex.Message);
                    BeginInvoke(new Action(() =>
                    {
                        RefreshLocalStatuses();
                        SetBusy(false, "Thao tác Bỏ làm mờ thất bại.");
                        MessageBox.Show("Lỗi: " + ex.Message, "Thất bại", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }));
                }
            });
        }

        private void StartInstallOrUpdate()
        {
            if (_busy) return;
            string gameDir = txtGamePath.Text.Trim();
            string launcherDir = txtLauncherPath.Text.Trim();
            bool applyDeblur = chkDeblur.Checked;
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
                    string packRoot = EnsurePackageAvailable(applyDeblur);
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

                        if (applyDeblur && File.Exists(Path.Combine(packRoot, "tools", "Apply-JPDeblur.ps1")))
                        {
                            Log("Đang áp dụng Bỏ làm mờ (Deblur - tùy chọn người dùng bật)...");
                            int drc = Helpers.RunPsScript(
                                Path.Combine(packRoot, "tools", "Apply-JPDeblur.ps1"),
                                "-Action Apply -Language vi -Hint \"" + gameDir + "\"",
                                Log, needAdmin && !Helpers.IsAdmin()
                            );
                            if (drc != 0) throw new Exception("Apply-JPDeblur.ps1 thất bại với mã " + drc);
                        }
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

                    string installedExe = Helpers.SyncInstalledExe(packRoot);
                    string packVer = Helpers.DetectVersionInDir(packRoot, Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));
                    string appliedVer = !string.IsNullOrEmpty(packVer) ? packVer
                        : (_remote != null && !string.IsNullOrEmpty(_remote.version) ? _remote.version : Config.CurrentInstallerVersion);

                    _localVersion = appliedVer;
                    _state.installed_version = appliedVer;
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
                        UpdateHeaderLabel(lblGameStatus.Text);
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

                        string deblurScript = Path.Combine(_packRoot, "tools", "Apply-JPDeblur.ps1");
                        if (File.Exists(deblurScript) && Helpers.CheckDeblurStatus(_packRoot, gameDir).IndexOf("Đang TẮT") < 0)
                        {
                            Log("Đang khôi phục 4 file Bỏ làm mờ (nếu có)...");
                            Helpers.RunPsScript(deblurScript, "-Action Restore -Language vi -Hint \"" + gameDir + "\"", Log, needAdmin && !Helpers.IsAdmin());
                        }
                    }
                    if (!string.IsNullOrEmpty(launcherDir))
                    {
                        int rc = Helpers.RunPsScript(Path.Combine(_packRoot, "tools", "Apply-Launchers.ps1"),
                            "-Action Restore -Target jp_launcher -Language vi -Hint \"" + launcherDir + "\"", Log, needAdmin && !Helpers.IsAdmin());
                        if (rc != 0) throw new Exception("Restore JP Launcher lỗi mã " + rc);
                    }
                    _localVersion = "";
                    _state.installed_version = "";
                    Helpers.SaveState(_state);
                    BeginInvoke(new Action(() =>
                    {
                        RefreshLocalStatuses();
                        UpdateHeaderLabel(lblGameStatus.Text);
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
                    {
                        Helpers.RunPsScript(Path.Combine(_packRoot, "tools", "Apply-JPCRCZH.ps1"),
                            "-Action Verify -Language vi -Hint \"" + gameDir + "\"", Log, false);
                        string deblurScript = Path.Combine(_packRoot, "tools", "Apply-JPDeblur.ps1");
                        if (File.Exists(deblurScript))
                            Helpers.RunPsScript(deblurScript, "-Action Verify -Language vi -Hint \"" + gameDir + "\"", Log, false);
                    }
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
                            Helpers.SyncInstalledExe(newPack);
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
