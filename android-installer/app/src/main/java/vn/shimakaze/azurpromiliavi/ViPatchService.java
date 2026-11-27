package vn.shimakaze.azurpromiliavi;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.util.Locale;

public class ViPatchService extends IViPatchService.Stub {

    public ViPatchService() {
    }

    @Override
    public void destroy() {
        System.exit(0);
    }

    @Override
    public String detectResVersion(String gameFilesDir) {
        try {
            File mfDir = new File(gameFilesDir, ".res/raw_base_package/ManifestFiles");
            if (!mfDir.isDirectory()) return "";
            File[] files = mfDir.listFiles();
            if (files == null) return "";
            for (File f : files) {
                String n = f.getName();
                if (n.startsWith("0release_raw_base_package_") && n.endsWith(".bytes")) {
                    return n.substring("0release_raw_base_package_".length(), n.length() - ".bytes".length());
                }
            }
            return "";
        } catch (Throwable t) {
            return "";
        }
    }

    @Override
    public String forceStopGame(String packageName) {
        try {
            Process p = new ProcessBuilder("am", "force-stop", packageName).redirectErrorStream(true).start();
            int rc = p.waitFor();
            return rc == 0 ? "OK" : ("RC=" + rc);
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    @Override
    public String probeGameState(String gameFilesDir, String manifestJson) {
        try {
            JSONObject out = new JSONObject();
            File gf = new File(gameFilesDir);
            File resDir = new File(gf, ".res");
            String detectedVer = detectResVersion(gameFilesDir);
            out.put("files_dir_exists", gf.isDirectory());
            out.put("res_exists", resDir.isDirectory());
            out.put("detected_version", detectedVer);

            if (manifestJson == null || manifestJson.trim().isEmpty()) {
                return out.toString();
            }

            JSONObject plan = new JSONObject(manifestJson);
            String targetVer = plan.optString("resource_version", "");
            out.put("target_version", targetVer);
            File reqManifest = new File(resDir, "raw_base_package/ManifestFiles/0release_raw_base_package_" + targetVer + ".bytes");
            out.put("manifest_matched", reqManifest.isFile());

            JSONArray arr = plan.getJSONArray("files");
            File backupRoot = new File(gf, ".vi-android-backup-" + targetVer);

            int total = arr.length();
            int viCount = 0;
            int perfCount = 0;
            int origCount = 0;
            int missingCount = 0;
            int mismatchCount = 0;
            int backupCount = 0;

            for (int i = 0; i < total; i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path");
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                String perfSha = item.optString("perf_target_sha256", "").toLowerCase(Locale.ROOT);

                File dest = new File(resDir, rel);
                if (!dest.isFile()) {
                    missingCount++;
                } else if (dest.length() != size) {
                    mismatchCount++;
                } else {
                    String h = sha256(dest);
                    if (h.equals(tgtSha)) {
                        viCount++;
                    } else if (!perfSha.isEmpty() && h.equals(perfSha)) {
                        viCount++;
                        perfCount++;
                    } else if (h.equals(srcSha)) {
                        origCount++;
                    } else {
                        mismatchCount++;
                    }
                }

                File bak = new File(backupRoot, rel);
                if (bak.isFile() && bak.length() == size && sha256(bak).equals(srcSha)) {
                    backupCount++;
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
            return "{\"error\":\"" + t.getMessage() + "\"}";
        }
    }

    private static String computePayloadHash(JSONArray arr) throws Exception {
        java.util.List<String> rows = new java.util.ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) {
            JSONObject item = arr.getJSONObject(i);
            String rel = item.getString("relative_path").replace('\\', '/');
            String tgt = item.getString("target_sha256").toLowerCase(Locale.ROOT);
            rows.add(rel + ":" + tgt + "\n");
        }
        java.util.Collections.sort(rows);
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        for (String r : rows) {
            md.update(r.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }
        byte[] digest = md.digest();
        StringBuilder sb = new StringBuilder(64);
        for (byte b : digest) {
            sb.append(String.format(Locale.ROOT, "%02x", b & 0xFF));
        }
        return sb.toString();
    }

    @Override
    public String installFromStaging(String stagingDir, String gameFilesDir, String manifestJson) {
        try {
            JSONObject plan = new JSONObject(manifestJson);
            String targetVer = plan.getString("resource_version");
            JSONArray arr = plan.getJSONArray("files");

            File gf = new File(gameFilesDir);
            File resDir = new File(gf, ".res");
            File stDir = new File(stagingDir);
            File backupRoot = new File(gf, ".vi-android-backup-" + targetVer);

            File reqManifest = new File(resDir, "raw_base_package/ManifestFiles/0release_raw_base_package_" + targetVer + ".bytes");
            if (!reqManifest.isFile()) {
                String found = detectResVersion(gameFilesDir);
                return "ERR:Phiên bản tài nguyên game không khớp (cần " + targetVer + ", trên máy là " + (found.isEmpty() ? "chưa tải" : found) + ")";
            }

            // Step 1: Verify every staged file before touching game assets
            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path");
                long size = item.getLong("size");
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                File staged = new File(stDir, rel);
                if (!staged.isFile()) {
                    staged = new File(stDir, "android_game/" + rel);
                }
                if (!staged.isFile()) {
                    staged = new File(stDir, "android_perf/" + rel);
                }
                if (!staged.isFile() || staged.length() != size || !sha256(staged).equals(tgtSha)) {
                    return "ERR:Gói tải về bị lỗi hoặc thiếu file: " + rel;
                }
            }

            // Step 2: Backup intact original files & install atomically
            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path");
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                String tgtSha = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                String altSha = item.optString("perf_target_sha256", "").toLowerCase(Locale.ROOT);

                File dest = new File(resDir, rel);
                if (!dest.isFile()) {
                    return "ERR:Game chưa tải đủ file này (hãy vào game tải full data trước): " + rel;
                }

                // Only backup if current dest is verified original and backup does not yet hold verified original
                String curSha = sha256(dest);
                if (curSha.equals(srcSha)) {
                    File bak = new File(backupRoot, rel);
                    if (!bak.isFile() || !sha256(bak).equals(srcSha)) {
                        copyFile(dest, bak);
                        if (!sha256(bak).equals(srcSha)) {
                            return "ERR:Lỗi tạo backup cho " + rel;
                        }
                    }
                } else if (!curSha.equals(tgtSha) && (altSha.isEmpty() || !curSha.equals(altSha))) {
                    return "ERR:File gốc trên máy không khớp baseline (" + rel + "), hãy Verify tài nguyên trong game trước.";
                }

                if (curSha.equals(tgtSha)) {
                    continue; // already at target v1.0.2+
                }

                File staged = new File(stDir, rel);
                if (!staged.isFile()) staged = new File(stDir, "android_game/" + rel);
                if (!staged.isFile()) staged = new File(stDir, "android_perf/" + rel);

                File tmp = new File(dest.getParentFile(), dest.getName() + ".vitmp");
                copyFile(staged, tmp);
                if (tmp.length() != size || !sha256(tmp).equals(tgtSha)) {
                    tmp.delete();
                    return "ERR:Kiểm tra SHA-256 sau khi ghi tạm thất bại: " + rel;
                }
                if (dest.exists() && !dest.delete()) {
                    // Fallback direct overwrite if delete refused
                    copyFile(staged, dest);
                    tmp.delete();
                } else if (!tmp.renameTo(dest)) {
                    copyFile(tmp, dest);
                    tmp.delete();
                }
                if (!dest.isFile() || !sha256(dest).equals(tgtSha)) {
                    return "ERR:Kiểm tra SHA-256 cuối thất bại: " + rel;
                }
            }
            return "OK:" + arr.length();
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    @Override
    public String restoreFromBackup(String gameFilesDir, String manifestJson) {
        try {
            JSONObject plan = new JSONObject(manifestJson);
            String targetVer = plan.getString("resource_version");
            JSONArray arr = plan.getJSONArray("files");

            File gf = new File(gameFilesDir);
            File resDir = new File(gf, ".res");
            File backupRoot = new File(gf, ".vi-android-backup-" + targetVer);

            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path");
                long size = item.getLong("size");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                File bak = new File(backupRoot, rel);
                if (!bak.isFile() || bak.length() != size || !sha256(bak).equals(srcSha)) {
                    return "ERR:Thiếu hoặc hỏng file backup: " + rel;
                }
            }

            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path");
                String srcSha = item.getString("source_sha256").toLowerCase(Locale.ROOT);
                File bak = new File(backupRoot, rel);
                File dest = new File(resDir, rel);
                File tmp = new File(dest.getParentFile(), dest.getName() + ".vitmp");
                copyFile(bak, tmp);
                if (dest.exists()) dest.delete();
                if (!tmp.renameTo(dest)) {
                    copyFile(tmp, dest);
                    tmp.delete();
                }
                if (!sha256(dest).equals(srcSha)) {
                    return "ERR:Khôi phục thất bại cho " + rel;
                }
            }
            return "OK:" + arr.length();
        } catch (Throwable t) {
            return "ERR:" + t.getMessage();
        }
    }

    private static void copyFile(File src, File dst) throws IOException {
        File parent = dst.getParentFile();
        if (parent != null && !parent.exists()) {
            parent.mkdirs();
        }
        byte[] buf = new byte[1048576];
        try (FileInputStream in = new FileInputStream(src);
             FileOutputStream out = new FileOutputStream(dst, false)) {
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            out.getFD().sync();
        }
    }

    private static String sha256(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buf = new byte[1048576];
        try (FileInputStream in = new FileInputStream(f)) {
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
