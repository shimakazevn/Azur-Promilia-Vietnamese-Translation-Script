package vn.shimakaze.azurpromiliavi;

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
                    + "  break\n"
                    + "done\n";
            ExecResult res = exec("sh", "-c", script, "sh", gameFilesDir);
            if (res.exitCode != 0) return "";
            String line = res.stdout.trim();
            int nl = line.indexOf('\n');
            return nl >= 0 ? line.substring(0, nl).trim() : line;
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
            int origCount = 0;
            int missingCount = 0;
            int mismatchCount = 0;
            int backupCount = 0;

            for (int i = 0; i < total; i++) {
                JSONObject item = arr.getJSONObject(i);
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);

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
                if (!staged.isFile() || staged.length() != size || !sha256File(staged).equals(tgtSha)) {
                    return "ERR:Gói tải về bị lỗi hoặc thiếu file: " + rel;
                }
                stagedFiles.add(staged);
            }

            // Step 2: Backup originals and write patched files atomically as UID 2000
            String script = "set -e\n"
                    + "gf=\"$1\"; ver=\"$2\"; rel=\"$3\"; stg=\"$4\"; src_sha=\"$5\"; tgt_sha=\"$6\"; exp_sz=\"$7\"\n"
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
                    + "elif [ \"$cur\" != \"$tgt_sha\" ]; then\n"
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
                File staged = stagedFiles.get(i);

                ExecResult r = exec("sh", "-c", script, "sh",
                        gameFilesDir, targetVer, rel, staged.getAbsolutePath(),
                        srcSha, tgtSha, Long.toString(size));
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
}
