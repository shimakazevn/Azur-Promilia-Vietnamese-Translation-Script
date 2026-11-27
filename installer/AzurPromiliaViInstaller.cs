using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using WF = System.Windows.Forms;

[assembly: AssemblyTitle("Azur Promilia VI Installer & Auto-Updater")]
[assembly: AssemblyDescription("Bo cai dat & tu dong cap nhat Viet hoa Azur Promilia (JP)")]
[assembly: AssemblyCompany("shimakazevn")]
[assembly: AssemblyProduct("AzurPromilia-VI-Setup")]
[assembly: AssemblyVersion("1.0.12.0")]
[assembly: AssemblyFileVersion("1.0.12.0")]

namespace AzurPromiliaVIInstaller
{
    internal static class Config
    {
        public const string RepoSlug = "shimakazevn/Azur-Promilia-Vietnamese-Translation-Script";
        public const string ReleaseLatestJsonUrl = "https://github.com/" + RepoSlug + "/releases/latest/download/latest-vi.json";
        public const string LatestJsonUrl = "https://raw.githubusercontent.com/" + RepoSlug + "/main/latest-vi.json";
        public const string ReleasesApiUrl = "https://api.github.com/repos/" + RepoSlug + "/releases/latest";
        public const string CurrentInstallerVersion = "v1.0.12";
        public static readonly string AppDataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AzurPromiliaVI"
        );
        public static readonly string StatePath = Path.Combine(AppDataDir, "state.json");
        public static readonly string CacheRoot = Path.Combine(AppDataDir, "cache");
        public static readonly string MediaRoot = Path.Combine(AppDataDir, "media");
    }

    internal class InstallerState
    {
        public string installed_version = "";
        public string jp_game_path = "";
        public string jp_launcher_path = "";
        public bool auto_update_on_launch = true;
        public bool enable_bgm = true;
        public bool enable_video = true;
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

        public static int CompareVersions(string a, string b)
        {
            int[] pa = ParseVersionParts(a);
            int[] pb = ParseVersionParts(b);
            int max = Math.Max(pa.Length, pb.Length);
            for (int i = 0; i < max; i++)
            {
                int va = i < pa.Length ? pa[i] : 0;
                int vb = i < pb.Length ? pb[i] : 0;
                if (va != vb) return va > vb ? 1 : -1;
            }
            return 0;
        }

        private static int[] ParseVersionParts(string ver)
        {
            if (string.IsNullOrWhiteSpace(ver)) return new int[0];
            string s = ver.Trim();
            if (s.StartsWith("v", StringComparison.OrdinalIgnoreCase)) s = s.Substring(1);
            int dash = s.IndexOf('-');
            if (dash >= 0) s = s.Substring(0, dash);
            string[] tokens = s.Split('.');
            List<int> nums = new List<int>();
            foreach (string tok in tokens)
            {
                int n;
                if (int.TryParse(tok.Trim(), out n)) nums.Add(n);
            }
            return nums.ToArray();
        }

        public static BitmapImage LoadEmbeddedImage(string resourceName)
        {
            try
            {
                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(resourceName))
                {
                    if (s == null) return null;
                    MemoryStream ms = new MemoryStream();
                    s.CopyTo(ms);
                    ms.Position = 0;
                    BitmapImage bmp = new BitmapImage();
                    bmp.BeginInit();
                    bmp.CacheOption = BitmapCacheOption.OnLoad;
                    bmp.StreamSource = ms;
                    bmp.EndInit();
                    bmp.Freeze();
                    ms.Dispose();
                    return bmp;
                }
            }
            catch { return null; }
        }

        public static ImageSource LoadEmbeddedIcon(string resourceName)
        {
            try
            {
                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(resourceName))
                {
                    if (s == null) return null;
                    MemoryStream ms = new MemoryStream();
                    s.CopyTo(ms);
                    ms.Position = 0;
                    BitmapDecoder dec = BitmapDecoder.Create(ms, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
                    if (dec.Frames.Count > 0)
                    {
                        BitmapFrame frame = dec.Frames[0];
                        frame.Freeze();
                        ms.Dispose();
                        return frame;
                    }
                    ms.Dispose();
                }
            }
            catch { }
            return null;
        }

        public static string ExtractEmbeddedMedia(string resourceName, string fileName)
        {
            try
            {
                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(resourceName))
                {
                    if (s == null) return "";
                    Directory.CreateDirectory(Config.MediaRoot);
                    string dest = Path.Combine(Config.MediaRoot, fileName);
                    long expectedLen = s.Length;
                    if (File.Exists(dest))
                    {
                        FileInfo fi = new FileInfo(dest);
                        if (fi.Length == expectedLen) return dest;
                    }
                    string tmp = dest + ".tmp";
                    using (FileStream fs = File.Create(tmp))
                        s.CopyTo(fs);
                    if (File.Exists(dest)) File.Delete(dest);
                    File.Move(tmp, dest);
                    return dest;
                }
            }
            catch { return ""; }
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
                if (orig == files.Count) return "Bản gốc Nhật (Chưa Việt hóa)";
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
                        return "Bản gốc Nhật (Chưa Việt hóa)";
                    object prevObj;
                    if (item.TryGetValue("previous_sha256", out prevObj) && prevObj is IEnumerable)
                    {
                        foreach (object pv in (IEnumerable)prevObj)
                        {
                            if (string.Equals(h, Convert.ToString(pv), StringComparison.OrdinalIgnoreCase))
                                return "Bản Việt hóa cũ (Cần cập nhật)";
                        }
                    }
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

        private static RemoteRelease ParseLatestJson(string raw, string sourceLabel)
        {
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
                source = sourceLabel
            };
            if (doc.ContainsKey("installer") && doc["installer"] is Dictionary<string, object>)
            {
                var inst = (Dictionary<string, object>)doc["installer"];
                rr.installer_url = inst.ContainsKey("url") ? Convert.ToString(inst["url"]) : "";
                rr.installer_sha256 = inst.ContainsKey("sha256") ? Convert.ToString(inst["sha256"]) : "";
            }
            return rr;
        }

        public static RemoteRelease FetchLatestRelease(int timeoutMs)
        {
            InitTls();
            // 1. Try GitHub Release latest asset directly (0-second CDN lag)
            try
            {
                string raw = DownloadString(Config.ReleaseLatestJsonUrl, timeoutMs);
                return ParseLatestJson(raw, "GitHub Release");
            }
            catch { }

            // 2. Fallback to raw latest-vi.json
            try
            {
                string raw = DownloadString(Config.LatestJsonUrl + "?t=" + DateTimeOffset.UtcNow.ToUnixTimeSeconds(), timeoutMs);
                return ParseLatestJson(raw, "latest-vi.json");
            }
            catch { }

            // 3. Fallback to GitHub Releases API
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

        private static readonly string[][] PsLogMap = new[]
        {
            new[] { "通过 [原版定位] ", "Đạt [Bản gốc - Hotfix] " },
            new[] { "通过 [已汉化定位] ", "Đạt [Đã Việt hóa - Hotfix] " },
            new[] { "通过 [原版] ", "Đạt [Bản gốc] " },
            new[] { "通过 [已汉化] ", "Đạt [Đã Việt hóa] " },
            new[] { "通过 ", "Đạt " },
            new[] { "已写入并校验：", "Đã ghi & kiểm tra CRC/SHA256: " },
            new[] { "已写入并校验:", "Đã ghi & kiểm tra CRC/SHA256: " },
            new[] { "完整校验通过，所有只读基线保持原字节。", "Kiểm tra toàn vẹn đạt 100%: toàn bộ file baseline chỉ-đọc đều giữ nguyên từng byte gốc." },
            new[] { "所有文件均已处于目标状态，无需修改。", "Tất cả file đã ở đúng trạng thái mục tiêu, không cần ghi đè." },
            new[] { "Apply 完成。资源大小、段 CRC、整包 CRC 和只读基线均通过。", "Cài đặt hoàn tất: dung lượng, CRC từng đoạn, CRC toàn gói và baseline chỉ-đọc đều đạt." },
            new[] { "Restore 完成。资源大小、段 CRC、整包 CRC 和只读基线均通过。", "Khôi phục hoàn tất: dung lượng, CRC từng đoạn, CRC toàn gói và baseline chỉ-đọc đều đạt." },
            new[] { "载荷通过：", "Gói file hợp lệ: " },
            new[] { "全部载荷通过：大小、SHA256、整包 CRC、全部段 CRC。", "Toàn bộ file Việt hóa đạt chuẩn: dung lượng, SHA-256, CRC toàn file và CRC từng đoạn." },
            new[] { "写入目标目录需要管理员权限，正在请求……", "Cần quyền Quản trị viên (UAC) để ghi thư mục game, đang xin cấp quyền..." },
            new[] { "请先完全退出游戏主程序或启动器：", "Vui lòng đóng hoàn toàn game hoặc Launcher đang chạy: " },
            new[] { "请先完全退出启动器：", "Vui lòng đóng hoàn toàn Launcher đang chạy: " },
            new[] { "请先完全退出游戏主程序：", "Vui lòng đóng hoàn toàn game đang chạy: " },
            new[] { "检测到同名进程 ", "Phát hiện tiến trình trùng tên " },
            new[] { " 但无法读取其路径，将继续执行；若文件被占用将自动回滚。", " nhưng không đọc được đường dẫn; sẽ thử chạy tiếp và tự khôi phục nếu file bị khóa." },
            new[] { "游戏资源版本低于补丁基线：", "Phiên bản tài nguyên game cũ hơn bản nền của patch: " },
            new[] { "文件缺失：", "Thiếu file: " },
            new[] { "游戏文件缺失：", "Thiếu file game: " },
            new[] { "缺少原版备份：", "Thiếu file sao lưu bản gốc: " },
            new[] { "原版备份不匹配：", "File sao lưu bản gốc không khớp: " },
            new[] { "原版只读基线不匹配：", "Game đã cập nhật hoặc file baseline chỉ-đọc không khớp: " },
            new[] { "原版只读基线版本过低：", "Phiên bản game quá cũ so với baseline: " },
            new[] { "原版只读基线缺失：", "Thiếu file baseline chỉ-đọc: " },
            new[] { "文件大小不匹配：", "Dung lượng file không khớp: " },
            new[] { "文件版本不匹配：", "Phiên bản file không khớp: " },
            new[] { "文件既非原版也非本版汉化：", "File không khớp cả bản gốc lẫn bản Việt hóa hiện tại: " },
            new[] { "整包 CRC 不匹配：", "CRC toàn file không khớp: " },
            new[] { "段 CRC 不匹配：", "CRC từng đoạn không khớp: " },
            new[] { "SHA256 不匹配：", "Mã SHA-256 không khớp: " },
            new[] { "目标磁盘剩余空间不足", "Dung lượng trống ổ đĩa không đủ" },
            new[] { "已回滚到操作前：", "Đã tự hoàn tác về trạng thái trước khi sửa: " },
            new[] { "操作失败：", "Thao tác thất bại: " },
            new[] { "补丁载荷目录不存在：", "Không tìm thấy thư mục gói Việt hóa: " },
            new[] { "（请下载 Releases 完整包，勿直接下载源码 ZIP）", " (vui lòng tải bản Full ZIP trong Releases, không tải Source ZIP)." }
        };

        public static string TranslatePsLogLine(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return raw;
            string s = raw;
            if (s.StartsWith("ORIGINAL ", StringComparison.Ordinal))
                return "Launcher đang ở bản gốc Nhật (" + s.Substring("ORIGINAL ".Length).Trim() + ")";
            if (s.StartsWith("LOCALIZED ", StringComparison.Ordinal))
                return "Launcher đã cài Việt hóa (" + s.Substring("LOCALIZED ".Length).Trim() + ")";
            if (s.StartsWith("ALREADY_ORIGINAL ", StringComparison.Ordinal))
                return "Launcher đã ở nguyên bản Nhật, không cần khôi phục.";
            if (s.StartsWith("ALREADY_CURRENT ", StringComparison.Ordinal))
                return "Launcher đã ở bản Việt hóa mới nhất.";
            if (s.StartsWith("APPLY_OK ", StringComparison.Ordinal))
                return "Đã cài Việt hóa Launcher thành công (" + s.Substring("APPLY_OK ".Length).Trim() + ").";
            if (s.StartsWith("RESTORE_OK ", StringComparison.Ordinal))
                return "Đã khôi phục Launcher về bản gốc thành công (" + s.Substring("RESTORE_OK ".Length).Trim() + ").";
            if (s.StartsWith("PAYLOAD_OK ", StringComparison.Ordinal))
                return "Gói Launcher hợp lệ (" + s.Substring("PAYLOAD_OK ".Length).Trim() + ").";

            for (int i = 0; i < PsLogMap.Length; i++)
            {
                if (s.IndexOf(PsLogMap[i][0], StringComparison.Ordinal) >= 0)
                    s = s.Replace(PsLogMap[i][0], PsLogMap[i][1]);
            }
            return s;
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
                    p.OutputDataReceived += (s, e) => { if (e.Data != null && onLog != null) onLog(TranslatePsLogLine(e.Data)); };
                    p.ErrorDataReceived += (s, e) => { if (e.Data != null && onLog != null) onLog("[ERR] " + TranslatePsLogLine(e.Data)); };
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
            string exeDir = Path.GetDirectoryName(setupExePath);
            string psScript =
                "$ws = New-Object -ComObject WScript.Shell; " +
                "$sc = $ws.CreateShortcut('" + lnk.Replace("'", "''") + "'); " +
                "$sc.TargetPath = '" + setupExePath.Replace("'", "''") + "'; " +
                "$sc.Arguments = '--auto-launch'; " +
                "$sc.WorkingDirectory = '" + exeDir.Replace("'", "''") + "'; " +
                "$sc.IconLocation = '" + setupExePath.Replace("'", "''") + ",0'; " +
                "$sc.Description = 'Azur Promilia - Kiem tra cap nhat Viet hoa & Mo game'; " +
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

    internal class LauncherWindow : Window
    {
        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

        private MediaElement _videoBg;
        private MediaPlayer _bgmPlayer;
        private bool _bgmLoaded = false;
        private bool _videoLoaded = false;

        private TextBox _txtGamePath;
        private TextBox _txtLauncherPath;
        private TextBlock _lblGameStatus;
        private TextBlock _lblLauncherStatus;
        private TextBlock _lblDeblurStatus;
        private TextBlock _lblVersionInfo;
        private CheckBox _chkShortcut;
        private CheckBox _chkAutoLaunch;
        private Border _progressTrack;
        private Border _progressFill;
        private TextBlock _lblProgress;
        private TextBox _txtLog;
        private Button _btnInstall;
        private Button _btnCheckUpdate;
        private Button _btnRestore;
        private Button _btnVerify;
        private Button _btnLaunch;
        private Button _btnDeblurToggle;
        private Button _btnBgmToggle;
        private Button _btnVideoToggle;

        private InstallerState _state;
        private string _packRoot = "";
        private string _localVersion = "";
        private RemoteRelease _remote;
        private bool _busy = false;
        private double _progressPct = 0;

        public LauncherWindow()
        {
            _state = Helpers.LoadState();
            InitializeUi();
            SourceInitialized += (s, e) => ApplyWin11WindowChrome();
            ContentRendered += (s, e) =>
            {
                StartMediaAsync();
                RefreshStateAndCheckAsync(true);
            };
            Closed += (s, e) => DisposeMedia();
        }

        private void ApplyWin11WindowChrome()
        {
            try
            {
                IntPtr hwnd = new WindowInteropHelper(this).Handle;
                int dark = 1;
                if (DwmSetWindowAttribute(hwnd, 20, ref dark, sizeof(int)) != 0)
                    DwmSetWindowAttribute(hwnd, 19, ref dark, sizeof(int));
                int cornerPref = 2; // DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
                DwmSetWindowAttribute(hwnd, 33, ref cornerPref, sizeof(int));
                int borderColor = 0x00784828; // DWMWA_BORDER_COLOR = 34 (BGR subtle midnight blue)
                DwmSetWindowAttribute(hwnd, 34, ref borderColor, sizeof(int));
            }
            catch { }
        }

        private void DragWindow(object sender, MouseButtonEventArgs e)
        {
            if (e.LeftButton == MouseButtonState.Pressed)
            {
                try { DragMove(); } catch { }
            }
        }

        private void InitializeUi()
        {
            Title = "Azur Promilia — Cài đặt & Tự động cập nhật Việt hóa (" + Config.CurrentInstallerVersion + ")";
            WindowStyle = WindowStyle.None;
            Width = 910;
            Height = 636;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            ResizeMode = ResizeMode.CanMinimize;
            Background = new SolidColorBrush(Color.FromRgb(14, 17, 26));
            Foreground = new SolidColorBrush(Color.FromRgb(236, 240, 248));
            FontFamily = new FontFamily("Segoe UI");
            FontSize = 12.5;

            ImageSource winIcon = Helpers.LoadEmbeddedIcon("AzurPromiliaVI.app.ico");
            if (winIcon != null) Icon = winIcon;

            Grid root = new Grid { ClipToBounds = true };

            // Layer 0: Crisp embedded 16:9 key art (instant frame 0 + offline fallback)
            ImageSource posterImg = Helpers.LoadEmbeddedImage("AzurPromiliaVI.kv-poster.jpg");
            if (posterImg != null)
            {
                Image imgBg = new Image
                {
                    Source = posterImg,
                    Stretch = Stretch.UniformToFill,
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Top
                };
                imgBg.MouseLeftButtonDown += DragWindow;
                RenderOptions.SetBitmapScalingMode(imgBg, BitmapScalingMode.HighQuality);
                root.Children.Add(imgBg);
            }

            // Layer 1: Live hardware-accelerated MP4 background loop
            _videoBg = new MediaElement
            {
                LoadedBehavior = MediaState.Manual,
                UnloadedBehavior = MediaState.Close,
                IsMuted = true,
                Stretch = Stretch.UniformToFill,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Top,
                Visibility = Visibility.Collapsed
            };
            _videoBg.MouseLeftButtonDown += DragWindow;
            _videoBg.MediaOpened += (s, e) =>
            {
                if (_state.enable_video)
                {
                    _videoBg.Visibility = Visibility.Visible;
                    try { _videoBg.Play(); } catch { }
                }
            };
            _videoBg.MediaEnded += (s, e) =>
            {
                if (_state.enable_video)
                {
                    try
                    {
                        _videoBg.Position = TimeSpan.FromMilliseconds(1);
                        _videoBg.Play();
                    }
                    catch { }
                }
            };
            _videoBg.MediaFailed += (s, e) =>
            {
                _videoBg.Visibility = Visibility.Collapsed;
            };
            root.Children.Add(_videoBg);

            // Layer 2: Atmospheric vignette keeping top character art bright & lower dashboard legible
            LinearGradientBrush scrim = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1)
            };
            scrim.GradientStops.Add(new GradientStop(Color.FromArgb(42, 8, 10, 18), 0.00));
            scrim.GradientStops.Add(new GradientStop(Color.FromArgb(6, 8, 10, 18), 0.28));
            scrim.GradientStops.Add(new GradientStop(Color.FromArgb(135, 11, 14, 24), 0.45));
            scrim.GradientStops.Add(new GradientStop(Color.FromArgb(222, 12, 16, 28), 0.64));
            scrim.GradientStops.Add(new GradientStop(Color.FromArgb(245, 10, 13, 22), 1.00));
            root.Children.Add(new System.Windows.Shapes.Rectangle { Fill = scrim, IsHitTestVisible = false });

            // Layer 3: Foreground Dashboard
            Grid layout = new Grid { Margin = new Thickness(18, 14, 18, 14) };
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });              // Top HUD bar
            layout.RowDefinitions.Add(new RowDefinition { Height = new GridLength(172) });         // Hero art showcase + drag zone
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });              // Frosted paths + deblur card
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });              // Action buttons
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });              // Gold launcher progress bar
            layout.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) }); // Console log

            // --- Row 0: Top HUD Overlay ---
            Grid topBar = new Grid();
            topBar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            topBar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            topBar.MouseLeftButtonDown += DragWindow;

            Border titlePill = new Border
            {
                Background = new SolidColorBrush(Color.FromArgb(182, 11, 15, 26)),
                BorderBrush = new SolidColorBrush(Color.FromArgb(80, 120, 200, 255)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(9),
                Padding = new Thickness(11, 5, 12, 5),
                HorizontalAlignment = HorizontalAlignment.Left,
                Effect = new DropShadowEffect { Color = Colors.Black, BlurRadius = 12, ShadowDepth = 2, Opacity = 0.55 }
            };
            titlePill.MouseLeftButtonDown += DragWindow;
            StackPanel titleStack = new StackPanel();
            titleStack.Children.Add(new TextBlock
            {
                Text = "AZUR PROMILIA — VIỆT HÓA TIẾNG VIỆT (JP CLIENT) · " + Config.CurrentInstallerVersion,
                FontSize = 14,
                FontWeight = FontWeights.Bold,
                Foreground = new SolidColorBrush(Color.FromRgb(126, 214, 255))
            });
            _lblVersionInfo = new TextBlock
            {
                Text = "App: " + Config.CurrentInstallerVersion + "  |  Đang kiểm tra trạng thái & GitHub...",
                FontSize = 11.2,
                Margin = new Thickness(0, 2, 0, 0),
                Foreground = new SolidColorBrush(Color.FromRgb(212, 222, 240))
            };
            titleStack.Children.Add(_lblVersionInfo);
            titlePill.Child = titleStack;
            Grid.SetColumn(titlePill, 0);
            topBar.Children.Add(titlePill);

            StackPanel hudPills = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                VerticalAlignment = VerticalAlignment.Top,
                HorizontalAlignment = HorizontalAlignment.Right
            };
            _btnBgmToggle = MakeButton(_state.enable_bgm ? "🔊 Nhạc: BẬT" : "🔇 Nhạc: TẮT", 104, 30,
                Color.FromArgb(196, 16, 22, 36), Color.FromArgb(196, 12, 16, 28), Color.FromArgb(90, 255, 255, 255), false);
            _btnBgmToggle.Margin = new Thickness(0, 0, 6, 0);
            _btnBgmToggle.Click += (s, e) => ToggleBgm();

            _btnVideoToggle = MakeButton(_state.enable_video ? "🎬 Động" : "🖼️ Tĩnh", 78, 30,
                Color.FromArgb(196, 16, 22, 36), Color.FromArgb(196, 12, 16, 28), Color.FromArgb(90, 255, 255, 255), false);
            _btnVideoToggle.Margin = new Thickness(0, 0, 6, 0);
            _btnVideoToggle.Click += (s, e) => ToggleVideo();

            _btnCheckUpdate = MakeButton("Cập nhật", 84, 30,
                Color.FromArgb(215, 24, 52, 92), Color.FromArgb(215, 18, 38, 68), Color.FromArgb(115, 110, 195, 255), false);
            _btnCheckUpdate.Margin = new Thickness(0, 0, 8, 0);
            _btnCheckUpdate.Click += (s, e) => RefreshStateAndCheckAsync(true);

            Button btnMin = MakeButton("—", 32, 30,
                Color.FromArgb(196, 18, 24, 38), Color.FromArgb(196, 12, 16, 28), Color.FromArgb(85, 255, 255, 255), false);
            btnMin.Margin = new Thickness(0, 0, 5, 0);
            btnMin.Click += (s, e) => { WindowState = WindowState.Minimized; };

            Button btnClose = MakeButton("✕", 32, 30,
                Color.FromArgb(210, 140, 42, 46), Color.FromArgb(210, 108, 30, 34), Color.FromArgb(110, 255, 130, 130), true);
            btnClose.Click += (s, e) => Close();

            hudPills.Children.Add(_btnBgmToggle);
            hudPills.Children.Add(_btnVideoToggle);
            hudPills.Children.Add(_btnCheckUpdate);
            hudPills.Children.Add(btnMin);
            hudPills.Children.Add(btnClose);
            Grid.SetColumn(hudPills, 1);
            topBar.Children.Add(hudPills);

            Grid.SetRow(topBar, 0);
            layout.Children.Add(topBar);

            // Transparent drag catcher over Row 1 open hero showcase
            Border heroDrag = new Border { Background = Brushes.Transparent };
            heroDrag.MouseLeftButtonDown += DragWindow;
            Grid.SetRow(heroDrag, 1);
            layout.Children.Add(heroDrag);

            // --- Row 2: Frosted Glass Paths & Settings Card ---
            Border card = new Border
            {
                Background = new SolidColorBrush(Color.FromArgb(204, 16, 21, 34)),
                BorderBrush = new SolidColorBrush(Color.FromArgb(72, 185, 215, 255)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(10),
                Padding = new Thickness(14, 10, 14, 10),
                Effect = new DropShadowEffect { Color = Colors.Black, BlurRadius = 18, ShadowDepth = 4, Opacity = 0.6 }
            };
            Grid cardGrid = new Grid();
            for (int i = 0; i < 7; i++)
                cardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            // Game Path Row
            cardGrid.Children.Add(BuildLabelStatusRow("Thư mục Game JP (AZUPRO_JP):", out _lblGameStatus, 0));
            Grid gameInputRow = BuildPathInputRow(out _txtGamePath, true, 1);
            cardGrid.Children.Add(gameInputRow);

            // Launcher Path Row
            Grid l2Row = BuildLabelStatusRow("Thư mục Launcher JP (AZUPRO_JP_Gamelauncher):", out _lblLauncherStatus, 2);
            l2Row.Margin = new Thickness(0, 8, 0, 3);
            cardGrid.Children.Add(l2Row);
            Grid launcherInputRow = BuildPathInputRow(out _txtLauncherPath, false, 3);
            cardGrid.Children.Add(launcherInputRow);

            // Options Checkboxes
            Grid optRow = new Grid { Margin = new Thickness(0, 8, 0, 6) };
            optRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            optRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            _chkShortcut = new CheckBox
            {
                Content = "Tạo shortcut Desktop \"Azur Promilia (Việt Hóa)\"",
                IsChecked = true,
                Foreground = new SolidColorBrush(Color.FromRgb(215, 224, 242)),
                VerticalContentAlignment = VerticalAlignment.Center
            };
            _chkAutoLaunch = new CheckBox
            {
                Content = "Tự kiểm tra & cập nhật khi mở Launcher",
                IsChecked = _state.auto_update_on_launch,
                Foreground = new SolidColorBrush(Color.FromRgb(215, 224, 242)),
                VerticalContentAlignment = VerticalAlignment.Center
            };
            Grid.SetColumn(_chkShortcut, 0);
            Grid.SetColumn(_chkAutoLaunch, 1);
            optRow.Children.Add(_chkShortcut);
            optRow.Children.Add(_chkAutoLaunch);
            Grid.SetRow(optRow, 4);
            cardGrid.Children.Add(optRow);

            // Divider
            Border div = new Border
            {
                Height = 1,
                Background = new SolidColorBrush(Color.FromArgb(52, 255, 255, 255)),
                Margin = new Thickness(0, 2, 0, 7)
            };
            Grid.SetRow(div, 5);
            cardGrid.Children.Add(div);

            // Deblur Row (Default OFF — single clean toggle button)
            Grid deblurRow = new Grid();
            deblurRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            deblurRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            deblurRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            TextBlock lblDeblurHint = new TextBlock
            {
                Text = "Bỏ làm mờ (Tắt hiệu ứng mờ khi zoom sát, mặc định Tắt):",
                Foreground = new SolidColorBrush(Color.FromRgb(200, 212, 232)),
                VerticalAlignment = VerticalAlignment.Center
            };
            _lblDeblurStatus = new TextBlock
            {
                Text = "...",
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(10, 0, 12, 0),
                Foreground = new SolidColorBrush(Color.FromRgb(170, 185, 210))
            };
            _btnDeblurToggle = MakeButton("Bật Bỏ làm mờ", 142, 27,
                Color.FromRgb(52, 62, 84), Color.FromRgb(42, 50, 70), Color.FromArgb(65, 255, 255, 255), false);
            _btnDeblurToggle.Click += (s, e) => ToggleDeblurAsync();

            Grid.SetColumn(lblDeblurHint, 0);
            Grid.SetColumn(_lblDeblurStatus, 1);
            Grid.SetColumn(_btnDeblurToggle, 2);
            deblurRow.Children.Add(lblDeblurHint);
            deblurRow.Children.Add(_lblDeblurStatus);
            deblurRow.Children.Add(_btnDeblurToggle);
            Grid.SetRow(deblurRow, 6);
            cardGrid.Children.Add(deblurRow);

            card.Child = cardGrid;
            Grid.SetRow(card, 2);
            layout.Children.Add(card);

            // --- Row 3: Action Buttons ---
            Grid actGrid = new Grid { Margin = new Thickness(0, 10, 0, 8) };
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(2.2, GridUnitType.Star) });
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(10) });
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.4, GridUnitType.Star) });
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(10) });
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.15, GridUnitType.Star) });
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(10) });
            actGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.45, GridUnitType.Star) });

            _btnInstall = MakeButton("Cài đặt / Cập nhật Việt hóa", 0, 39,
                Color.FromRgb(42, 138, 245), Color.FromRgb(25, 96, 198), Color.FromArgb(95, 135, 215, 255), true);
            _btnInstall.FontSize = 13.5;
            _btnInstall.Click += (s, e) => StartInstallOrUpdate();

            _btnRestore = MakeButton("Khôi phục bản gốc", 0, 39,
                Color.FromRgb(148, 60, 62), Color.FromRgb(116, 42, 44), Color.FromArgb(75, 255, 160, 160), false);
            _btnRestore.Click += (s, e) => StartRestore();

            _btnVerify = MakeButton("Kiểm tra CRC", 0, 39,
                Color.FromRgb(56, 70, 96), Color.FromRgb(42, 53, 75), Color.FromArgb(65, 200, 220, 255), false);
            _btnVerify.Click += (s, e) => StartVerify();

            _btnLaunch = MakeButton("Mở Launcher", 0, 39,
                Color.FromRgb(40, 152, 102), Color.FromRgb(26, 118, 78), Color.FromArgb(85, 130, 245, 185), true);
            _btnLaunch.FontSize = 13.5;
            _btnLaunch.Click += (s, e) => LaunchGame();

            Grid.SetColumn(_btnInstall, 0);
            Grid.SetColumn(_btnRestore, 2);
            Grid.SetColumn(_btnVerify, 4);
            Grid.SetColumn(_btnLaunch, 6);
            actGrid.Children.Add(_btnInstall);
            actGrid.Children.Add(_btnRestore);
            actGrid.Children.Add(_btnVerify);
            actGrid.Children.Add(_btnLaunch);
            Grid.SetRow(actGrid, 3);
            layout.Children.Add(actGrid);

            // --- Row 4: Official-Launcher-Style Gold Progress Bar + Status ---
            StackPanel progWrap = new StackPanel { Margin = new Thickness(0, 0, 0, 8) };
            _lblProgress = new TextBlock
            {
                Text = "Sẵn sàng.",
                FontSize = 11.5,
                Margin = new Thickness(2, 0, 0, 4),
                Foreground = new SolidColorBrush(Color.FromRgb(205, 218, 240))
            };
            _progressTrack = new Border
            {
                Height = 8,
                CornerRadius = new CornerRadius(4),
                Background = new SolidColorBrush(Color.FromArgb(50, 255, 255, 255)),
                ClipToBounds = true
            };
            LinearGradientBrush goldFill = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(1, 0)
            };
            goldFill.GradientStops.Add(new GradientStop(Color.FromRgb(236, 186, 36), 0.0));
            goldFill.GradientStops.Add(new GradientStop(Color.FromRgb(252, 222, 92), 1.0));
            _progressFill = new Border
            {
                Height = 8,
                Width = 0,
                CornerRadius = new CornerRadius(4),
                HorizontalAlignment = HorizontalAlignment.Left,
                Background = goldFill
            };
            _progressTrack.Child = _progressFill;
            _progressTrack.SizeChanged += (s, e) => ApplyProgressWidth();

            progWrap.Children.Add(_lblProgress);
            progWrap.Children.Add(_progressTrack);
            Grid.SetRow(progWrap, 4);
            layout.Children.Add(progWrap);

            // --- Row 5: Log Console ---
            _txtLog = new TextBox
            {
                IsReadOnly = true,
                AcceptsReturn = true,
                TextWrapping = TextWrapping.Wrap,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Background = new SolidColorBrush(Color.FromArgb(224, 10, 12, 19)),
                Foreground = new SolidColorBrush(Color.FromRgb(215, 224, 242)),
                BorderBrush = new SolidColorBrush(Color.FromArgb(52, 255, 255, 255)),
                BorderThickness = new Thickness(1),
                Padding = new Thickness(8, 6, 8, 6),
                FontFamily = new FontFamily("Consolas"),
                FontSize = 11.5
            };
            Grid.SetRow(_txtLog, 5);
            layout.Children.Add(_txtLog);

            root.Children.Add(layout);
            Content = root;
        }

        private Grid BuildLabelStatusRow(string labelText, out TextBlock statusBlock, int rowIdx)
        {
            Grid g = new Grid { Margin = new Thickness(0, 0, 0, 3) };
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            TextBlock lbl = new TextBlock
            {
                Text = labelText,
                Foreground = new SolidColorBrush(Color.FromRgb(190, 204, 228)),
                VerticalAlignment = VerticalAlignment.Center
            };
            statusBlock = new TextBlock
            {
                Text = "...",
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(Color.FromRgb(120, 230, 160))
            };
            Grid.SetColumn(lbl, 0);
            Grid.SetColumn(statusBlock, 1);
            g.Children.Add(lbl);
            g.Children.Add(statusBlock);
            Grid.SetRow(g, rowIdx);
            return g;
        }

        private Grid BuildPathInputRow(out TextBox box, bool isGame, int rowIdx)
        {
            Grid g = new Grid();
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(8) });
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            box = new TextBox
            {
                Height = 27,
                VerticalContentAlignment = VerticalAlignment.Center,
                Padding = new Thickness(7, 0, 7, 0),
                Background = new SolidColorBrush(Color.FromArgb(228, 12, 15, 24)),
                Foreground = Brushes.White,
                BorderBrush = new SolidColorBrush(Color.FromArgb(72, 160, 188, 230)),
                BorderThickness = new Thickness(1)
            };
            TextBox capturedBox = box;
            Button btnBrowse = MakeButton("Chọn...", 82, 27,
                Color.FromRgb(52, 62, 84), Color.FromRgb(42, 50, 70), Color.FromArgb(65, 255, 255, 255), false);
            btnBrowse.Click += (s, e) => BrowseFolder(capturedBox, isGame);

            Grid.SetColumn(box, 0);
            Grid.SetColumn(btnBrowse, 2);
            g.Children.Add(box);
            g.Children.Add(btnBrowse);
            Grid.SetRow(g, rowIdx);
            return g;
        }

        private static Button MakeButton(string text, double width, double height, Color topBg, Color botBg, Color borderColor, bool bold)
        {
            LinearGradientBrush grad = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1)
            };
            grad.GradientStops.Add(new GradientStop(topBg, 0.0));
            grad.GradientStops.Add(new GradientStop(botBg, 1.0));

            Color hoverTop = Color.FromArgb(topBg.A,
                (byte)Math.Min(255, topBg.R + 22),
                (byte)Math.Min(255, topBg.G + 22),
                (byte)Math.Min(255, topBg.B + 22));
            Color hoverBot = Color.FromArgb(botBg.A,
                (byte)Math.Min(255, botBg.R + 18),
                (byte)Math.Min(255, botBg.G + 18),
                (byte)Math.Min(255, botBg.B + 18));
            LinearGradientBrush hoverGrad = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1)
            };
            hoverGrad.GradientStops.Add(new GradientStop(hoverTop, 0.0));
            hoverGrad.GradientStops.Add(new GradientStop(hoverBot, 1.0));

            FrameworkElementFactory borderFactory = new FrameworkElementFactory(typeof(Border), "bd");
            borderFactory.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Control.BackgroundProperty));
            borderFactory.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(Control.BorderBrushProperty));
            borderFactory.SetValue(Border.BorderThicknessProperty, new TemplateBindingExtension(Control.BorderThicknessProperty));
            borderFactory.SetValue(Border.CornerRadiusProperty, new CornerRadius(7));

            FrameworkElementFactory contentFactory = new FrameworkElementFactory(typeof(ContentPresenter));
            contentFactory.SetValue(ContentPresenter.HorizontalAlignmentProperty, HorizontalAlignment.Center);
            contentFactory.SetValue(ContentPresenter.VerticalAlignmentProperty, VerticalAlignment.Center);
            contentFactory.SetValue(ContentPresenter.MarginProperty, new Thickness(8, 0, 8, 0));
            borderFactory.AppendChild(contentFactory);

            ControlTemplate tpl = new ControlTemplate(typeof(Button));
            tpl.VisualTree = borderFactory;

            Trigger trigHover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            trigHover.Setters.Add(new Setter(Border.BackgroundProperty, hoverGrad, "bd"));
            tpl.Triggers.Add(trigHover);

            Trigger trigDisabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
            trigDisabled.Setters.Add(new Setter(UIElement.OpacityProperty, 0.48, "bd"));
            tpl.Triggers.Add(trigDisabled);

            Button b = new Button
            {
                Content = text,
                Height = height,
                Background = grad,
                Foreground = Brushes.White,
                BorderBrush = new SolidColorBrush(borderColor),
                BorderThickness = new Thickness(1),
                FontWeight = bold ? FontWeights.Bold : FontWeights.SemiBold,
                Cursor = Cursors.Hand,
                Template = tpl
            };
            if (width > 0) b.Width = width;
            return b;
        }

        private void StartMediaAsync()
        {
            ThreadPool.QueueUserWorkItem(_ =>
            {
                string mp4 = Helpers.ExtractEmbeddedMedia("AzurPromiliaVI.kv-loop.mp4", "kv-loop.mp4");
                string mp3 = Helpers.ExtractEmbeddedMedia("AzurPromiliaVI.bgm.mp3", "bgm.mp3");
                RunOnUi(() =>
                {
                    if (!string.IsNullOrEmpty(mp4) && File.Exists(mp4))
                    {
                        try
                        {
                            _videoBg.Source = new Uri(mp4, UriKind.Absolute);
                            _videoLoaded = true;
                            if (_state.enable_video)
                            {
                                _videoBg.Visibility = Visibility.Visible;
                                _videoBg.Play();
                            }
                        }
                        catch { _videoBg.Visibility = Visibility.Collapsed; }
                    }
                    if (!string.IsNullOrEmpty(mp3) && File.Exists(mp3))
                    {
                        try
                        {
                            _bgmPlayer = new MediaPlayer();
                            _bgmPlayer.Volume = 0.36;
                            _bgmPlayer.MediaEnded += (s2, e2) =>
                            {
                                if (_state.enable_bgm && _bgmPlayer != null)
                                {
                                    try { _bgmPlayer.Position = TimeSpan.Zero; _bgmPlayer.Play(); } catch { }
                                }
                            };
                            _bgmPlayer.Open(new Uri(mp3, UriKind.Absolute));
                            _bgmLoaded = true;
                            if (_state.enable_bgm) _bgmPlayer.Play();
                        }
                        catch { _bgmLoaded = false; }
                    }
                });
            });
        }

        private void ToggleBgm()
        {
            _state.enable_bgm = !_state.enable_bgm;
            Helpers.SaveState(_state);
            _btnBgmToggle.Content = _state.enable_bgm ? "🔊 Nhạc: BẬT" : "🔇 Nhạc: TẮT";
            if (_bgmLoaded && _bgmPlayer != null)
            {
                try
                {
                    if (_state.enable_bgm) _bgmPlayer.Play();
                    else _bgmPlayer.Pause();
                }
                catch { }
            }
        }

        private void ToggleVideo()
        {
            _state.enable_video = !_state.enable_video;
            Helpers.SaveState(_state);
            _btnVideoToggle.Content = _state.enable_video ? "🎬 Động" : "🖼️ Tĩnh";
            if (_videoLoaded)
            {
                try
                {
                    if (_state.enable_video)
                    {
                        _videoBg.Visibility = Visibility.Visible;
                        _videoBg.Play();
                    }
                    else
                    {
                        _videoBg.Pause();
                        _videoBg.Visibility = Visibility.Collapsed;
                    }
                }
                catch { }
            }
        }

        private void PauseBgmForGameLaunch()
        {
            if (_bgmLoaded && _bgmPlayer != null && _state.enable_bgm)
            {
                try
                {
                    _bgmPlayer.Pause();
                    _btnBgmToggle.Content = "🔇 Nhạc (tạm dừng)";
                }
                catch { }
            }
        }

        private void DisposeMedia()
        {
            try
            {
                if (_bgmPlayer != null) { _bgmPlayer.Stop(); _bgmPlayer.Close(); _bgmPlayer = null; }
            }
            catch { }
            try
            {
                if (_videoBg != null) { _videoBg.Stop(); _videoBg.Close(); }
            }
            catch { }
        }

        private void RunOnUi(Action action)
        {
            if (Dispatcher.CheckAccess()) action();
            else Dispatcher.BeginInvoke(action);
        }

        private void BrowseFolder(TextBox target, bool isGame)
        {
            using (WF.FolderBrowserDialog dlg = new WF.FolderBrowserDialog())
            {
                dlg.Description = isGame ? "Chọn thư mục AZUPRO_JP" : "Chọn thư mục AZUPRO_JP_Gamelauncher";
                if (Directory.Exists(target.Text)) dlg.SelectedPath = target.Text;
                if (dlg.ShowDialog() == WF.DialogResult.OK)
                {
                    target.Text = isGame
                        ? (Helpers.FindJpGameRoot(dlg.SelectedPath) != "" ? Helpers.FindJpGameRoot(dlg.SelectedPath) : dlg.SelectedPath)
                        : (Helpers.FindJpLauncherRoot(dlg.SelectedPath, _txtGamePath.Text) != "" ? Helpers.FindJpLauncherRoot(dlg.SelectedPath, _txtGamePath.Text) : dlg.SelectedPath);
                    RefreshLocalStatuses();
                    SyncLocalVersionFromStatus(null);
                }
            }
        }

        private void Log(string line)
        {
            RunOnUi(() =>
            {
                _txtLog.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + line + Environment.NewLine);
                _txtLog.ScrollToEnd();
            });
        }

        private void SetProgress(double pct, string status)
        {
            RunOnUi(() =>
            {
                _progressPct = Math.Max(0, Math.Min(100, pct));
                ApplyProgressWidth();
                if (!string.IsNullOrEmpty(status)) _lblProgress.Text = status;
            });
        }

        private void ApplyProgressWidth()
        {
            if (_progressTrack == null || _progressFill == null) return;
            double w = _progressTrack.ActualWidth;
            if (w <= 0) w = 850;
            _progressFill.Width = w * (_progressPct / 100.0);
        }

        private void SetBusy(bool busy, string status)
        {
            RunOnUi(() =>
            {
                _busy = busy;
                _btnInstall.IsEnabled = !busy;
                _btnRestore.IsEnabled = !busy;
                _btnVerify.IsEnabled = !busy;
                _btnCheckUpdate.IsEnabled = !busy;
                _btnLaunch.IsEnabled = !busy;
                _btnDeblurToggle.IsEnabled = !busy;
                if (!string.IsNullOrEmpty(status)) _lblProgress.Text = status;
            });
        }

        private void RefreshLocalStatuses()
        {
            string g = _txtGamePath.Text.Trim();
            string l = _txtLauncherPath.Text.Trim();
            string gs = Helpers.CheckGameStatus(_packRoot, g);
            string ls = Helpers.CheckLauncherStatus(_packRoot, l);
            string ds = Helpers.CheckDeblurStatus(_packRoot, g);
            _lblGameStatus.Text = gs;
            _lblGameStatus.Foreground = new SolidColorBrush(
                gs.IndexOf("Đã cài") >= 0 ? Color.FromRgb(110, 235, 160) :
                gs.IndexOf("Chưa tìm") >= 0 || gs.IndexOf("chờ patch") >= 0 ? Color.FromRgb(255, 195, 95) :
                Color.FromRgb(150, 210, 255));
            _lblLauncherStatus.Text = ls;
            _lblLauncherStatus.Foreground = new SolidColorBrush(
                ls.IndexOf("Đã cài") >= 0 ? Color.FromRgb(110, 235, 160) : Color.FromRgb(150, 210, 255));

            bool deblurOn = ds.IndexOf("Đang BẬT") >= 0;
            _lblDeblurStatus.Text = ds;
            _lblDeblurStatus.Foreground = new SolidColorBrush(
                deblurOn ? Color.FromRgb(255, 200, 100) :
                ds.IndexOf("Đang TẮT") >= 0 ? Color.FromRgb(145, 215, 175) :
                Color.FromRgb(170, 185, 210));
            _btnDeblurToggle.Content = deblurOn ? "Tắt Bỏ làm mờ" : "Bật Bỏ làm mờ";
        }

        private void SyncLocalVersionFromStatus(string preferredVersion)
        {
            if (_lblGameStatus.Text.IndexOf("Đã cài") >= 0)
            {
                if (!string.IsNullOrEmpty(preferredVersion))
                {
                    _localVersion = preferredVersion;
                }
                else if (string.IsNullOrEmpty(_localVersion))
                {
                    string tmpVer;
                    Helpers.FindPayloadPackRoot(out tmpVer);
                    _localVersion = !string.IsNullOrEmpty(tmpVer)
                        ? tmpVer
                        : (!string.IsNullOrEmpty(_state.installed_version) ? _state.installed_version : Config.CurrentInstallerVersion);
                }
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
            UpdateHeaderLabel(_lblGameStatus.Text);
        }

        private void UpdateHeaderLabel(string gameStatus)
        {
            bool gameInstalled = !string.IsNullOrEmpty(gameStatus) && gameStatus.IndexOf("Đã cài") >= 0;
            bool fileMismatch = !string.IsNullOrEmpty(gameStatus) && (gameStatus.IndexOf("File không khớp") >= 0 || gameStatus.IndexOf("Cài dở dang") >= 0);

            string gameVerDesc;
            if (gameInstalled)
            {
                gameVerDesc = !string.IsNullOrEmpty(_localVersion) ? _localVersion : Config.CurrentInstallerVersion;
            }
            else if (fileMismatch)
            {
                gameVerDesc = string.IsNullOrEmpty(_state.installed_version)
                    ? "bản cũ (cần cập nhật)"
                    : (_state.installed_version + " (cần cập nhật)");
            }
            else if (!string.IsNullOrEmpty(gameStatus) && gameStatus.IndexOf("Chưa tìm") >= 0)
            {
                gameVerDesc = "chưa thấy thư mục game";
            }
            else
            {
                gameVerDesc = "chưa cài";
            }

            if (_remote != null && !string.IsNullOrEmpty(_remote.version))
            {
                bool installerOutdated = Helpers.CompareVersions(_remote.version, Config.CurrentInstallerVersion) > 0;
                bool gameOutdated = gameInstalled && !string.IsNullOrEmpty(_localVersion) && Helpers.CompareVersions(_remote.version, _localVersion) > 0;

                string updateNote;
                if (installerOutdated || gameOutdated || fileMismatch)
                    updateNote = " (CÓ BẢN MỚI!)";
                else if (!gameInstalled)
                    updateNote = " (Sẵn sàng cài)";
                else
                    updateNote = " (Đã mới nhất)";

                _lblVersionInfo.Text = string.Format("App: {0}  |  Việt hóa: {1}  |  GitHub: {2}{3}",
                    Config.CurrentInstallerVersion, gameVerDesc, _remote.version, updateNote);
            }
            else
            {
                _lblVersionInfo.Text = string.Format("App: {0}  |  Việt hóa: {1}  |  Đang check GitHub...",
                    Config.CurrentInstallerVersion, gameVerDesc);
            }
        }

        private void RefreshStateAndCheckAsync(bool fetchOnline)
        {
            string detectedVer;
            _packRoot = Helpers.FindPayloadPackRoot(out detectedVer);
            Helpers.SyncInstalledExe(_packRoot);
            if (string.IsNullOrEmpty(_txtGamePath.Text))
                _txtGamePath.Text = Helpers.FindJpGameRoot(_state.jp_game_path);
            if (string.IsNullOrEmpty(_txtLauncherPath.Text))
                _txtLauncherPath.Text = Helpers.FindJpLauncherRoot(_state.jp_launcher_path, _txtGamePath.Text);
            RefreshLocalStatuses();
            SyncLocalVersionFromStatus(!string.IsNullOrEmpty(detectedVer) ? detectedVer : Config.CurrentInstallerVersion);

            if (!fetchOnline) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    RemoteRelease rr = Helpers.FetchLatestRelease(8000);
                    _remote = rr;
                    RunOnUi(() =>
                    {
                        UpdateHeaderLabel(_lblGameStatus.Text);
                        Log("Đã kiểm tra GitHub (" + rr.source + "): bản mới nhất = " + rr.version +
                            (string.IsNullOrEmpty(rr.jp_resource_version) ? "" : " (Client JP #" + rr.jp_resource_version + ")"));
                    });
                }
                catch (Exception ex)
                {
                    RunOnUi(() =>
                    {
                        string localTxt = string.IsNullOrEmpty(_packRoot) ? "Chưa có payload" : "Payload cục bộ sẵn sàng";
                        _lblVersionInfo.Text = string.Format("App: {0}  |  {1} (Offline)", Config.CurrentInstallerVersion, localTxt);
                        Log("Không kiểm tra được GitHub (sẽ dùng gói cục bộ nếu có): " + ex.Message);
                    });
                }
            });
        }

        private string EnsurePackageAvailable(bool requireDeblur)
        {
            string localVer;
            string localRoot = Helpers.FindPayloadPackRoot(out localVer);
            bool needDownload = string.IsNullOrEmpty(localRoot);

            if (requireDeblur && !string.IsNullOrEmpty(localRoot) && !Helpers.HasDeblurPayload(localRoot))
                needDownload = true;

            if (_remote != null && !string.IsNullOrEmpty(_remote.full_zip_url) && !string.IsNullOrEmpty(_remote.version))
            {
                if (string.IsNullOrEmpty(localRoot) || (!string.IsNullOrEmpty(localVer) && Helpers.CompareVersions(_remote.version, localVer) > 0))
                    needDownload = true;
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
                SetProgress(pct, string.Format("Đang tải gói Việt hóa... {0}% ({1:0.0} / {2:0.0} MB)",
                    pct, rec / 1048576.0, Math.Max(tot, rec) / 1048576.0));
            });

            if (!string.IsNullOrEmpty(_remote.full_zip_sha256))
            {
                Log("Đang kiểm tra SHA256 file tải về...");
                string got = Helpers.Sha256File(zipPath);
                if (!string.Equals(got, _remote.full_zip_sha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("File tải về bị hỏng SHA256! Mong đợi " + _remote.full_zip_sha256 + ", nhận được " + got);
                Log("SHA256 khớp 100%.");
            }

            SetProgress(92, "Đang giải nén gói Việt hóa...");
            string extracted = Helpers.ExtractPackageZip(zipPath, _remote.version);
            _packRoot = extracted;
            _localVersion = _remote.version;
            return extracted;
        }

        private void ToggleDeblurAsync()
        {
            if (_busy) return;
            string gameDir = _txtGamePath.Text.Trim();
            if (string.IsNullOrEmpty(gameDir) || !Directory.Exists(Path.Combine(gameDir, "AzurPromiliaJP_Data")))
            {
                MessageBox.Show(this, "Chưa tìm thấy thư mục AZUPRO_JP để bật/tắt Bỏ làm mờ!", "Thiếu đường dẫn", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            string curStatus = Helpers.CheckDeblurStatus(_packRoot, gameDir);
            bool currentlyOn = curStatus.IndexOf("Đang BẬT") >= 0;

            if (!currentlyOn)
            {
                if (MessageBox.Show(this,
                    "Bật tính năng Bỏ làm mờ (Deblur) cho Azur Promilia JP?\n\n" +
                    "• Tắt hiệu ứng làm mờ/ẩn nhân vật khi zoom sát hoặc xoay góc camera từ dưới lên (4 file .r, giữ nguyên dung lượng & CRC32).\n" +
                    "• Tính năng này mặc định TẮT để an toàn tối đa; bạn có thể bấm nút 'Tắt Bỏ làm mờ' bất kỳ lúc nào để khôi phục 4 file gốc.",
                    "Xác nhận Bật Bỏ làm mờ (Deblur)", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
                {
                    return;
                }
            }
            else
            {
                if (MessageBox.Show(this,
                    "Tắt Bỏ làm mờ (Deblur) và khôi phục lại 4 file gốc của JP Game?",
                    "Xác nhận Tắt Bỏ làm mờ", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
                {
                    return;
                }
            }

            SetBusy(true, currentlyOn ? "Đang tắt Bỏ làm mờ (khôi phục 4 file gốc)..." : "Đang bật Bỏ làm mờ (Deblur)...");
            if (!EnsureTargetProcessClosed("AzurPromiliaJP", "Game AzurPromiliaJP.exe"))
            {
                SetBusy(false, "Đã hủy thao tác Bỏ làm mờ.");
                return;
            }
            SetProgress(0, null);

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

                    RunOnUi(() =>
                    {
                        SetProgress(100, null);
                        RefreshLocalStatuses();
                        string msg = currentlyOn ? "Đã TẮT Bỏ làm mờ (khôi phục 4 file gốc)!" : "Đã BẬT Bỏ làm mờ (Deblur) thành công!";
                        SetBusy(false, msg);
                        MessageBox.Show(this, msg, "Hoàn tất", MessageBoxButton.OK, MessageBoxImage.Information);
                    });
                }
                catch (Exception ex)
                {
                    Log("[LỖI Deblur] " + ex.Message);
                    RunOnUi(() =>
                    {
                        RefreshLocalStatuses();
                        SetBusy(false, "Thao tác Bỏ làm mờ thất bại.");
                        MessageBox.Show(this, "Lỗi: " + ex.Message, "Thất bại", MessageBoxButton.OK, MessageBoxImage.Error);
                    });
                }
            });
        }

        private bool EnsureTargetProcessClosed(string procName, string displayLabel)
        {
            Process[] procs = Process.GetProcessesByName(procName);
            if (procs == null || procs.Length == 0) return true;
            try
            {
                if (MessageBox.Show(this,
                    displayLabel + " vẫn đang chạy (có thể đang thu gọn ở khay hệ thống nên khóa file).\n\n" +
                    "Bạn có muốn đóng hoàn toàn " + displayLabel + " ngay bây giờ để tiếp tục không?",
                    "Đóng tiến trình đang chạy", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
                {
                    return false;
                }
                foreach (Process p in procs)
                {
                    try
                    {
                        if (!p.HasExited)
                        {
                            p.Kill();
                            p.WaitForExit(3000);
                        }
                    }
                    catch { }
                }
            }
            finally
            {
                foreach (Process p in procs)
                {
                    try { p.Dispose(); } catch { }
                }
            }
            Thread.Sleep(250);
            Process[] left = Process.GetProcessesByName(procName);
            int remaining = left != null ? left.Length : 0;
            if (left != null)
            {
                foreach (Process p in left) { try { p.Dispose(); } catch { } }
            }
            if (remaining > 0)
            {
                MessageBox.Show(this,
                    "Không thể tự đóng " + displayLabel + " (có thể đang chạy với quyền Administrator). Vui lòng tắt thủ công rồi thử lại.",
                    "Không thể đóng tiến trình", MessageBoxButton.OK, MessageBoxImage.Warning);
                return false;
            }
            return true;
        }

        private void StartInstallOrUpdate()
        {
            if (_busy) return;
            string gameDir = _txtGamePath.Text.Trim();
            string launcherDir = _txtLauncherPath.Text.Trim();
            bool createShortcut = _chkShortcut.IsChecked == true;
            bool autoLaunch = _chkAutoLaunch.IsChecked == true;
            if (string.IsNullOrEmpty(gameDir) && string.IsNullOrEmpty(launcherDir))
            {
                MessageBox.Show(this, "Chưa chọn thư mục AZUPRO_JP hoặc AZUPRO_JP_Gamelauncher!", "Thiếu đường dẫn", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            if (!string.IsNullOrEmpty(gameDir) && Helpers.CheckGameStatus(_packRoot, gameDir).IndexOf("Đã cài") < 0)
            {
                if (!EnsureTargetProcessClosed("AzurPromiliaJP", "Game AzurPromiliaJP.exe")) return;
            }
            if (!string.IsNullOrEmpty(launcherDir) && Helpers.CheckLauncherStatus(_packRoot, launcherDir).IndexOf("Đã cài") < 0)
            {
                if (!EnsureTargetProcessClosed("AZUPRO_JP_Gamelauncher", "Launcher gốc (AZUPRO_JP_Gamelauncher.exe)")) return;
            }
            SetBusy(true, "Đang chuẩn bị cài đặt...");
            SetProgress(0, null);

            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string packRoot = EnsurePackageAvailable(false);
                    bool needAdmin = (!string.IsNullOrEmpty(gameDir) && !Helpers.CanWriteDir(Path.Combine(gameDir, "AzurPromiliaJP_Data"))) ||
                                     (!string.IsNullOrEmpty(launcherDir) && !Helpers.CanWriteDir(Path.Combine(launcherDir, "resources")));
                    if (needAdmin && !Helpers.IsAdmin())
                        Log("Thư mục game cần quyền Quản trị viên (UAC), hệ thống sẽ hỏi xác nhận...");

                    if (!string.IsNullOrEmpty(gameDir))
                    {
                        SetProgress(94, "Đang cài Việt hóa vào JP Game...");
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
                        SetProgress(97, "Đang cài Việt hóa vào JP Launcher...");
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
                    _state.auto_update_on_launch = autoLaunch;
                    _state.last_checked_utc = DateTime.UtcNow.ToString("o");
                    Helpers.SaveState(_state);

                    if (createShortcut)
                    {
                        Helpers.CreateDesktopShortcut(installedExe);
                        Log("Đã tạo shortcut Desktop: \"Azur Promilia (Việt Hóa)\".");
                    }

                    RunOnUi(() =>
                    {
                        SetProgress(100, "Cài đặt Việt hóa thành công!");
                        RefreshLocalStatuses();
                        UpdateHeaderLabel(_lblGameStatus.Text);
                        SetBusy(false, "Cài đặt Việt hóa thành công!");
                        MessageBox.Show(this, "Cài đặt / Cập nhật Việt hóa hoàn tất!", "Thành công", MessageBoxButton.OK, MessageBoxImage.Information);
                    });
                }
                catch (Exception ex)
                {
                    Log("[LỖI] " + ex.Message);
                    RunOnUi(() =>
                    {
                        SetBusy(false, "Cài đặt thất bại.");
                        MessageBox.Show(this, "Lỗi: " + ex.Message, "Thất bại", MessageBoxButton.OK, MessageBoxImage.Error);
                    });
                }
            });
        }

        private void StartRestore()
        {
            if (_busy || string.IsNullOrEmpty(_packRoot))
            {
                MessageBox.Show(this, "Cần có thư mục tools/ hoặc gói Việt hóa để chạy Khôi phục an toàn.", "Thông báo", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }
            string gameDir = _txtGamePath.Text.Trim();
            string launcherDir = _txtLauncherPath.Text.Trim();
            if (!string.IsNullOrEmpty(gameDir) && !EnsureTargetProcessClosed("AzurPromiliaJP", "Game AzurPromiliaJP.exe")) return;
            if (!string.IsNullOrEmpty(launcherDir) && !EnsureTargetProcessClosed("AZUPRO_JP_Gamelauncher", "Launcher gốc (AZUPRO_JP_Gamelauncher.exe)")) return;
            SetBusy(true, "Đang khôi phục bản gốc...");
            SetProgress(35, "Đang khôi phục bản gốc...");
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
                    RunOnUi(() =>
                    {
                        SetProgress(100, "Đã khôi phục nguyên bản!");
                        RefreshLocalStatuses();
                        UpdateHeaderLabel(_lblGameStatus.Text);
                        SetBusy(false, "Đã khôi phục nguyên bản!");
                    });
                }
                catch (Exception ex)
                {
                    Log("[LỖI] " + ex.Message);
                    RunOnUi(() => SetBusy(false, "Khôi phục lỗi."));
                }
            });
        }

        private void StartVerify()
        {
            if (_busy || string.IsNullOrEmpty(_packRoot))
            {
                RefreshLocalStatuses();
                SyncLocalVersionFromStatus(null);
                return;
            }
            string gameDir = _txtGamePath.Text.Trim();
            string launcherDir = _txtLauncherPath.Text.Trim();
            SetBusy(true, "Đang kiểm tra toàn bộ CRC32 & SHA256...");
            SetProgress(35, "Đang kiểm tra toàn bộ CRC32 & SHA256...");
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
                    RunOnUi(() =>
                    {
                        SetProgress(100, "Kiểm tra hoàn tất.");
                        RefreshLocalStatuses();
                        SyncLocalVersionFromStatus(null);
                        SetBusy(false, "Kiểm tra hoàn tất.");
                    });
                }
                catch (Exception ex)
                {
                    Log("[LỖI] " + ex.Message);
                    RunOnUi(() => SetBusy(false, "Kiểm tra gặp lỗi."));
                }
            });
        }

        private void LaunchGame()
        {
            string launcherDir = _txtLauncherPath.Text.Trim();
            if (string.IsNullOrEmpty(launcherDir) || !File.Exists(Path.Combine(launcherDir, "AZUPRO_JP_Gamelauncher.exe")))
            {
                MessageBox.Show(this, "Không tìm thấy AZUPRO_JP_Gamelauncher.exe!", "Lỗi", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            _state.auto_update_on_launch = _chkAutoLaunch.IsChecked == true;
            _state.jp_game_path = _txtGamePath.Text.Trim();
            _state.jp_launcher_path = launcherDir;
            Helpers.SaveState(_state);

            if (_state.auto_update_on_launch && _remote != null && !string.IsNullOrEmpty(_remote.version)
                && !string.IsNullOrEmpty(_localVersion) && Helpers.CompareVersions(_remote.version, _localVersion) > 0)
            {
                if (MessageBox.Show(this, "Có bản cập nhật Việt hóa mới (" + _remote.version + "). Cập nhật ngay trước khi mở Launcher?",
                    "Cập nhật Việt hóa", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes)
                {
                    StartInstallOrUpdate();
                    return;
                }
            }
            PauseBgmForGameLaunch();
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
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        private static void RunGui()
        {
            Application app = new Application();
            app.Run(new LauncherWindow());
        }

        [STAThread]
        private static int Main(string[] args)
        {
            try { SetProcessDPIAware(); } catch { }
            try { Console.OutputEncoding = Encoding.UTF8; } catch { }

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

            RunGui();
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
                    if (!string.IsNullOrEmpty(rr.version) && Helpers.CompareVersions(rr.version, cur) > 0 && !string.IsNullOrEmpty(rr.full_zip_url))
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
                RunGui();
            }
        }
    }
}
