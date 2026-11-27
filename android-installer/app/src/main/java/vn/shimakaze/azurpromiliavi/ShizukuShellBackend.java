package vn.shimakaze.azurpromiliavi;

import android.os.Build;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import moe.shizuku.server.IRemoteProcess;
import moe.shizuku.server.IShizukuService;
import rikka.shizuku.Shizuku;

/**
 * Fallback backend using IShizukuService#newProcess directly as UID 2000/0 shell.
 * Avoids UserService (app_process / LoadedApk.makeApplicationInner), which crashes
 * or hangs silently on some Xiaomi HyperOS / MIUI and custom OEM ROMs.
 */
final class ShizukuShellBackend {

    static final class ExecResult {
        final int exitCode;
        final String stdout;
        final String stderr;

        ExecResult(int exitCode, String stdout, String stderr) {
            this.exitCode = exitCode;
            this.stdout = stdout;
            this.stderr = stderr;
        }
    }

    private ShizukuShellBackend() {
    }

    static String probeShellUid() throws Exception {
        ExecResult res = exec("sh", "-c", "id -u");
        if (res.exitCode != 0) {
            String err = res.stderr.trim();
            throw new IllegalStateException(err.isEmpty() ? ("shell exit " + res.exitCode) : err);
        }
        String uid = res.stdout.trim();
        if (uid.isEmpty()) {
            throw new IllegalStateException("Empty id -u output");
        }
        for (int i = 0; i < uid.length(); i++) {
            if (!Character.isDigit(uid.charAt(i))) {
                throw new IllegalStateException("Unexpected uid output: " + uid);
            }
        }
        return uid;
    }

    static String detectResVersion(String gameFilesDir) {
        try {
            String script = "d=\"$1/.res/raw_base_package/ManifestFiles\"\n"
                    + "[ -d \"$d\" ] || exit 0\n"
                    + "for f in \"$d\"/0release_raw_base_package_*.bytes; do\n"
                    + "  [ -f \"$f\" ] || continue\n"
                    + "  n=\"${f##*/}\"\n"
                    + "  n=\"${n#0release_raw_base_package_}\"\n"
                    + "  n=\"${n%.bytes}\"\n"
                    + "  printf '%s\\n' \"$n\"\n"
                    + "done\n";
            ExecResult res = exec("sh", "-c", script, "sh", gameFilesDir);
            if (res.exitCode != 0) return "";
            String best = "";
            long bestNum = Long.MIN_VALUE;
            for (String raw : res.stdout.split("\n")) {
                String cand = raw.trim();
                if (cand.isEmpty()) continue;
                try {
                    long v = Long.parseLong(cand);
                    if (v > bestNum) {
                        bestNum = v;
                        best = cand;
                    }
                } catch (NumberFormatException ignored) {
                    if (best.isEmpty() || cand.compareTo(best) > 0) {
                        best = cand;
                    }
                }
            }
            return best;
        } catch (Throwable t) {
            return "";
        }
    }

    static String forceStopGame(String packageName) {
        try {
            ExecResult res = exec("am", "force-stop", packageName);
            return res.exitCode == 0 ? "OK" : ("RC=" + res.exitCode);
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    static String probeGameState(String gameFilesDir, String manifestJson) {
        try {
            boolean hasManifest = manifestJson != null && !manifestJson.trim().isEmpty();
            JSONObject plan = hasManifest ? new JSONObject(manifestJson) : null;
            String targetVer = plan != null ? plan.optString("resource_version", "") : "";
            JSONArray arr = plan != null ? plan.getJSONArray("files") : new JSONArray();

            List<String> argv = new ArrayList<>(4 + arr.length());
            argv.add("sh");
            argv.add("-c");
            String script = "gf=\"$1\"; ver=\"$2\"; shift 2\n"
                    + "res=\"$gf/.res\"\n"
                    + "bakroot=\"$gf/.vi-android-backup-$ver\"\n"
                    + "[ -d \"$gf\" ] && echo \"DIR=1\" || echo \"DIR=0\"\n"
                    + "[ -d \"$res\" ] && echo \"RES=1\" || echo \"RES=0\"\n"
                    + "det=\"\"\n"
                    + "for f in \"$res/raw_base_package/ManifestFiles\"/0release_raw_base_package_*.bytes; do\n"
                    + "  [ -f \"$f\" ] || continue\n"
                    + "  det=\"${f##*/}\"; det=\"${det#0release_raw_base_package_}\"; det=\"${det%.bytes}\"; break\n"
                    + "done\n"
                    + "echo \"DET=$det\"\n"
                    + "if [ -n \"$ver\" ] && [ -f \"$res/raw_base_package/ManifestFiles/0release_raw_base_package_${ver}.bytes\" ]; then echo \"MF=1\"; else echo \"MF=0\"; fi\n"
                    + "i=0\n"
                    + "for rel in \"$@\"; do\n"
                    + "  p=\"$res/$rel\"; b=\"$bakroot/$rel\"\n"
                    + "  if [ -f \"$p\" ]; then\n"
                    + "    ds=$(stat -c %s \"$p\" 2>/dev/null || wc -c < \"$p\")\n"
                    + "    dh=$(sha256sum \"$p\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "    echo \"D|$i|1|$ds|$dh\"\n"
                    + "  else\n"
                    + "    echo \"D|$i|0|0|\"\n"
                    + "  fi\n"
                    + "  if [ -f \"$b\" ]; then\n"
                    + "    bs=$(stat -c %s \"$b\" 2>/dev/null || wc -c < \"$b\")\n"
                    + "    bh=$(sha256sum \"$b\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "    echo \"B|$i|1|$bs|$bh\"\n"
                    + "  else\n"
                    + "    echo \"B|$i|0|0|\"\n"
                    + "  fi\n"
                    + "  i=$((i + 1))\n"
                    + "done\n";
            argv.add(script);
            argv.add("sh");
            argv.add(gameFilesDir);
            argv.add(targetVer);
            for (int i = 0; i < arr.length(); i++) {
                argv.add(arr.getJSONObject(i).getString("relative_path").replace('\\', '/'));
            }

            ExecResult res = exec(argv.toArray(new String[0]));
            if (res.exitCode != 0) {
                String msg = res.stderr.trim().isEmpty() ? ("Shell exit " + res.exitCode) : res.stderr.trim();
                return new JSONObject().put("error", msg).toString();
            }

            boolean dirExists = false;
            boolean resExists = false;
            boolean mfMatched = false;
            String detVer = "";
            Map<Integer, String[]> destMap = new HashMap<>();
            Map<Integer, String[]> bakMap = new HashMap<>();

            for (String rawLine : res.stdout.split("\n")) {
                String line = rawLine.trim();
                if (line.equals("DIR=1")) dirExists = true;
                else if (line.equals("RES=1")) resExists = true;
                else if (line.equals("MF=1")) mfMatched = true;
                else if (line.startsWith("DET=")) detVer = line.substring(4);
                else if (line.startsWith("D|") || line.startsWith("B|")) {
                    String[] parts = line.split("\\|", -1);
                    if (parts.length >= 5) {
                        int idx = Integer.parseInt(parts[1]);
                        if (parts[0].equals("D")) destMap.put(idx, parts);
                        else bakMap.put(idx, parts);
                    }
                }
            }

            JSONObject out = new JSONObject();
            out.put("files_dir_exists", dirExists);
            out.put("res_exists", resExists);
            out.put("detected_version", detVer);
            if (!hasManifest) {
                return out.toString();
            }

            out.put("target_version", targetVer);
            out.put("manifest_matched", mfMatched);

            int total = arr.length();
            int viCount = 0;
            int perfCount = 0;
            int origCount = 0;
            int missingCount = 0;
            int mismatchCount = 0;
            int backupCount = 0;

            for (int i = 0; i < total; i++) {
                JSONObject item = arr.getJSONObject(i);
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                String perfSha = item.optString("perf_target_sha256", "").toLowerCase(Locale.ROOT);

                String[] d = destMap.get(i);
                if (d == null || !"1".equals(d[2])) {
                    missingCount++;
                } else {
                    long dSize = parseLongSafe(d[3], -1);
                    String dHash = d[4].trim().toLowerCase(Locale.ROOT);
                    if (dSize != size) {
                        mismatchCount++;
                    } else if (dHash.equals(tgtSha)) {
                        viCount++;
                    } else if (!perfSha.isEmpty() && dHash.equals(perfSha)) {
                        viCount++;
                        perfCount++;
                    } else if (dHash.equals(srcSha)) {
                        origCount++;
                    } else {
                        mismatchCount++;
                    }
                }

                String[] b = bakMap.get(i);
                if (b != null && "1".equals(b[2])) {
                    long bSize = parseLongSafe(b[3], -1);
                    String bHash = b[4].trim().toLowerCase(Locale.ROOT);
                    if (bSize == size && bHash.equals(srcSha)) {
                        backupCount++;
                    }
                }
            }

            out.put("total", total);
            out.put("vi_count", viCount);
            out.put("perf_count", perfCount);
            out.put("orig_count", origCount);
            out.put("missing_count", missingCount);
            out.put("mismatch_count", mismatchCount);
            out.put("backup_count", backupCount);
            out.put("payload_hash", computePayloadHash(arr));
            return out.toString();
        } catch (Throwable t) {
            try {
                return new JSONObject().put("error", String.valueOf(t.getMessage())).toString();
            } catch (Throwable ignored) {
                return "{\"error\":\"probe error\"}";
            }
        }
    }

    static String installFromStaging(String stagingDir, String gameFilesDir, String manifestJson) {
        try {
            JSONObject plan = new JSONObject(manifestJson);
            String targetVer = plan.getString("resource_version");
            JSONArray arr = plan.getJSONArray("files");

            // Check resource version manifest via shell
            ExecResult mfChk = exec("sh", "-c",
                    "[ -f \"$1/.res/raw_base_package/ManifestFiles/0release_raw_base_package_${2}.bytes\" ] && echo OK || echo MISS",
                    "sh", gameFilesDir, targetVer);
            if (mfChk.exitCode != 0 || !mfChk.stdout.trim().equals("OK")) {
                String found = detectResVersion(gameFilesDir);
                return "ERR:Phiên bản tài nguyên game không khớp (cần " + targetVer + ", trên máy là " + (found.isEmpty() ? "chưa tải" : found) + ")";
            }

            // Step 1: Verify every staged file in app storage before touching game files
            File stDir = new File(stagingDir);
            List<File> stagedFiles = new ArrayList<>(arr.length());
            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path").replace('\\', '/');
                long size = item.getLong("size");
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                File staged = new File(stDir, rel);
                if (!staged.isFile()) {
                    staged = new File(stDir, "android_game/" + rel);
                }
                if (!staged.isFile()) {
                    staged = new File(stDir, "android_perf/" + rel);
                }
                if (!staged.isFile() || staged.length() != size || !sha256File(staged).equals(tgtSha)) {
                    return "ERR:Gói tải về bị lỗi hoặc thiếu file: " + rel;
                }
                stagedFiles.add(staged);
            }

            // Step 2: Backup originals and write patched files atomically as UID 2000
            String script = "set -e\n"
                    + "gf=\"$1\"; ver=\"$2\"; rel=\"$3\"; stg=\"$4\"; src_sha=\"$5\"; tgt_sha=\"$6\"; exp_sz=\"$7\"; alt_sha=\"$8\"\n"
                    + "dest=\"$gf/.res/$rel\"\n"
                    + "bak=\"$gf/.vi-android-backup-$ver/$rel\"\n"
                    + "if [ ! -f \"$dest\" ]; then echo \"ERR:MISSING\"; exit 1; fi\n"
                    + "cur=$(sha256sum \"$dest\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "if [ \"$cur\" = \"$src_sha\" ]; then\n"
                    + "  need_bak=1\n"
                    + "  if [ -f \"$bak\" ]; then\n"
                    + "    bh=$(sha256sum \"$bak\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "    [ \"$bh\" = \"$src_sha\" ] && need_bak=0\n"
                    + "  fi\n"
                    + "  if [ \"$need_bak\" -eq 1 ]; then\n"
                    + "    mkdir -p \"${bak%/*}\"\n"
                    + "    cp -f \"$dest\" \"$bak\" || { echo \"ERR:BAKFAIL\"; exit 1; }\n"
                    + "    bh=$(sha256sum \"$bak\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "    [ \"$bh\" = \"$src_sha\" ] || { echo \"ERR:BAKSHA\"; exit 1; }\n"
                    + "  fi\n"
                    + "elif [ \"$cur\" != \"$tgt_sha\" ] && { [ -z \"$alt_sha\" ] || [ \"$cur\" != \"$alt_sha\" ]; }; then\n"
                    + "  echo \"ERR:MISMATCH\"; exit 1\n"
                    + "fi\n"
                    + "if [ \"$cur\" = \"$tgt_sha\" ]; then echo \"OK:SKIP\"; exit 0; fi\n"
                    + "tmp=\"${dest}.vitmp\"\n"
                    + "cp -f \"$stg\" \"$tmp\" || { rm -f \"$tmp\"; echo \"ERR:CPTMP\"; exit 1; }\n"
                    + "ts=$(stat -c %s \"$tmp\" 2>/dev/null || wc -c < \"$tmp\")\n"
                    + "th=$(sha256sum \"$tmp\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "[ \"$ts\" = \"$exp_sz\" ] && [ \"$th\" = \"$tgt_sha\" ] || { rm -f \"$tmp\"; echo \"ERR:TMPSHA\"; exit 1; }\n"
                    + "mv -f \"$tmp\" \"$dest\" || { rm -f \"$dest\" && mv -f \"$tmp\" \"$dest\"; } || { cp -f \"$stg\" \"$dest\" && rm -f \"$tmp\"; }\n"
                    + "fs=$(stat -c %s \"$dest\" 2>/dev/null || wc -c < \"$dest\")\n"
                    + "fh=$(sha256sum \"$dest\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "[ \"$fs\" = \"$exp_sz\" ] && [ \"$fh\" = \"$tgt_sha\" ] || { echo \"ERR:FINALSHA\"; exit 1; }\n"
                    + "echo \"OK:WRITTEN\"\n";

            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path").replace('\\', '/');
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                String altSha = item.optString("perf_target_sha256", "").toLowerCase(Locale.ROOT);
                File staged = stagedFiles.get(i);

                ExecResult r = exec("sh", "-c", script, "sh",
                        gameFilesDir, targetVer, rel, staged.getAbsolutePath(),
                        srcSha, tgtSha, Long.toString(size), altSha);
                String out = r.stdout.trim();
                if (r.exitCode != 0 || !out.startsWith("OK:")) {
                    if (out.contains("ERR:MISSING")) {
                        return "ERR:Game chưa tải đủ file này (hãy vào game tải full data trước): " + rel;
                    }
                    if (out.contains("ERR:MISMATCH")) {
                        return "ERR:File gốc trên máy không khớp baseline (" + rel + "), hãy Verify tài nguyên trong game trước.";
                    }
                    if (out.contains("ERR:BAKFAIL") || out.contains("ERR:BAKSHA")) {
                        return "ERR:Lỗi tạo backup cho " + rel;
                    }
                    if (out.contains("ERR:TMPSHA")) {
                        return "ERR:Kiểm tra SHA-256 sau khi ghi tạm thất bại: " + rel;
                    }
                    if (out.contains("ERR:FINALSHA")) {
                        return "ERR:Kiểm tra SHA-256 cuối thất bại: " + rel;
                    }
                    String detail = !out.isEmpty() ? out : r.stderr.trim();
                    return "ERR:Lỗi chép file " + rel + (detail.isEmpty() ? "" : " (" + detail + ")");
                }
            }
            return "OK:" + arr.length();
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    static String restoreFromBackup(String gameFilesDir, String manifestJson) {
        try {
            JSONObject plan = new JSONObject(manifestJson);
            String targetVer = plan.getString("resource_version");
            JSONArray arr = plan.getJSONArray("files");

            // Step 1: Verify every backup file first via probe
            String verifyScript = "gf=\"$1\"; ver=\"$2\"; rel=\"$3\"; src_sha=\"$4\"; exp_sz=\"$5\"\n"
                    + "bak=\"$gf/.vi-android-backup-$ver/$rel\"\n"
                    + "[ -f \"$bak\" ] || { echo \"MISS\"; exit 1; }\n"
                    + "bs=$(stat -c %s \"$bak\" 2>/dev/null || wc -c < \"$bak\")\n"
                    + "bh=$(sha256sum \"$bak\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "[ \"$bs\" = \"$exp_sz\" ] && [ \"$bh\" = \"$src_sha\" ] && echo \"OK\" || echo \"BAD\"\n";

            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path").replace('\\', '/');
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                ExecResult r = exec("sh", "-c", verifyScript, "sh",
                        gameFilesDir, targetVer, rel, srcSha, Long.toString(size));
                if (r.exitCode != 0 || !r.stdout.trim().equals("OK")) {
                    return "ERR:Thiếu hoặc hỏng file backup: " + rel;
                }
            }

            // Step 2: Restore atomically
            String restoreScript = "set -e\n"
                    + "gf=\"$1\"; ver=\"$2\"; rel=\"$3\"; src_sha=\"$4\"\n"
                    + "bak=\"$gf/.vi-android-backup-$ver/$rel\"\n"
                    + "dest=\"$gf/.res/$rel\"\n"
                    + "mkdir -p \"${dest%/*}\"\n"
                    + "tmp=\"${dest}.vitmp\"\n"
                    + "cp -f \"$bak\" \"$tmp\" || { rm -f \"$tmp\"; echo \"ERR:CP\"; exit 1; }\n"
                    + "mv -f \"$tmp\" \"$dest\" || { rm -f \"$dest\" && mv -f \"$tmp\" \"$dest\"; } || { cp -f \"$bak\" \"$dest\" && rm -f \"$tmp\"; }\n"
                    + "fh=$(sha256sum \"$dest\" | while read h _; do echo \"$h\"; break; done)\n"
                    + "[ \"$fh\" = \"$src_sha\" ] && echo \"OK\" || { echo \"ERR:SHA\"; exit 1; }\n";

            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path").replace('\\', '/');
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                ExecResult r = exec("sh", "-c", restoreScript, "sh",
                        gameFilesDir, targetVer, rel, srcSha);
                if (r.exitCode != 0 || !r.stdout.trim().equals("OK")) {
                    return "ERR:Khôi phục thất bại cho " + rel;
                }
            }
            return "OK:" + arr.length();
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    private static ExecResult exec(String... argv) throws Exception {
        IBinder binder = Shizuku.getBinder();
        if (binder == null || !binder.pingBinder()) {
            throw new IllegalStateException("Shizuku binder not alive");
        }
        IShizukuService service = IShizukuService.Stub.asInterface(binder);
        if (service == null) {
            throw new IllegalStateException("IShizukuService unavailable");
        }
        IRemoteProcess proc = service.newProcess(argv, null, null);
        if (proc == null) {
            throw new IllegalStateException("newProcess returned null");
        }
        try {
            try {
                ParcelFileDescriptor stdinPfd = proc.getOutputStream();
                if (stdinPfd != null) stdinPfd.close();
            } catch (Throwable ignored) {
            }

            final ByteArrayOutputStream errBuf = new ByteArrayOutputStream();
            final ParcelFileDescriptor errPfd = proc.getErrorStream();
            Thread errThread = new Thread(() -> {
                if (errPfd == null) return;
                try (InputStream es = new ParcelFileDescriptor.AutoCloseInputStream(errPfd)) {
                    byte[] b = new byte[8192];
                    int n;
                    while ((n = es.read(b)) > 0) {
                        if (errBuf.size() < 65536) {
                            errBuf.write(b, 0, Math.min(n, 65536 - errBuf.size()));
                        }
                    }
                } catch (Throwable ignored) {
                }
            }, "shiz-err");
            errThread.setDaemon(true);
            errThread.start();

            ByteArrayOutputStream outBuf = new ByteArrayOutputStream();
            ParcelFileDescriptor outPfd = proc.getInputStream();
            if (outPfd != null) {
                try (InputStream is = new ParcelFileDescriptor.AutoCloseInputStream(outPfd)) {
                    byte[] b = new byte[16384];
                    int n;
                    while ((n = is.read(b)) > 0) {
                        outBuf.write(b, 0, n);
                    }
                }
            }

            int rc = proc.waitFor();
            try {
                errThread.join(2000);
            } catch (InterruptedException ignored) {
            }
            return new ExecResult(
                    rc,
                    new String(outBuf.toByteArray(), StandardCharsets.UTF_8),
                    new String(errBuf.toByteArray(), StandardCharsets.UTF_8)
            );
        } finally {
            try {
                if (proc.alive()) proc.destroy();
            } catch (Throwable ignored) {
            }
        }
    }

    private static long parseLongSafe(String s, long fallback) {
        try {
            return Long.parseLong(s.trim());
        } catch (Throwable t) {
            return fallback;
        }
    }

    private static String computePayloadHash(JSONArray arr) throws Exception {
        List<String> rows = new ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) {
            JSONObject item = arr.getJSONObject(i);
            String rel = item.getString("relative_path").replace('\\', '/');
            String tgt = item.getString("target_sha256").toLowerCase(Locale.ROOT);
            rows.add(rel + ":" + tgt + "\n");
        }
        Collections.sort(rows);
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        for (String r : rows) {
            md.update(r.getBytes(StandardCharsets.UTF_8));
        }
        byte[] digest = md.digest();
        StringBuilder sb = new StringBuilder(64);
        for (byte b : digest) {
            sb.append(String.format(Locale.ROOT, "%02x", b & 0xFF));
        }
        return sb.toString();
    }

    private static String sha256File(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buf = new byte[524288];
        try (InputStream in = new FileInputStream(f)) {
            int n;
            while ((n = in.read(buf)) > 0) {
                md.update(buf, 0, n);
            }
        }
        byte[] digest = md.digest();
        StringBuilder sb = new StringBuilder(64);
        for (byte b : digest) {
            sb.append(String.format(Locale.ROOT, "%02x", b & 0xFF));
        }
        return sb.toString();
    }

    static JSONObject probeGameMode(String packageName) {
        JSONObject out = new JSONObject();
        try {
            ExecResult lm = exec("cmd", "game", "list-modes", packageName);
            String mOut = (lm.stdout + "\n" + lm.stderr).trim();
            String low = mOut.toLowerCase(Locale.ROOT);
            if (lm.exitCode != 0 || low.contains("unknown command") || low.contains("can't find service") || mOut.isEmpty()) {
                out.put("supported", false);
                out.put("reason", mOut.isEmpty() ? "Thiết bị chưa bật GameManagerService (Android < 13 hoặc ROM đã tắt)" : mOut);
                return out;
            }
            out.put("supported", true);
            String curMode = "standard";
            Matcher mm = Pattern.compile("current mode:\\s*([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(mOut);
            if (mm.find()) {
                curMode = mm.group(1).toLowerCase(Locale.ROOT);
            }
            out.put("mode", curMode);

            ExecResult lc = exec("cmd", "game", "list-configs", packageName);
            String cOut = (lc.stdout + "\n" + lc.stderr).trim();
            out.put("raw_configs", cOut);
            String scaling = "-1";
            String fps = "-1";
            Matcher mc = Pattern.compile("Game Mode:\\s*4\\b[^\\]]*", Pattern.CASE_INSENSITIVE).matcher(cOut);
            if (mc.find()) {
                String seg = mc.group(0);
                Matcher ms = Pattern.compile("Scaling:\\s*([0-9.\\-]+)").matcher(seg);
                if (ms.find()) scaling = ms.group(1);
                Matcher mf = Pattern.compile("Fps:\\s*([0-9\\-]+)").matcher(seg);
                if (mf.find()) fps = mf.group(1);
            }
            out.put("scaling", scaling);
            out.put("fps", fps);
            return out;
        } catch (Throwable t) {
            try {
                out.put("supported", false);
                out.put("reason", String.valueOf(t.getMessage()));
            } catch (Throwable ignored) {
            }
            return out;
        }
    }

    private static String formatDownscaleArg(double scale) {
        if (scale >= 0.99 && scale <= 1.01) return "disable";
        // Snap to 0.05 step and trim trailing .0 zeros ("0.60" -> "0.6") for strict Android 13 parsers
        double snapped = Math.round(scale * 20.0) / 20.0;
        String s = String.format(Locale.ROOT, "%.2f", snapped);
        if (s.endsWith("0")) s = s.substring(0, s.length() - 1);
        return s;
    }

    static String applyGameMode(String packageName, String downscaleArg, int fps) {
        try {
            boolean noScale = downscaleArg == null || downscaleArg.isEmpty()
                    || "disable".equalsIgnoreCase(downscaleArg)
                    || "1.0".equals(downscaleArg) || "1.00".equals(downscaleArg);
            if (noScale && fps <= 0) {
                return resetGameMode(packageName);
            }
            exec("cmd", "game", "reset", packageName);

            ExecResult setRes = runCmdGameSet(packageName, noScale ? "disable" : downscaleArg, fps);
            String out = (setRes.stdout + " " + setRes.stderr).trim();
            if (setRes.exitCode != 0 || out.toLowerCase(Locale.ROOT).contains("error")) {
                // On strict Android 13/14 ROMs, values > 0.9 may be rejected; fallback to native "disable"
                double parsed = -1;
                try { if (!noScale) parsed = Double.parseDouble(downscaleArg); } catch (NumberFormatException ignored) {}
                if (parsed > 0.9) {
                    setRes = runCmdGameSet(packageName, "disable", fps);
                    out = (setRes.stdout + " " + setRes.stderr).trim();
                }
                if (setRes.exitCode != 0 || out.toLowerCase(Locale.ROOT).contains("error")) {
                    return "ERR:Thiết bị không chấp nhận cấu hình (" + (out.isEmpty() ? "exit " + setRes.exitCode : out) + ")";
                }
            }

            ExecResult modeRes = exec("cmd", "game", "mode", "custom", packageName);
            String mOut = (modeRes.stdout + " " + modeRes.stderr).trim();
            if (modeRes.exitCode != 0) {
                return "ERR:Không chuyển được GameMode custom (" + mOut + ")";
            }
            return "OK:" + out;
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    private static ExecResult runCmdGameSet(String packageName, String scaleArg, int fps) throws Exception {
        List<String> argv = new ArrayList<>();
        argv.add("cmd");
        argv.add("game");
        argv.add("set");
        argv.add("--downscale");
        argv.add(scaleArg);
        if (fps > 0) {
            argv.add("--fps");
            argv.add(Integer.toString(fps));
        }
        argv.add(packageName);
        return exec(argv.toArray(new String[0]));
    }

    static String resetGameMode(String packageName) {
        try {
            exec("cmd", "game", "reset", packageName);
            ExecResult res = exec("cmd", "game", "mode", "standard", packageName);
            String out = (res.stdout + " " + res.stderr).trim();
            if (res.exitCode != 0) {
                return "ERR:" + (out.isEmpty() ? "exit " + res.exitCode : out);
            }
            return "OK:STANDARD";
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    // =========================================================================
    // Universal Multi-Layer Performance Engine (Weak devices + Gaming devices)
    // =========================================================================

    static double presetScaleForIndex(int presetIdx, double customScale) {
        switch (presetIdx) {
            case 0: return 0.60; // Máy yếu / Chống lag
            case 1: return 0.75; // Cân bằng mượt
            case 2: return 1.00; // Nguyên bản
            case 3: return 1.00; // Gaming Max
            default: return Math.max(0.45, Math.min(1.50, customScale));
        }
    }

    static int[] computeScaledWmDimensions(int nw, int nh, int nd, double scale) {
        if (nw <= 0 || nh <= 0 || scale >= 0.99) return new int[]{nw, nh, nd};
        int tw = Math.max(360, ((int) Math.round(nw * scale) / 8) * 8);
        int th = Math.max(640, ((int) Math.round(nh * scale) / 8) * 8);
        if (tw >= nw) tw = ((int) Math.round(nw * scale) / 4) * 4;
        if (th >= nh) th = ((int) Math.round(nh * scale) / 4) * 4;
        int td = nd > 0 ? Math.max(160, (int) Math.round(nd * scale)) : 0;
        return new int[]{tw, th, td};
    }

    /**
     * Phát hiện khả năng thực tế của thiết bị (không đánh dấu ảo):
     *   sdk, has_game_service, has_game_mode, has_device_config,
     *   has_wm, native_width, native_height, native_density,
     *   has_thermal, has_fps_unlock
     */
    static JSONObject detectPerfCapabilities(String packageName) {
        JSONObject out = new JSONObject();
        try {
            out.put("sdk", Build.VERSION.SDK_INT);

            boolean hasGameService = false;
            try {
                ExecResult svc = exec("service", "check", "game");
                String s = (svc.stdout + "\n" + svc.stderr).toLowerCase(Locale.ROOT);
                hasGameService = s.contains("found") && !s.contains("not found");
            } catch (Throwable ignored) {
            }

            boolean hasGameMode = false;
            try {
                ExecResult r = exec("cmd", "game", "list-modes", packageName);
                String s = (r.stdout + "\n" + r.stderr).trim().toLowerCase(Locale.ROOT);
                hasGameMode = r.exitCode == 0 && !s.contains("unknown command")
                        && !s.contains("can't find service") && !s.isEmpty();
                if (hasGameMode) hasGameService = true;
            } catch (Throwable ignored) {
            }
            out.put("has_game_service", hasGameService);
            out.put("has_game_mode", hasGameMode);

            // device_config game_overlay ONLY works if GameManagerService exists and OS isn't blocking writes
            // On Android 14+, allowlist restrictions commonly throw SecurityException on device_config put;
            // we treat it strictly as secondary fallback for Android 12/13 (API 31-33) when cmd game failed.
            boolean hasDc = !hasGameMode && hasGameService && Build.VERSION.SDK_INT >= 31 && Build.VERSION.SDK_INT <= 33;
            out.put("has_device_config", hasDc);

            int nw = 0, nh = 0, nd = 0;
            try {
                ExecResult rSize = exec("wm", "size");
                Matcher mPhys = Pattern.compile("Physical size:\\s*(\\d+)x(\\d+)", Pattern.CASE_INSENSITIVE)
                        .matcher(rSize.stdout);
                if (mPhys.find()) {
                    nw = Integer.parseInt(mPhys.group(1));
                    nh = Integer.parseInt(mPhys.group(2));
                }
                ExecResult rDens = exec("wm", "density");
                Matcher mDens = Pattern.compile("Physical density:\\s*(\\d+)", Pattern.CASE_INSENSITIVE)
                        .matcher(rDens.stdout);
                if (mDens.find()) {
                    nd = Integer.parseInt(mDens.group(1));
                }
                out.put("has_wm", nw > 0 && nh > 0);
            } catch (Throwable t) {
                out.put("has_wm", false);
            }
            out.put("native_width", nw);
            out.put("native_height", nh);
            out.put("native_density", nd);

            boolean hasThermal = false;
            try {
                ExecResult svc = exec("service", "check", "thermalservice");
                String s = (svc.stdout + "\n" + svc.stderr).toLowerCase(Locale.ROOT);
                hasThermal = s.contains("found") && !s.contains("not found");
                if (!hasThermal) {
                    ExecResult h = exec("cmd", "thermalservice", "help");
                    String hs = (h.stdout + "\n" + h.stderr).toLowerCase(Locale.ROOT);
                    hasThermal = h.exitCode == 0 && !hs.contains("can't find service") && !hs.contains("unknown command");
                }
            } catch (Throwable ignored) {
            }
            out.put("has_thermal", hasThermal);

            // Android 15+ (SDK >= 35) SurfaceFlinger 60Hz game cap unlock via Shizuku setprop
            boolean hasFpsUnlock = false;
            if (Build.VERSION.SDK_INT >= 35) {
                try {
                    ExecResult g1 = exec("getprop", "debug.graphics.game_default_frame_rate.disabled");
                    ExecResult g2 = exec("getprop", "ro.surface_flinger.game_default_frame_rate_override");
                    String v1 = g1.stdout.trim();
                    String v2 = g2.stdout.trim();
                    hasFpsUnlock = !v1.isEmpty() || !v2.isEmpty();
                } catch (Throwable ignored) {
                }
            }
            out.put("has_fps_unlock", hasFpsUnlock);
        } catch (Throwable t) {
            try { out.put("error", t.getMessage()); } catch (Throwable ignored) {}
        }
        return out;
    }

    /**
     * Áp dụng preset hiệu năng cross-device.
     */
    static String applyUniversalPreset(String packageName, JSONObject caps,
                                        int presetIdx, double customScale, int fpsTarget,
                                        boolean allowWmResize, boolean thermalOverride, boolean clearRam) {
        try {
            double scale = presetScaleForIndex(presetIdx, customScale);
            String presetName;
            switch (presetIdx) {
                case 0: presetName = "Máy yếu / Chống lag"; break;
                case 1: presetName = "Cân bằng mượt"; break;
                case 2: presetName = "Nguyên bản"; break;
                case 3: presetName = "Gaming Max"; break;
                default: presetName = "Tùy chỉnh"; break;
            }

            boolean hasGameMode  = caps.optBoolean("has_game_mode", false);
            boolean hasDc        = caps.optBoolean("has_device_config", false);
            boolean hasWm        = caps.optBoolean("has_wm", false);
            boolean hasThermal   = caps.optBoolean("has_thermal", false);
            boolean hasFpsUnlock = caps.optBoolean("has_fps_unlock", false);

            StringBuilder applied = new StringBuilder();
            boolean gameModeOk = false;
            boolean dcOk = false;

            // === Layer 1: Per-app GameMode (Pixel / AOSP GameManager) ===
            if (hasGameMode) {
                try {
                    String downscaleArg = (presetIdx == 2 || presetIdx == 3)
                            ? "disable"
                            : formatDownscaleArg(scale);
                    String gmRes = applyGameMode(packageName, downscaleArg, fpsTarget);
                    if (gmRes.startsWith("OK:")) {
                        gameModeOk = true;
                        applied.append("GameMode(")
                                .append("disable".equals(downscaleArg) ? "1.0×" : (downscaleArg + "×"))
                                .append(fpsTarget > 0 ? "/" + fpsTarget + "fps" : "")
                                .append(")");
                    }
                } catch (Throwable ignored) {
                }
            }

            // === Layer 2: device_config game_overlay (fallback Android 12/13 with game service) ===
            if (!gameModeOk && hasDc) {
                try {
                    if (presetIdx == 2 && fpsTarget <= 0) {
                        exec("device_config", "delete", "game_overlay", packageName);
                        dcOk = true;
                        applied.append("DeviceConfig(Reset)");
                    } else {
                        StringBuilder cfg = new StringBuilder();
                        cfg.append("mode=").append(presetIdx == 0 ? 3 : 2);
                        if (scale < 0.99) {
                            cfg.append(",downscaleFactor=").append(formatDownscaleArg(scale));
                        }
                        if (fpsTarget > 0) {
                            cfg.append(",fps=").append(fpsTarget);
                        }
                        ExecResult r = exec("device_config", "put", "game_overlay", packageName, cfg.toString());
                        String s = (r.stdout + " " + r.stderr).toLowerCase(Locale.ROOT);
                        if (r.exitCode == 0 && !s.contains("exception") && !s.contains("permission denial") && !s.contains("error")) {
                            dcOk = true;
                            applied.append("DeviceConfig");
                        }
                    }
                } catch (Throwable ignored) {
                }
            }

            // === Layer 3: WM Resolution Scaling (Universal fallback for non-GameMode devices) ===
            if (!gameModeOk && !dcOk && hasWm) {
                JSONObject st = probeUniversalPerfState(packageName, caps);
                boolean currentlyOverridden = st.optBoolean("wm_override", false) || st.optBoolean("wm_density_override", false);
                if (scale < 0.99 && allowWmResize) {
                    int nw = caps.optInt("native_width", 0);
                    int nh = caps.optInt("native_height", 0);
                    int nd = caps.optInt("native_density", 0);
                    int[] dim = computeScaledWmDimensions(nw, nh, nd, scale);
                    if (dim[0] > 0 && dim[1] > 0) {
                        ExecResult r1 = exec("wm", "size", dim[0] + "x" + dim[1]);
                        if (r1.exitCode == 0) {
                            if (dim[2] > 0) exec("wm", "density", Integer.toString(dim[2]));
                            if (applied.length() > 0) applied.append(" + ");
                            applied.append("WM(").append(dim[0]).append("×").append(dim[1]).append(")");
                        }
                    }
                } else if (currentlyOverridden && (scale >= 0.99 || !allowWmResize)) {
                    exec("wm", "size", "reset");
                    exec("wm", "density", "reset");
                    if (applied.length() > 0) applied.append(" + ");
                    applied.append("WM(Gốc)");
                }
            }

            // === Layer 4: Thermal Unlock (cmd thermalservice — Snapdragon / MediaTek / Pixel) ===
            if (hasThermal) {
                if (thermalOverride) {
                    try {
                        ExecResult r = exec("cmd", "thermalservice", "override-status", "0");
                        if (r.exitCode == 0) {
                            if (applied.length() > 0) applied.append(" + ");
                            applied.append("ThermalUnlock");
                        }
                    } catch (Throwable ignored) {
                    }
                } else {
                    try {
                        JSONObject st = probeUniversalPerfState(packageName, caps);
                        if (st.optBoolean("thermal_override", false)) {
                            exec("cmd", "thermalservice", "reset");
                            if (applied.length() > 0) applied.append(" + ");
                            applied.append("ThermalAuto");
                        }
                    } catch (Throwable ignored) {
                    }
                }
            }

            // === Layer 5: Android 15+ 60Hz Game Cap Unlock (all OEMs) ===
            if (hasFpsUnlock) {
                boolean wantUnlock = fpsTarget > 60 || (presetIdx == 3 && fpsTarget == 0);
                try {
                    ExecResult r = exec("setprop", "debug.graphics.game_default_frame_rate.disabled",
                            wantUnlock ? "true" : "false");
                    if (r.exitCode == 0 && wantUnlock) {
                        if (applied.length() > 0) applied.append(" + ");
                        applied.append("Unlock120Hz");
                    }
                } catch (Throwable ignored) {
                }
            }

            // === Layer 6: Background RAM Purge (Universal — helps 4GB/6GB/8GB phones) ===
            if (clearRam && presetIdx != 2) {
                try {
                    ExecResult r = exec("am", "kill-all");
                    if (r.exitCode == 0) {
                        if (applied.length() > 0) applied.append(" + ");
                        applied.append("DọnRAM");
                    }
                } catch (Throwable ignored) {
                }
            }

            if (applied.length() == 0) {
                if (presetIdx == 2) {
                    return "OK:Nguyên bản";
                }
                return "ERR:Không áp dụng được layer hệ thống nào trên ROM này. Hãy dùng Mod Mở Khóa Đồ Họa In-Game bên dưới!";
            }
            return "OK:" + applied + " · " + presetName
                    + (fpsTarget > 0 ? " (" + fpsTarget + " FPS)" : "");
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    /**
     * Reset toàn bộ các layer đang bật về mặc định hệ thống an toàn.
     */
    static String resetUniversalPreset(String packageName, JSONObject caps) {
        StringBuilder done = new StringBuilder();
        JSONObject st = probeUniversalPerfState(packageName, caps);

        if (caps != null && caps.optBoolean("has_game_mode", false)) {
            try {
                resetGameMode(packageName);
                done.append("GameMode ");
            } catch (Throwable ignored) {
            }
        }
        if (caps != null && caps.optBoolean("has_device_config", false) && !st.optString("dc_config", "").isEmpty()) {
            try {
                exec("device_config", "delete", "game_overlay", packageName);
                done.append("DeviceConfig ");
            } catch (Throwable ignored) {
            }
        }
        if (st.optBoolean("wm_override", false) || st.optBoolean("wm_density_override", false)) {
            try {
                exec("wm", "size", "reset");
                exec("wm", "density", "reset");
                done.append("WM ");
            } catch (Throwable ignored) {
            }
        }
        if (caps != null && caps.optBoolean("has_thermal", false)) {
            try {
                exec("cmd", "thermalservice", "reset");
                done.append("Thermal ");
            } catch (Throwable ignored) {
            }
        }
        if (caps != null && caps.optBoolean("has_fps_unlock", false)) {
            try {
                exec("setprop", "debug.graphics.game_default_frame_rate.disabled", "false");
                done.append("FPSLock60Hz ");
            } catch (Throwable ignored) {
            }
        }
        return "OK:" + (done.length() > 0 ? done.toString().trim() : "Nguyên bản");
    }

    /**
     * Probe trạng thái hiệu năng hiện tại (ONLY call from worker thread!).
     */
    static JSONObject probeUniversalPerfState(String packageName, JSONObject caps) {
        JSONObject out = new JSONObject();
        try {
            if (caps != null && caps.optBoolean("has_device_config", false)) {
                try {
                    ExecResult r = exec("device_config", "get", "game_overlay", packageName);
                    String v = r.stdout.trim();
                    out.put("dc_config", (r.exitCode == 0 && !v.equalsIgnoreCase("null")) ? v : "");
                } catch (Throwable t) {
                    out.put("dc_config", "");
                }
            } else {
                out.put("dc_config", "");
            }

            try {
                ExecResult r = exec("wm", "size");
                String s = r.stdout.trim();
                Matcher m = Pattern.compile("Override size:\\s*(\\d+x\\d+)", Pattern.CASE_INSENSITIVE).matcher(s);
                boolean hasOvr = m.find();
                out.put("wm_override", hasOvr);
                out.put("wm_size", hasOvr ? m.group(1) : "");

                ExecResult rd = exec("wm", "density");
                out.put("wm_density_override", rd.stdout.toLowerCase(Locale.ROOT).contains("override density"));
            } catch (Throwable t) {
                out.put("wm_override", false);
                out.put("wm_size", "");
                out.put("wm_density_override", false);
            }

            if (caps != null && caps.optBoolean("has_thermal", false)) {
                try {
                    ExecResult r = exec("dumpsys", "thermalservice");
                    String low = r.stdout.toLowerCase(Locale.ROOT);
                    out.put("thermal_override", low.contains("isstatusoverride: true"));
                } catch (Throwable t) {
                    out.put("thermal_override", false);
                }
            } else {
                out.put("thermal_override", false);
            }

            if (caps != null && caps.optBoolean("has_fps_unlock", false)) {
                try {
                    ExecResult r = exec("getprop", "debug.graphics.game_default_frame_rate.disabled");
                    out.put("fps_unlocked", "true".equalsIgnoreCase(r.stdout.trim()));
                } catch (Throwable t) {
                    out.put("fps_unlocked", false);
                }
            } else {
                out.put("fps_unlocked", false);
            }
        } catch (Throwable t) {
            try { out.put("error", t.getMessage()); } catch (Throwable ignored) {}
        }
        return out;
    }
}
