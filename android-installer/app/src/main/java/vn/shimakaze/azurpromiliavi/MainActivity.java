package vn.shimakaze.azurpromiliavi;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.IBinder;
import android.text.method.ScrollingMovementMethod;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import rikka.shizuku.Shizuku;

public class MainActivity extends Activity {

    private static final String REPO_SLUG = "shimakazevn/Azur-Promilia-Vietnamese-Translation-Script";
    private static final String LATEST_JSON_URL = "https://raw.githubusercontent.com/" + REPO_SLUG + "/main/latest-vi.json";
    private static final String RELEASES_API_URL = "https://api.github.com/repos/" + REPO_SLUG + "/releases/latest";
    private static final String RELEASES_PAGE_URL = "https://github.com/" + REPO_SLUG + "/releases/latest";
    private static final String SHIZUKU_RELEASES_URL = "https://github.com/RikkaApps/Shizuku/releases/latest";
    private static final String SHIZUKU_PLAY_URL = "https://play.google.com/store/apps/details?id=moe.shizuku.privileged.api";
    private static final String SHIZUKU_PKG = "moe.shizuku.privileged.api";
    private static final String GAME_PKG = "com.Yostar.AzurpromiliaJP";

    private static final int REQ_SHIZUKU_PERM = 1001;
    private static final int REQ_PICK_ZIP = 1002;

    private static final String PREFS_NAME = "azur_vi_mobile_prefs";
    private static final String KEY_INSTALLED_VER = "installed_patch_version";
    private static final String KEY_CACHED_PLAN = "cached_deployment_json";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private TextView tvUpdateBanner;
    private TextView tvShizukuStatus;
    private TextView tvGameStatus;
    private TextView tvRemoteStatus;
    private TextView tvProgressLabel;
    private ProgressBar progressBar;
    private TextView tvLog;

    private Button btnOpenShizuku;
    private Button btnGrantShizuku;
    private Button btnInstallOnline;
    private Button btnInstallOffline;
    private Button btnRestore;
    private Button btnOpenGame;
    private Button btnCheckUpdate;

    private volatile IViPatchService patchService = null;
    private boolean serviceBound = false;
    private boolean busy = false;
    private boolean autoUpdateDialogShown = false;

    private JSONObject remoteInfo = null;
    private String currentPlanJson = "";
    private JSONObject lastProbe = null;

    private final Shizuku.UserServiceArgs userServiceArgs =
            new Shizuku.UserServiceArgs(new ComponentName(BuildConfig.APPLICATION_ID, ViPatchService.class.getName()))
                    .daemon(false)
                    .processNameSuffix("vipatch")
                    .debuggable(BuildConfig.DEBUG)
                    .version(BuildConfig.VERSION_CODE);

    private final ServiceConnection serviceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            patchService = IViPatchService.Stub.asInterface(binder);
            serviceBound = true;
            log("Đã kết nối Shizuku UserService (UID 2000).");
            runOnUiThread(() -> updateShizukuUi());
            probeGameAsync();
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
            patchService = null;
            serviceBound = false;
            runOnUiThread(() -> updateShizukuUi());
        }
    };

    private final Shizuku.OnBinderReceivedListener binderReceivedListener = () -> runOnUiThread(() -> {
        updateShizukuUi();
        ensureServiceBound();
    });

    private final Shizuku.OnBinderDeadListener binderDeadListener = () -> {
        patchService = null;
        serviceBound = false;
        runOnUiThread(this::updateShizukuUi);
    };

    private final Shizuku.OnRequestPermissionResultListener permListener = (requestCode, grantResult) -> {
        if (requestCode == REQ_SHIZUKU_PERM) {
            boolean granted = grantResult == PackageManager.PERMISSION_GRANTED;
            log(granted ? "Đã cấp quyền Shizuku!" : "Bạn đã từ chối quyền Shizuku.");
            runOnUiThread(this::updateShizukuUi);
            if (granted) ensureServiceBound();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(Color.parseColor("#0B101B"));
            getWindow().setNavigationBarColor(Color.parseColor("#0B101B"));
        }

        currentPlanJson = loadInitialPlanJson();
        buildUi();

        Shizuku.addBinderReceivedListenerSticky(binderReceivedListener);
        Shizuku.addBinderDeadListener(binderDeadListener);
        Shizuku.addRequestPermissionResultListener(permListener);

        updateShizukuUi();
        probeGameAsync();
        ensureServiceBound();
        checkUpdatesAsync(true);
    }

    @Override
    protected void onResume() {
        super.onResume();
        updateShizukuUi();
        ensureServiceBound();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        Shizuku.removeBinderReceivedListener(binderReceivedListener);
        Shizuku.removeBinderDeadListener(binderDeadListener);
        Shizuku.removeRequestPermissionResultListener(permListener);
        if (serviceBound) {
            try {
                Shizuku.unbindUserService(userServiceArgs, serviceConnection, true);
            } catch (Throwable ignored) {
            }
        }
        executor.shutdownNow();
    }

    private String loadInitialPlanJson() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String cached = prefs.getString(KEY_CACHED_PLAN, "");
        if (!cached.isEmpty()) return cached;
        try (InputStream is = getAssets().open("android-deployment-vi.json")) {
            byte[] data = readAllBytes(is);
            return new String(data, StandardCharsets.UTF_8);
        } catch (Throwable t) {
            return "";
        }
    }

    // -------------------------------------------------------------------------
    // UI Construction (Dark Luxury Modern Theme)
    // -------------------------------------------------------------------------
    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#0B101B"));
        scroll.setFillViewport(true);
        scroll.setFitsSystemWindows(true);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(16);
        root.setPadding(pad, dp(20), pad, dp(24));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            scroll.setOnApplyWindowInsetsListener((v, insets) -> {
                root.setPadding(pad, dp(16) + insets.getSystemWindowInsetTop(), pad, dp(20) + insets.getSystemWindowInsetBottom());
                return insets;
            });
        }
        scroll.addView(root);

        // Header
        TextView title = new TextView(this);
        title.setText("Azur Promilia — Việt Hóa Mobile");
        title.setTextColor(Color.parseColor("#F8FAFC"));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 21);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("App " + BuildConfig.VERSION_NAME + " · Không cần Root · Giữ nguyên chữ ký APK gốc");
        subtitle.setTextColor(Color.parseColor("#94A3B8"));
        subtitle.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f);
        subtitle.setPadding(0, dp(4), 0, dp(12));
        root.addView(subtitle);

        // Auto-update alert banner (hidden until update found)
        tvUpdateBanner = new TextView(this);
        tvUpdateBanner.setVisibility(View.GONE);
        tvUpdateBanner.setTextColor(Color.parseColor("#ECFDF5"));
        tvUpdateBanner.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f);
        tvUpdateBanner.setTypeface(Typeface.DEFAULT_BOLD);
        tvUpdateBanner.setPadding(dp(14), dp(12), dp(14), dp(12));
        tvUpdateBanner.setBackground(makeCardBg("#064E3B", "#10B981", 12));
        LinearLayout.LayoutParams bannerLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bannerLp.bottomMargin = dp(12);
        root.addView(tvUpdateBanner, bannerLp);

        // Card 1: Shizuku Status
        LinearLayout cShizuku = makeCard(root, "1. Quyền hệ thống (Shizuku)");
        tvShizukuStatus = makeBodyText(cShizuku, "Đang kiểm tra Shizuku...");

        LinearLayout rowShizuku = makeRow(cShizuku);
        btnOpenShizuku = makeButton(rowShizuku, "Mở / Tải Shizuku", "#1E293B", "#E2E8F0", 1);
        btnGrantShizuku = makeButton(rowShizuku, "Cấp quyền", "#0284C7", "#FFFFFF", 1);
        Button btnGuide = makeButton(rowShizuku, "Hướng dẫn", "#334155", "#F8FAFC", 1);

        btnOpenShizuku.setOnClickListener(v -> openOrInstallShizuku());
        btnGrantShizuku.setOnClickListener(v -> requestShizukuPermission());
        btnGuide.setOnClickListener(v -> showGuideDialog());

        // Card 2: Game & Patch Status
        LinearLayout cGame = makeCard(root, "2. Trạng thái Game & Việt Hóa");
        tvGameStatus = makeBodyText(cGame, "Đang quét thư mục dữ liệu game...");
        tvRemoteStatus = makeBodyText(cGame, "GitHub: đang kiểm tra bản mới nhất...");
        tvRemoteStatus.setTextColor(Color.parseColor("#7DD3FC"));

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setProgress(0);
        progressBar.setVisibility(View.GONE);
        LinearLayout.LayoutParams pbLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(8));
        pbLp.topMargin = dp(8);
        cGame.addView(progressBar, pbLp);

        tvProgressLabel = new TextView(this);
        tvProgressLabel.setVisibility(View.GONE);
        tvProgressLabel.setTextColor(Color.parseColor("#CBD5E1"));
        tvProgressLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        tvProgressLabel.setPadding(0, dp(4), 0, 0);
        cGame.addView(tvProgressLabel);

        btnInstallOnline = makeButton(cGame, "Tải & Cài Đặt Việt Hóa (GitHub)", "#10B981", "#042F2E", 0);
        btnInstallOnline.setTypeface(Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams mainBtnLp = (LinearLayout.LayoutParams) btnInstallOnline.getLayoutParams();
        mainBtnLp.topMargin = dp(10);
        btnInstallOnline.setOnClickListener(v -> startOnlineInstall());

        LinearLayout rowSec = makeRow(cGame);
        btnInstallOffline = makeButton(rowSec, "Chọn file .ZIP offline", "#1E293B", "#E2E8F0", 1);
        btnCheckUpdate = makeButton(rowSec, "Check cập nhật", "#1E293B", "#7DD3FC", 1);
        btnInstallOffline.setOnClickListener(v -> pickOfflineZip());
        btnCheckUpdate.setOnClickListener(v -> {
            autoUpdateDialogShown = false;
            checkUpdatesAsync(true);
            probeGameAsync();
        });

        LinearLayout rowActions = makeRow(cGame);
        btnRestore = makeButton(rowActions, "Khôi phục gốc", "#7F1D1D", "#FECACA", 1);
        btnOpenGame = makeButton(rowActions, "Mở Azur Promilia", "#2563EB", "#FFFFFF", 1);
        btnRestore.setOnClickListener(v -> confirmRestore());
        btnOpenGame.setOnClickListener(v -> launchGame());

        // Card 3: Activity Log
        LinearLayout cLog = makeCard(root, "Nhật ký xử lý");
        tvLog = new TextView(this);
        tvLog.setTextColor(Color.parseColor("#CBD5E1"));
        tvLog.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f);
        tvLog.setTypeface(Typeface.MONOSPACE);
        tvLog.setMovementMethod(new ScrollingMovementMethod());
        tvLog.setMinLines(6);
        tvLog.setMaxLines(12);
        cLog.addView(tvLog);

        setContentView(scroll);
        log("Khởi động tool (" + BuildConfig.VERSION_NAME + "). Đang kiểm tra GitHub...");
    }

    private LinearLayout makeCard(LinearLayout parent, String heading) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        int p = dp(14);
        card.setPadding(p, p, p, p);
        card.setBackground(makeCardBg("#141C2B", "#23304A", 14));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(12);
        parent.addView(card, lp);

        TextView h = new TextView(this);
        h.setText(heading);
        h.setTextColor(Color.parseColor("#F1F5F9"));
        h.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        h.setTypeface(Typeface.DEFAULT_BOLD);
        h.setPadding(0, 0, 0, dp(6));
        card.addView(h);
        return card;
    }

    private TextView makeBodyText(LinearLayout parent, String text) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextColor(Color.parseColor("#CBD5E1"));
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        tv.setPadding(0, dp(2), 0, dp(4));
        parent.addView(tv);
        return tv;
    }

    private LinearLayout makeRow(LinearLayout parent) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(8);
        parent.addView(row, lp);
        return row;
    }

    private Button makeButton(LinearLayout parent, String label, String bgHex, String fgHex, int weight) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.parseColor(fgHex));
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f);
        b.setBackground(makeCardBg(bgHex, "#334155", 10));
        b.setPadding(dp(8), dp(8), dp(8), dp(8));
        b.setMinimumHeight(dp(40));
        LinearLayout.LayoutParams lp;
        if (weight > 0) {
            lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, weight);
            lp.setMargins(dp(3), 0, dp(3), 0);
        } else {
            lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }
        parent.addView(b, lp);
        return b;
    }

    private GradientDrawable makeCardBg(String fillHex, String strokeHex, int radiusDp) {
        GradientDrawable gd = new GradientDrawable();
        gd.setColor(Color.parseColor(fillHex));
        gd.setCornerRadius(dp(radiusDp));
        gd.setStroke(dp(1), Color.parseColor(strokeHex));
        return gd;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    // -------------------------------------------------------------------------
    // Shizuku State & Binding
    // -------------------------------------------------------------------------
    private boolean isPackageInstalled(String pkg) {
        try {
            getPackageManager().getPackageInfo(pkg, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    private void setBtnEnabled(Button b, boolean enabled) {
        b.setEnabled(enabled);
        b.setAlpha(enabled ? 1.0f : 0.42f);
    }

    private void updateShizukuUi() {
        boolean shizukuInstalled = isPackageInstalled(SHIZUKU_PKG);
        boolean binderAlive = false;
        boolean permGranted = false;
        try {
            binderAlive = Shizuku.pingBinder();
            if (binderAlive) {
                permGranted = Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED;
            }
        } catch (Throwable ignored) {
        }

        if (!shizukuInstalled) {
            tvShizukuStatus.setText("🔴 Chưa cài ứng dụng Shizuku.\nNhấn 'Tải Shizuku' hoặc xem 'Hướng dẫn'.");
            btnOpenShizuku.setText("Tải Shizuku");
            setBtnEnabled(btnGrantShizuku, false);
        } else if (!binderAlive) {
            tvShizukuStatus.setText("🟡 Đã cài Shizuku nhưng CHƯA BẬT.\nHãy mở Shizuku → Ghép đôi / Bắt đầu bằng Gỡ lỗi không dây.");
            btnOpenShizuku.setText("Mở Shizuku");
            setBtnEnabled(btnGrantShizuku, false);
        } else if (!permGranted) {
            tvShizukuStatus.setText("🟡 Shizuku đang chạy! Cần bấm 'Cấp quyền' cho tool.");
            btnOpenShizuku.setText("Mở Shizuku");
            setBtnEnabled(btnGrantShizuku, true);
        } else if (!serviceBound || patchService == null) {
            tvShizukuStatus.setText("🟡 Đã cấp quyền Shizuku, đang kết nối UserService...");
            btnOpenShizuku.setText("Mở Shizuku");
            setBtnEnabled(btnGrantShizuku, false);
        } else {
            tvShizukuStatus.setText("🟢 Shizuku sẵn sàng (UID 2000 — đọc/ghi được Android/data)");
            btnOpenShizuku.setText("Mở Shizuku");
            setBtnEnabled(btnGrantShizuku, false);
        }

        boolean ready = binderAlive && permGranted && serviceBound && patchService != null && !busy;
        setBtnEnabled(btnInstallOnline, ready);
        setBtnEnabled(btnInstallOffline, ready);
        setBtnEnabled(btnRestore, ready);
        setBtnEnabled(btnOpenGame, isPackageInstalled(GAME_PKG));
    }

    private void ensureServiceBound() {
        try {
            if (!Shizuku.pingBinder()) return;
            if (Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) return;
            if (!serviceBound) {
                Shizuku.bindUserService(userServiceArgs, serviceConnection);
            }
        } catch (Throwable t) {
            log("Lỗi kết nối Shizuku: " + t.getMessage());
        }
    }

    private void requestShizukuPermission() {
        try {
            if (!Shizuku.pingBinder()) {
                toast("Shizuku chưa chạy! Hãy mở Shizuku trước.");
                return;
            }
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
                ensureServiceBound();
                return;
            }
            Shizuku.requestPermission(REQ_SHIZUKU_PERM);
        } catch (Throwable t) {
            toast("Lỗi xin quyền Shizuku: " + t.getMessage());
        }
    }

    private void openOrInstallShizuku() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(SHIZUKU_PKG);
        if (launch != null) {
            startActivity(launch);
        } else {
            new AlertDialog.Builder(this)
                    .setTitle("Tải ứng dụng Shizuku")
                    .setMessage("Chọn nguồn tải Shizuku chính chủ:")
                    .setPositiveButton("Google Play", (d, w) -> openUrl(SHIZUKU_PLAY_URL))
                    .setNeutralButton("GitHub APK", (d, w) -> openUrl(SHIZUKU_RELEASES_URL))
                    .setNegativeButton("Đóng", null)
                    .show();
        }
    }

    private void showGuideDialog() {
        String msg =
                "📱 HƯỚNG DẪN CÀI VIỆT HÓA ANDROID (KHÔNG CẦN ROOT / KHÔNG CẦN PC)\n\n" +
                "1️⃣ Cài game Azur Promilia JP bản gốc từ CH Play/APKPure/TapTap, đăng nhập và tải XONG toàn bộ dữ liệu trong game, sau đó ĐÓNG HẲN GAME.\n\n" +
                "2️⃣ Tải & cài đặt ứng dụng 'Shizuku' (nút Tải Shizuku).\n\n" +
                "3️⃣ Bật Shizuku ngay trên điện thoại bằng Wi-Fi:\n" +
                "   • Cài đặt → Giới thiệu điện thoại → Chạm 7 lần vào 'Số bản dựng' (Build number) để bật Tùy chọn nhà phát triển.\n" +
                "   • Vào Hệ thống → Tùy chọn nhà phát triển → Bật 'Gỡ lỗi không dây' (Wireless debugging).\n" +
                "   • Mở Shizuku → mục 'Bắt đầu qua Gỡ lỗi không dây' → bấm 'Ghép đôi' (Pairing), nhập mã 6 số hiện trên thông báo → quay lại Shizuku bấm 'Bắt đầu' (Start).\n\n" +
                "4️⃣ Quay lại app này:\n" +
                "   • Bấm 'Cấp quyền' Shizuku (chọn Cho phép).\n" +
                "   • Bấm 'Tải & Cài Đặt Việt Hóa (GitHub)' → đợi 15-30s là xong!\n\n" +
                "ℹ️ Lưu ý:\n" +
                "   • Không sửa/ký lại APK nên an toàn chữ ký gốc.\n" +
                "   • Khi có bản mới trên GitHub, mở app lên sẽ báo tự động ngay để cập nhật 1 chạm!";
        new AlertDialog.Builder(this)
                .setTitle("Hướng dẫn sử dụng")
                .setMessage(msg)
                .setPositiveButton("Đã hiểu", null)
                .show();
    }

    // -------------------------------------------------------------------------
    // Game Probe
    // -------------------------------------------------------------------------
    private String getGameFilesDir() {
        return Environment.getExternalStorageDirectory().getAbsolutePath() + "/Android/data/" + GAME_PKG + "/files";
    }

    private void probeGameAsync() {
        final IViPatchService svc = patchService;
        if (svc == null) {
            runOnUiThread(() -> {
                if (!isPackageInstalled(GAME_PKG)) {
                    tvGameStatus.setText("❌ Chưa cài game Azur Promilia JP (" + GAME_PKG + ").");
                } else {
                    tvGameStatus.setText("⏳ Đã cài Azur Promilia JP. Bật & cấp quyền Shizuku ở mục (1) để kiểm tra & cài Việt hóa.");
                }
            });
            return;
        }
        executor.execute(() -> {
            try {
                String res = svc.probeGameState(getGameFilesDir(), currentPlanJson);
                JSONObject obj = new JSONObject(res);
                lastProbe = obj;
                runOnUiThread(() -> renderProbeState(obj));
            } catch (Throwable t) {
                log("Lỗi kiểm tra thư mục game: " + t.getMessage());
            }
        });
    }

    private void renderProbeState(JSONObject obj) {
        if (!isPackageInstalled(GAME_PKG)) {
            tvGameStatus.setText("❌ Chưa cài game Azur Promilia JP (" + GAME_PKG + ").");
            return;
        }
        if (obj.has("error")) {
            tvGameStatus.setText("⚠️ Lỗi đọc thư mục game: " + obj.optString("error"));
            return;
        }
        boolean resExists = obj.optBoolean("res_exists", false);
        if (!resExists) {
            tvGameStatus.setText("⚠️ Chưa thấy thư mục .res/. Hãy mở game tải xong dữ liệu lần đầu rồi quay lại!");
            return;
        }
        String det = obj.optString("detected_version", "");
        int total = obj.optInt("total", 0);
        int vi = obj.optInt("vi_count", 0);
        int orig = obj.optInt("orig_count", 0);
        int bak = obj.optInt("backup_count", 0);
        String verInstalled = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(KEY_INSTALLED_VER, "");

        StringBuilder sb = new StringBuilder();
        sb.append("• Game JP: Đã cài · Resource ver: ").append(det.isEmpty() ? "?" : det).append("\n");
        if (total > 0) {
            if (vi == total) {
                sb.append("✅ Đã Việt hóa ").append(vi).append("/").append(total).append(" file");
                if (!verInstalled.isEmpty()) sb.append(" (").append(verInstalled).append(")");
            } else if (orig == total) {
                sb.append("📦 Đang ở bản gốc JP (").append(orig).append("/").append(total).append(" file) — sẵn sàng cài!");
            } else {
                sb.append("ℹ️ Việt hóa: ").append(vi).append("/").append(total)
                  .append(" · Gốc: ").append(orig).append("/").append(total);
            }
            sb.append(" · Backup gốc: ").append(bak).append("/").append(total);
        }
        tvGameStatus.setText(sb.toString());
        evaluateUpdateNotifications();
    }

    // -------------------------------------------------------------------------
    // Auto-Update Check (GitHub latest-vi.json + Releases API fallback)
    // -------------------------------------------------------------------------
    private void checkUpdatesAsync(boolean showPopupIfNew) {
        executor.execute(() -> {
            try {
                log("Đang kiểm tra bản mới trên GitHub...");
                JSONObject data = fetchRemoteInfo();
                if (data == null) {
                    runOnUiThread(() -> tvRemoteStatus.setText("⚠️ Không kiểm tra được GitHub (vẫn cài được từ file .ZIP offline)."));
                    return;
                }
                remoteInfo = data;
                runOnUiThread(() -> {
                    String ver = data.optString("version", "");
                    JSONObject an = data.optJSONObject("android");
                    String rVer = an != null ? an.optString("resource_version", "") : "";
                    long sz = an != null ? an.optLong("size", 0) : 0;
                    String apkVer = (an != null && an.optJSONObject("apk") != null)
                            ? an.optJSONObject("apk").optString("version", "") : "";
                    tvRemoteStatus.setText(String.format(Locale.ROOT,
                            "🌐 Bản mới nhất trên GitHub: %s (Mobile res %s · %.1f MB%s)",
                            ver, rVer, sz / (1024.0 * 1024.0),
                            apkVer.isEmpty() ? "" : " · App " + apkVer));
                    evaluateUpdateNotifications();
                    if (showPopupIfNew) maybeShowUpdatePopup();
                });
            } catch (Throwable t) {
                log("Lỗi check GitHub: " + t.getMessage());
            }
        });
    }

    private JSONObject fetchRemoteInfo() {
        // 1. Try raw latest-vi.json with cache buster
        try {
            String raw = httpGetString(LATEST_JSON_URL + "?t=" + System.currentTimeMillis());
            if (raw != null && raw.trim().startsWith("{")) {
                JSONObject j = new JSONObject(raw);
                if (j.has("android")) return j;
            }
        } catch (Throwable ignored) {
        }
        // 2. Fallback to GitHub Releases API
        try {
            String api = httpGetString(RELEASES_API_URL);
            if (api != null) {
                JSONObject rel = new JSONObject(api);
                String tag = rel.optString("tag_name", "");
                JSONArray assets = rel.optJSONArray("assets");
                String zipUrl = "", zipName = "", apkUrl = "", apkName = "";
                long zipSize = 0, apkSize = 0;
                if (assets != null) {
                    for (int i = 0; i < assets.length(); i++) {
                        JSONObject a = assets.getJSONObject(i);
                        String n = a.optString("name", "");
                        if (n.startsWith("AzurPromilia-Localization-Android-vi-") && n.endsWith(".zip")) {
                            zipUrl = a.optString("browser_download_url", "");
                            zipName = n;
                            zipSize = a.optLong("size", 0);
                        } else if (n.equals("AzurPromilia-VI-Mobile.apk")) {
                            apkUrl = a.optString("browser_download_url", "");
                            apkName = n;
                            apkSize = a.optLong("size", 0);
                        }
                    }
                }
                if (!zipUrl.isEmpty()) {
                    JSONObject out = new JSONObject();
                    out.put("version", tag);
                    out.put("notes", rel.optString("body", ""));
                    JSONObject an = new JSONObject();
                    an.put("resource_version", "3219596");
                    an.put("filename", zipName);
                    an.put("size", zipSize);
                    an.put("sha256", "");
                    an.put("url", zipUrl);
                    if (!apkUrl.isEmpty()) {
                        JSONObject apk = new JSONObject();
                        apk.put("version", tag);
                        apk.put("filename", apkName);
                        apk.put("size", apkSize);
                        apk.put("sha256", "");
                        apk.put("url", apkUrl);
                        an.put("apk", apk);
                    }
                    out.put("android", an);
                    return out;
                }
            }
        } catch (Throwable ignored) {
        }
        return null;
    }

    private void evaluateUpdateNotifications() {
        if (remoteInfo == null) return;
        String remotePatchVer = remoteInfo.optString("version", "");
        JSONObject an = remoteInfo.optJSONObject("android");
        JSONObject apk = an != null ? an.optJSONObject("apk") : null;
        String remoteApkVer = apk != null ? apk.optString("version", "") : "";

        boolean hasNewApk = !remoteApkVer.isEmpty() && compareSemver(remoteApkVer, BuildConfig.VERSION_NAME) > 0;
        String localPatchVer = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(KEY_INSTALLED_VER, "");
        boolean gameAlreadyVi = lastProbe != null
                && lastProbe.optInt("total", 0) > 0
                && lastProbe.optInt("vi_count", 0) == lastProbe.optInt("total", 0);
        boolean hasNewPatch = !remotePatchVer.isEmpty() && (
                (!localPatchVer.isEmpty() && compareSemver(remotePatchVer, localPatchVer) > 0)
                || (gameAlreadyVi && localPatchVer.isEmpty())
                || (lastProbe != null && lastProbe.optInt("orig_count", 0) > 0)
        );

        if (hasNewApk) {
            tvUpdateBanner.setVisibility(View.VISIBLE);
            tvUpdateBanner.setBackground(makeCardBg("#1E3A8A", "#38BDF8", 12));
            tvUpdateBanner.setText("🔔 CÓ BẢN APP MỚI " + remoteApkVer + " (hiện tại " + BuildConfig.VERSION_NAME + ") — Chạm vào đây để cập nhật App!");
            tvUpdateBanner.setOnClickListener(v -> startSelfApkUpdate(apk));
        } else if (hasNewPatch && !localPatchVer.isEmpty() && compareSemver(remotePatchVer, localPatchVer) > 0) {
            tvUpdateBanner.setVisibility(View.VISIBLE);
            tvUpdateBanner.setBackground(makeCardBg("#064E3B", "#10B981", 12));
            tvUpdateBanner.setText("🆕 Đã có bản Việt Hóa mới " + remotePatchVer + " (đang cài " + localPatchVer + ") — Bấm nút 'Tải & Cài Đặt' hoặc chạm đây!");
            tvUpdateBanner.setOnClickListener(v -> startOnlineInstall());
        } else {
            tvUpdateBanner.setVisibility(View.GONE);
        }
    }

    private void maybeShowUpdatePopup() {
        if (autoUpdateDialogShown || remoteInfo == null) return;
        JSONObject an = remoteInfo.optJSONObject("android");
        if (an == null) return;
        JSONObject apk = an.optJSONObject("apk");
        String remoteApkVer = apk != null ? apk.optString("version", "") : "";
        String remotePatchVer = remoteInfo.optString("version", "");
        String localPatchVer = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(KEY_INSTALLED_VER, "");
        String notes = remoteInfo.optString("notes", "");

        if (!remoteApkVer.isEmpty() && compareSemver(remoteApkVer, BuildConfig.VERSION_NAME) > 0) {
            autoUpdateDialogShown = true;
            new AlertDialog.Builder(this)
                    .setTitle("Có bản App Việt Hóa mới (" + remoteApkVer + ")")
                    .setMessage("Phiên bản app hiện tại: " + BuildConfig.VERSION_NAME + "\nPhiên bản mới trên GitHub: " + remoteApkVer + "\n\n" + notes)
                    .setPositiveButton("Tải & Cài đặt App", (d, w) -> startSelfApkUpdate(apk))
                    .setNegativeButton("Để sau", null)
                    .show();
        } else if (!remotePatchVer.isEmpty() && !localPatchVer.isEmpty() && compareSemver(remotePatchVer, localPatchVer) > 0) {
            autoUpdateDialogShown = true;
            new AlertDialog.Builder(this)
                    .setTitle("Có bản dịch Việt Hóa mới (" + remotePatchVer + ")")
                    .setMessage("Bản đang cài trên máy: " + localPatchVer + "\nBản mới trên GitHub: " + remotePatchVer + "\n\n" + notes)
                    .setPositiveButton("Cập nhật ngay", (d, w) -> startOnlineInstall())
                    .setNegativeButton("Để sau", null)
                    .show();
        }
    }

    private static int compareSemver(String a, String b) {
        int[] pa = parseSemver(a);
        int[] pb = parseSemver(b);
        for (int i = 0; i < 3; i++) {
            if (pa[i] != pb[i]) return Integer.compare(pa[i], pb[i]);
        }
        return 0;
    }

    private static int[] parseSemver(String v) {
        int[] res = new int[]{0, 0, 0};
        if (v == null) return res;
        String clean = v.trim();
        if (clean.startsWith("v") || clean.startsWith("V")) clean = clean.substring(1);
        int dash = clean.indexOf('-');
        if (dash >= 0) clean = clean.substring(0, dash);
        String[] parts = clean.split("\\.");
        for (int i = 0; i < Math.min(3, parts.length); i++) {
            try {
                res[i] = Integer.parseInt(parts[i].replaceAll("[^0-9]", ""));
            } catch (NumberFormatException ignored) {
            }
        }
        return res;
    }

    // -------------------------------------------------------------------------
    // Self-update APK
    // -------------------------------------------------------------------------
    private void startSelfApkUpdate(JSONObject apkObj) {
        if (busy || apkObj == null) return;
        String url = apkObj.optString("url", "");
        String expectedSha = apkObj.optString("sha256", "").toLowerCase(Locale.ROOT);
        if (url.isEmpty()) {
            openUrl(RELEASES_PAGE_URL);
            return;
        }
        setBusy(true);
        executor.execute(() -> {
            try {
                File dir = new File(getExternalFilesDir(null), "updates");
                dir.mkdirs();
                File apkFile = new File(dir, "AzurPromilia-VI-Mobile-update.apk");
                log("Đang tải APK mới: " + url);
                downloadFile(url, apkFile, apkObj.optLong("size", 0), "Đang tải APK mới");
                if (!expectedSha.isEmpty()) {
                    String got = sha256File(apkFile);
                    if (!got.equals(expectedSha)) {
                        throw new RuntimeException("SHA-256 APK tải về không khớp!");
                    }
                }
                log("Tải APK hoàn tất, mở trình cài đặt...");
                runOnUiThread(() -> {
                    setBusy(false);
                    try {
                        Uri contentUri = FileProvider.getUriForFile(this, BuildConfig.APPLICATION_ID + ".fileprovider", apkFile);
                        Intent intent = new Intent(Intent.ACTION_VIEW);
                        intent.setDataAndType(contentUri, "application/vnd.android.package-archive");
                        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(intent);
                    } catch (Throwable t) {
                        log("Không mở được bộ cài trực tiếp (" + t.getMessage() + "), mở trình duyệt...");
                        openUrl(url);
                    }
                });
            } catch (Throwable t) {
                log("❌ Lỗi tải APK mới: " + t.getMessage());
                runOnUiThread(() -> {
                    setBusy(false);
                    toast("Lỗi tải APK: " + t.getMessage());
                });
            }
        });
    }

    // -------------------------------------------------------------------------
    // Install / Restore Flows
    // -------------------------------------------------------------------------
    private void startOnlineInstall() {
        if (busy) return;
        if (patchService == null) {
            toast("Shizuku chưa sẵn sàng!");
            return;
        }
        if (remoteInfo == null || remoteInfo.optJSONObject("android") == null) {
            toast("Chưa lấy được thông tin từ GitHub. Thử bấm 'Check cập nhật' hoặc chọn file .ZIP offline.");
            return;
        }
        JSONObject an = remoteInfo.optJSONObject("android");
        String url = an.optString("url", "");
        String expectedSha = an.optString("sha256", "").toLowerCase(Locale.ROOT);
        long expectedSize = an.optLong("size", 0);
        String ver = remoteInfo.optString("version", "v1.0.2");

        setBusy(true);
        executor.execute(() -> {
            File zipFile = new File(getExternalFilesDir(null), "android_patch_download.zip");
            try {
                boolean cachedOk = zipFile.isFile() && !expectedSha.isEmpty() && sha256File(zipFile).equals(expectedSha);
                if (cachedOk) {
                    log("Dùng lại file ZIP đã tải trước (SHA-256 khớp).");
                } else {
                    log("Đang tải gói Việt hóa Mobile (" + ver + ") từ GitHub...");
                    downloadFile(url, zipFile, expectedSize, "Đang tải gói Việt hóa");
                    if (!expectedSha.isEmpty()) {
                        setProgressUi(true, 100, "Đang kiểm tra SHA-256...");
                        String got = sha256File(zipFile);
                        if (!got.equals(expectedSha)) {
                            zipFile.delete();
                            throw new RuntimeException("SHA-256 file ZIP không khớp! (" + got + ")");
                        }
                    }
                }
                applyFromZipStream(new FileInputStream(zipFile), ver);
            } catch (Throwable t) {
                log("❌ Lỗi cài đặt Online: " + t.getMessage());
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 0, "");
                    toast("Lỗi: " + t.getMessage());
                });
            }
        });
    }

    private void pickOfflineZip() {
        if (busy) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/zip", "application/x-zip-compressed", "application/octet-stream"});
        startActivityForResult(intent, REQ_PICK_ZIP);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_PICK_ZIP && resultCode == RESULT_OK && data != null && data.getData() != null) {
            final Uri uri = data.getData();
            if (patchService == null) {
                toast("Shizuku chưa sẵn sàng!");
                return;
            }
            setBusy(true);
            executor.execute(() -> {
                try {
                    log("Đang giải nén file ZIP đã chọn...");
                    InputStream is = getContentResolver().openInputStream(uri);
                    if (is == null) throw new RuntimeException("Không đọc được file đã chọn.");
                    applyFromZipStream(is, "offline");
                } catch (Throwable t) {
                    log("❌ Lỗi cài đặt Offline: " + t.getMessage());
                    runOnUiThread(() -> {
                        setBusy(false);
                        setProgressUi(false, 0, "");
                        toast("Lỗi: " + t.getMessage());
                    });
                }
            });
        }
    }

    private void applyFromZipStream(InputStream rawIn, String labelVer) throws Exception {
        File staging = new File(getExternalFilesDir(null), "staging");
        deleteRecursive(staging);
        staging.mkdirs();

        setProgressUi(true, 15, "Đang giải nén vào staging...");
        String extractedManifest = null;
        int fileCount = 0;

        try (ZipInputStream zis = new ZipInputStream(new BufferedInputStream(rawIn))) {
            ZipEntry entry;
            byte[] buf = new byte[524288];
            while ((entry = zis.getNextEntry()) != null) {
                if (entry.isDirectory()) continue;
                String name = entry.getName().replace('\\', '/');
                // Accept paths like android_game/..., tools/android-deployment-vi.json, or stripped prefix
                String cleanRel = null;
                if (name.endsWith("android-deployment-vi.json")) {
                    ByteArrayOutputStream bos = new ByteArrayOutputStream();
                    int n;
                    while ((n = zis.read(buf)) > 0) bos.write(buf, 0, n);
                    extractedManifest = new String(bos.toByteArray(), StandardCharsets.UTF_8);
                    continue;
                }
                int idx = name.indexOf("raw_base_package/");
                if (idx < 0) idx = name.indexOf("raw_streaming_package/");
                if (idx < 0) idx = name.indexOf("default_package/");
                if (idx >= 0) {
                    cleanRel = name.substring(idx);
                }
                if (cleanRel == null || cleanRel.contains("..")) continue;

                File out = new File(staging, cleanRel);
                out.getParentFile().mkdirs();
                try (FileOutputStream fos = new FileOutputStream(out)) {
                    int n;
                    while ((n = zis.read(buf)) > 0) fos.write(buf, 0, n);
                }
                fileCount++;
                setProgressUi(true, Math.min(70, 15 + fileCount * 8), "Đã giải nén " + fileCount + " file .r...");
            }
        }

        if (extractedManifest == null || extractedManifest.isEmpty()) {
            if (currentPlanJson.isEmpty()) throw new RuntimeException("Gói ZIP thiếu android-deployment-vi.json!");
            extractedManifest = currentPlanJson;
        } else {
            currentPlanJson = extractedManifest;
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putString(KEY_CACHED_PLAN, extractedManifest).apply();
        }

        log("Đang đóng game nếu còn chạy ngầm...");
        patchService.forceStopGame(GAME_PKG);

        setProgressUi(true, 85, "Đang sao lưu bản gốc & chép file Việt hóa (Shizuku)...");
        String result = patchService.installFromStaging(staging.getAbsolutePath(), getGameFilesDir(), extractedManifest);
        deleteRecursive(staging);

        if (result == null || !result.startsWith("OK:")) {
            throw new RuntimeException(result == null ? "Không nhận được phản hồi từ Shizuku" : result.replaceFirst("^ERR:", ""));
        }

        if (!"offline".equals(labelVer)) {
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putString(KEY_INSTALLED_VER, labelVer).apply();
        }
        log("🎉 HOÀN TẤT! Đã cài đặt thành công " + result.substring(3) + " file Việt hóa + verify SHA-256.");
        runOnUiThread(() -> {
            setBusy(false);
            setProgressUi(false, 100, "");
            probeGameAsync();
            new AlertDialog.Builder(this)
                    .setTitle("Cài đặt Việt Hóa thành công!")
                    .setMessage("Đã backup bản gốc an toàn và chép xong toàn bộ file Việt Hóa (đã kiểm tra SHA-256).\n\nBạn có thể mở game ngay bây giờ!")
                    .setPositiveButton("Mở Game Ngay", (d, w) -> launchGame())
                    .setNegativeButton("Đóng", null)
                    .show();
        });
    }

    private void confirmRestore() {
        if (busy || patchService == null) return;
        new AlertDialog.Builder(this)
                .setTitle("Khôi phục bản gốc JP?")
                .setMessage("Thao tác này sẽ trả lại 7 file gốc ban đầu từ bản sao lưu để gỡ Việt Hóa.")
                .setPositiveButton("Khôi phục", (d, w) -> runRestore())
                .setNegativeButton("Hủy", null)
                .show();
    }

    private void runRestore() {
        if (currentPlanJson.isEmpty()) {
            toast("Chưa có manifest android-deployment-vi.json để khôi phục.");
            return;
        }
        setBusy(true);
        executor.execute(() -> {
            try {
                patchService.forceStopGame(GAME_PKG);
                setProgressUi(true, 50, "Đang khôi phục bản gốc...");
                String res = patchService.restoreFromBackup(getGameFilesDir(), currentPlanJson);
                if (res == null || !res.startsWith("OK:")) {
                    throw new RuntimeException(res == null ? "Shizuku null" : res.replaceFirst("^ERR:", ""));
                }
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().remove(KEY_INSTALLED_VER).apply();
                log("↩️ Đã khôi phục bản gốc JP (" + res.substring(3) + " file) và kiểm tra SHA-256 thành công.");
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 0, "");
                    probeGameAsync();
                    toast("Đã khôi phục về bản gốc JP!");
                });
            } catch (Throwable t) {
                log("❌ Lỗi khôi phục: " + t.getMessage());
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 0, "");
                    toast("Lỗi: " + t.getMessage());
                });
            }
        });
    }

    private void launchGame() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(GAME_PKG);
        if (launch != null) {
            startActivity(launch);
        } else {
            toast("Không tìm thấy Azur Promilia JP trên máy.");
        }
    }

    // -------------------------------------------------------------------------
    // HTTP & File Helpers
    // -------------------------------------------------------------------------
    private String httpGetString(String urlStr) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(15000);
        conn.setRequestProperty("User-Agent", "AzurPromiliaVIMobile/" + BuildConfig.VERSION_NAME);
        try {
            int code = conn.getResponseCode();
            if (code >= 400) throw new RuntimeException("HTTP " + code);
            try (InputStream is = conn.getInputStream()) {
                return new String(readAllBytes(is), StandardCharsets.UTF_8);
            }
        } finally {
            conn.disconnect();
        }
    }

    private void downloadFile(String urlStr, File dest, long fallbackTotal, String label) throws Exception {
        File tmp = new File(dest.getParentFile(), dest.getName() + ".dl");
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        conn.setInstanceFollowRedirects(true);
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(30000);
        conn.setRequestProperty("User-Agent", "AzurPromiliaVIMobile/" + BuildConfig.VERSION_NAME);
        try {
            int code = conn.getResponseCode();
            if (code >= 400) throw new RuntimeException("HTTP " + code);
            long total = conn.getContentLengthLong();
            if (total <= 0) total = fallbackTotal;
            byte[] buf = new byte[262144];
            long readSum = 0;
            long lastUi = 0;
            try (InputStream is = new BufferedInputStream(conn.getInputStream());
                 FileOutputStream fos = new FileOutputStream(tmp)) {
                int n;
                while ((n = is.read(buf)) > 0) {
                    fos.write(buf, 0, n);
                    readSum += n;
                    long now = System.currentTimeMillis();
                    if (now - lastUi > 180) {
                        lastUi = now;
                        int pct = total > 0 ? (int) Math.min(99, (readSum * 100L) / total) : 0;
                        String msg = String.format(Locale.ROOT, "%s: %.1f / %.1f MB (%d%%)",
                                label, readSum / (1024.0 * 1024.0),
                                total > 0 ? total / (1024.0 * 1024.0) : 0.0, pct);
                        setProgressUi(true, pct, msg);
                    }
                }
            }
            if (dest.exists()) dest.delete();
            if (!tmp.renameTo(dest)) throw new RuntimeException("Không lưu được file tải về");
        } finally {
            conn.disconnect();
        }
    }

    private static byte[] readAllBytes(InputStream is) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
        return bos.toByteArray();
    }

    private static String sha256File(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buf = new byte[524288];
        try (InputStream is = new FileInputStream(f)) {
            int n;
            while ((n = is.read(buf)) > 0) md.update(buf, 0, n);
        }
        byte[] d = md.digest();
        StringBuilder sb = new StringBuilder(64);
        for (byte b : d) sb.append(String.format(Locale.ROOT, "%02x", b & 0xFF));
        return sb.toString();
    }

    private static void deleteRecursive(File f) {
        if (f == null || !f.exists()) return;
        if (f.isDirectory()) {
            File[] children = f.listFiles();
            if (children != null) {
                for (File c : children) deleteRecursive(c);
            }
        }
        f.delete();
    }

    private void openUrl(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Throwable t) {
            toast("Không mở được liên kết: " + url);
        }
    }

    private void setBusy(boolean b) {
        busy = b;
        runOnUiThread(this::updateShizukuUi);
    }

    private void setProgressUi(boolean visible, int pct, String msg) {
        runOnUiThread(() -> {
            progressBar.setVisibility(visible ? View.VISIBLE : View.GONE);
            tvProgressLabel.setVisibility(visible ? View.VISIBLE : View.GONE);
            progressBar.setProgress(pct);
            tvProgressLabel.setText(msg);
        });
    }

    private void log(String s) {
        String ts = new SimpleDateFormat("HH:mm:ss", Locale.ROOT).format(new Date());
        runOnUiThread(() -> {
            tvLog.append("[" + ts + "] " + s + "\n");
        });
    }

    private void toast(String s) {
        runOnUiThread(() -> Toast.makeText(this, s, Toast.LENGTH_LONG).show());
    }
}
