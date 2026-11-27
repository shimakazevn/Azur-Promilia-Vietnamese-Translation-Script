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
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.text.method.ScrollingMovementMethod;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import android.provider.Settings;

import androidx.core.content.FileProvider;
import androidx.core.content.pm.PackageInfoCompat;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

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
    private static final String RELEASE_LATEST_JSON_URL = "https://github.com/" + REPO_SLUG + "/releases/latest/download/latest-vi.json";
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
    private static final String KEY_INSTALLED_ZIP_SHA = "installed_patch_zip_sha256";
    private static final String KEY_INSTALLED_PAYLOAD_HASH = "installed_patch_payload_hash";
    private static final String KEY_CACHED_PLAN = "cached_deployment_json";
    private static final String KEY_CACHED_PLAN_APK_VER = "cached_plan_apk_ver";
    private static final String KEY_PERF_PRESET = "perf_preset_idx";
    private static final String KEY_PERF_FPS = "perf_fps_idx";
    private static final String KEY_PERF_CUSTOM_PCT = "perf_custom_pct";
    private static final String KEY_PERF_THERMAL = "perf_thermal_unlock";
    private static final String KEY_PERF_WM = "perf_wm_downscale";

    private static final String[] PERF_PRESET_LABELS = {
            "🔋 Máy yếu / Chống lag (Render 0.60× + Dọn RAM)",
            "⚡ Cân bằng / Mượt & Rõ (Render 0.75× + Dọn RAM)",
            "⚖️ Nguyên bản / Mặc định hệ thống (1.00×)",
            "🔥 Gaming Max / Flagship (1.00× + Mở khóa nhiệt & Hz)",
            "✏️ Tùy chỉnh (Custom GPU Scale 0.45×–1.50×)"
    };
    private static final String[] PERF_FPS_LABELS = {
            "Mặc định game (Không ép FPS)",
            "Giới hạn 30 FPS",
            "Giới hạn 45 FPS",
            "Giới hạn 60 FPS",
            "Giới hạn 90 FPS",
            "Giới hạn 120 FPS"
    };
    private static final int[] PERF_FPS_VALUES = {0, 30, 45, 60, 90, 120};

    private final ExecutorService workerExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService netExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private static final long USER_SERVICE_TIMEOUT_MS = 3000L;

    private TextView tvUpdateBanner;
    private TextView tvShizukuStatus;
    private TextView tvGameStatus;
    private TextView tvRemoteStatus;
    private TextView tvProgressLabel;
    private ProgressBar progressBar;
    private TextView tvGameModeStatus;
    private TextView tvCustomScaleLabel;
    private TextView tvInGamePerfStatus;
    private TextView tvLog;

    private Spinner spPerfPreset;
    private Spinner spPerfFps;
    private LinearLayout layoutCustomScale;
    private SeekBar sbCustomScale;
    private CheckBox cbThermalUnlock;
    private CheckBox cbWmDownscale;

    private Button btnOpenShizuku;
    private Button btnGrantShizuku;
    private Button btnInstallOnline;
    private Button btnInstallOffline;
    private Button btnRestore;
    private Button btnOpenGame;
    private Button btnCheckUpdate;
    private Button btnApplyGameMode;
    private Button btnResetGameMode;
    private Button btnToggleInGamePerf;

    private volatile JSONObject lastGameMode = null;
    private volatile JSONObject lastPerfCaps = null;   // detectPerfCapabilities() result
    private volatile JSONObject lastPerfState = null;  // probeUniversalPerfState() result (background thread)

    private volatile IViPatchService patchService = null;
    private volatile boolean serviceBound = false;
    private volatile boolean shellBackendReady = false;
    private volatile String shellUid = "";
    private volatile boolean serviceBindingInFlight = false;
    private volatile boolean preferDirectShell = false;
    private volatile String lastConnectError = "";
    private volatile int probeSeq = 0;
    private boolean busy = false;
    private boolean autoUpdateDialogShown = false;

    private JSONObject remoteInfo = null;
    private String currentPlanJson = "";
    private JSONObject lastProbe = null;
    private File pendingInstallApk = null;

    private final Runnable bindTimeoutRunnable = this::onUserServiceBindTimeout;

    private final Shizuku.UserServiceArgs userServiceArgs =
            new Shizuku.UserServiceArgs(new ComponentName(BuildConfig.APPLICATION_ID, ViPatchService.class.getName()))
                    .daemon(false)
                    .processNameSuffix("vipatch")
                    .debuggable(BuildConfig.DEBUG)
                    .version(BuildConfig.VERSION_CODE);

    private final ServiceConnection serviceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            mainHandler.removeCallbacks(bindTimeoutRunnable);
            patchService = IViPatchService.Stub.asInterface(binder);
            serviceBound = true;
            serviceBindingInFlight = false;
            lastConnectError = "";
            if (!shellBackendReady) {
                log("Đã kết nối Shizuku UserService (UID 2000).");
            }
            runOnUiThread(() -> updateShizukuUi());
            probeGameAsync();
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
            patchService = null;
            serviceBound = false;
            serviceBindingInFlight = false;
            runOnUiThread(() -> updateShizukuUi());
        }
    };

    private final Shizuku.OnBinderReceivedListener binderReceivedListener = () -> runOnUiThread(() -> {
        updateShizukuUi();
        ensureServiceBound(false);
    });

    private final Shizuku.OnBinderDeadListener binderDeadListener = () -> {
        mainHandler.removeCallbacks(bindTimeoutRunnable);
        patchService = null;
        serviceBound = false;
        shellBackendReady = false;
        shellUid = "";
        serviceBindingInFlight = false;
        lastConnectError = "";
        lastPerfCaps = null;
        lastPerfState = null;
        lastGameMode = null;
        runOnUiThread(this::updateShizukuUi);
    };

    private final Shizuku.OnRequestPermissionResultListener permListener = (requestCode, grantResult) -> {
        if (requestCode == REQ_SHIZUKU_PERM) {
            boolean granted = grantResult == PackageManager.PERMISSION_GRANTED;
            log(granted ? "Đã cấp quyền Shizuku!" : "Bạn đã từ chối quyền Shizuku.");
            lastConnectError = "";
            runOnUiThread(this::updateShizukuUi);
            if (granted) ensureServiceBound(true);
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
        preferDirectShell = getIntent() != null && getIntent().getBooleanExtra("force_shell", false);
        buildUi();

        Shizuku.addBinderReceivedListenerSticky(binderReceivedListener);
        Shizuku.addBinderDeadListener(binderDeadListener);
        Shizuku.addRequestPermissionResultListener(permListener);

        updateShizukuUi();
        probeGameAsync();
        ensureServiceBound(false);
        checkUpdatesAsync(true);
    }

    @Override
    protected void onResume() {
        super.onResume();
        updateShizukuUi();
        ensureServiceBound(false);
        if (pendingInstallApk != null && pendingInstallApk.isFile()
                && (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getPackageManager().canRequestPackageInstalls())) {
            File toInstall = pendingInstallApk;
            pendingInstallApk = null;
            launchApkInstaller(toInstall);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        mainHandler.removeCallbacks(bindTimeoutRunnable);
        Shizuku.removeBinderReceivedListener(binderReceivedListener);
        Shizuku.removeBinderDeadListener(binderDeadListener);
        Shizuku.removeRequestPermissionResultListener(permListener);
        if (serviceBound) {
            try {
                Shizuku.unbindUserService(userServiceArgs, serviceConnection, true);
            } catch (Throwable ignored) {
            }
        }
        workerExecutor.shutdownNow();
        netExecutor.shutdownNow();
    }

    private String loadInitialPlanJson() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String cached = prefs.getString(KEY_CACHED_PLAN, "");
        String bundled = "";
        try (InputStream is = getAssets().open("android-deployment-vi.json")) {
            bundled = new String(readAllBytes(is), StandardCharsets.UTF_8);
        } catch (Throwable ignored) {
        }
        if (cached.isEmpty()) {
            return bundled;
        }
        if (!bundled.isEmpty()) {
            try {
                long cachedApkVer = prefs.getLong(KEY_CACHED_PLAN_APK_VER, 0);
                JSONObject cObj = new JSONObject(cached);
                JSONObject bObj = new JSONObject(bundled);
                String cVer = cObj.optString("resource_version", "");
                String bVer = bObj.optString("resource_version", "");
                boolean missingPerfHash = bundled.contains("perf_target_sha256") && !cached.contains("perf_target_sha256");
                if (bVer.equals(cVer) && (cachedApkVer < BuildConfig.VERSION_CODE || missingPerfHash)) {
                    prefs.edit()
                            .putString(KEY_CACHED_PLAN, bundled)
                            .putLong(KEY_CACHED_PLAN_APK_VER, BuildConfig.VERSION_CODE)
                            .apply();
                    return bundled;
                }
            } catch (Throwable ignored) {
            }
        }
        return cached;
    }

    // -------------------------------------------------------------------------
    // UI Construction (Dark Luxury Modern Theme)
    // -------------------------------------------------------------------------
    private void buildUi() {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(Color.parseColor("#0B101B"));
        ViewCompat.setOnApplyWindowInsetsListener(outer, (v, windowInsets) -> {
            Insets insets = windowInsets.getInsets(
                    WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            v.setPadding(insets.left, insets.top, insets.right, insets.bottom);
            return WindowInsetsCompat.CONSUMED;
        });

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#0B101B"));
        scroll.setFillViewport(true);
        scroll.setClipToPadding(true);
        outer.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(16);
        root.setPadding(pad, dp(16), pad, dp(24));
        scroll.addView(root);

        // Header
        TextView title = new TextView(this);
        title.setText("Azur Promilia — Việt Hóa Mobile");
        title.setTextColor(Color.parseColor("#F8FAFC"));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 21);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("App " + getAppVersionName() + " · Không cần Root · Giữ nguyên chữ ký APK gốc");
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

        // Card 3: Performance & Graphics Mod (Multi-Device: Low-End + Gaming)
        LinearLayout cPerf = makeCard(root, "3. Mod Đồ Họa & Hiệu Năng (Đa thiết bị)");
        tvGameModeStatus = makeBodyText(cPerf, "⏳ Bật Shizuku để nhận diện phần cứng & tối ưu FPS (hỗ trợ cả máy yếu lẫn máy Gaming).");
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        int savedPreset = Math.max(0, Math.min(4, prefs.getInt(KEY_PERF_PRESET, 2)));
        int savedFpsIdx = Math.max(0, Math.min(PERF_FPS_VALUES.length - 1, prefs.getInt(KEY_PERF_FPS, 0)));
        int savedCustomPct = Math.max(45, Math.min(150, prefs.getInt(KEY_PERF_CUSTOM_PCT, 85)));
        boolean savedThermal = prefs.getBoolean(KEY_PERF_THERMAL, savedPreset == 3);
        boolean savedWm = prefs.getBoolean(KEY_PERF_WM, true);

        makeSmallLabel(cPerf, "Preset hiệu năng (tự động chọn phương thức phù hợp với máy):");
        spPerfPreset = makeDarkSpinner(cPerf, PERF_PRESET_LABELS, savedPreset);

        layoutCustomScale = new LinearLayout(this);
        layoutCustomScale.setOrientation(LinearLayout.VERTICAL);
        layoutCustomScale.setVisibility(savedPreset == 4 ? View.VISIBLE : View.GONE);
        layoutCustomScale.setPadding(0, dp(4), 0, dp(4));
        tvCustomScaleLabel = makeBodyText(layoutCustomScale,
                String.format(Locale.ROOT, "Tỷ lệ Render GPU tùy chỉnh: %.2f×", savedCustomPct / 100.0));
        sbCustomScale = new SeekBar(this);
        sbCustomScale.setMax(21); // 45%..150% step 5% -> (150-45)/5 = 21 steps
        sbCustomScale.setProgress((savedCustomPct - 45) / 5);
        layoutCustomScale.addView(sbCustomScale);
        cPerf.addView(layoutCustomScale);

        cbThermalUnlock = makeCheckBox(cPerf,
                "🌡️ Mở khóa nhiệt độ (Thermal Unlock — chống bóp FPS máy Gaming / nóng máy)",
                savedThermal);
        cbWmDownscale = makeCheckBox(cPerf,
                "📐 Hạ phân giải màn hình WM khi máy yếu không hỗ trợ GameMode (nhắc trước khi đổi)",
                savedWm);

        cbThermalUnlock.setOnCheckedChangeListener((buttonView, isChecked) ->
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putBoolean(KEY_PERF_THERMAL, isChecked).apply());
        cbWmDownscale.setOnCheckedChangeListener((buttonView, isChecked) ->
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putBoolean(KEY_PERF_WM, isChecked).apply());

        final int[] prevPreset = new int[]{savedPreset};
        spPerfPreset.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int pos, long id) {
                layoutCustomScale.setVisibility(pos == 4 ? View.VISIBLE : View.GONE);
                if (pos != prevPreset[0]) {
                    prevPreset[0] = pos;
                    boolean autoThermal = (pos == 3);
                    cbThermalUnlock.setChecked(autoThermal);
                    getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                            .putInt(KEY_PERF_PRESET, pos)
                            .putBoolean(KEY_PERF_THERMAL, autoThermal)
                            .apply();
                }
            }
            @Override
            public void onNothingSelected(AdapterView<?> parent) {}
        });
        sbCustomScale.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                int pct = 45 + progress * 5; // 45%–150%
                String note = pct == 100 ? " (Native gốc)" : (pct > 100 ? " (Siêu nét — tùy ROM/In-Game)" : " (Giảm tải GPU máy yếu)");
                tvCustomScaleLabel.setText(String.format(Locale.ROOT, "Tỷ lệ Render GPU tùy chỉnh: %.2f×%s", pct / 100.0, note));
                if (fromUser) {
                    getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putInt(KEY_PERF_CUSTOM_PCT, pct).apply();
                }
            }
            @Override public void onStartTrackingTouch(SeekBar seekBar) {}
            @Override public void onStopTrackingTouch(SeekBar seekBar) {}
        });

        makeSmallLabel(cPerf, "Giới hạn / Mở khóa FPS hệ thống (Android 15+ mở khóa 60Hz, tới 120 FPS):");
        spPerfFps = makeDarkSpinner(cPerf, PERF_FPS_LABELS, savedFpsIdx);
        spPerfFps.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int pos, long id) {
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putInt(KEY_PERF_FPS, pos).apply();
            }
            @Override public void onNothingSelected(AdapterView<?> parent) {}
        });

        LinearLayout rowGameMode = makeRow(cPerf);
        btnApplyGameMode = makeButton(rowGameMode, "Áp dụng Preset GPU/FPS", "#0284C7", "#FFFFFF", 1);
        btnResetGameMode = makeButton(rowGameMode, "Về mặc định", "#334155", "#E2E8F0", 1);
        btnApplyGameMode.setOnClickListener(v -> applySelectedGameMode());
        btnResetGameMode.setOnClickListener(v -> resetSelectedGameMode());

        View div = new View(this);
        div.setBackgroundColor(Color.parseColor("#23304A"));
        LinearLayout.LayoutParams dlp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1));
        dlp.topMargin = dp(10);
        dlp.bottomMargin = dp(8);
        cPerf.addView(div, dlp);

        tvInGamePerfStatus = makeBodyText(cPerf,
                "🎨 Mở Khóa Đồ Họa In-Game (Mọi máy): Tải riêng 1 file (~24 MB) mở khóa Tỷ lệ kết xuất 50%-170%, SSAA OFF, GI/AO/Phản chiếu, DoF, LightShaft.");
        btnToggleInGamePerf = makeButton(cPerf, "Bật Mở Khóa Đồ Họa In-Game", "#0F766E", "#FFFFFF", 0);
        btnToggleInGamePerf.setOnClickListener(v -> toggleInGamePerfMod());

        // Card 4: Activity Log
        LinearLayout cLog = makeCard(root, "Nhật ký xử lý");
        tvLog = new TextView(this);
        tvLog.setTextColor(Color.parseColor("#CBD5E1"));
        tvLog.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f);
        tvLog.setTypeface(Typeface.MONOSPACE);
        tvLog.setMovementMethod(new ScrollingMovementMethod());
        tvLog.setMinLines(6);
        tvLog.setMaxLines(12);
        cLog.addView(tvLog);

        setContentView(outer);
        log("Khởi động tool (" + getAppVersionName() + "). Đang kiểm tra GitHub...");
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

    private TextView makeSmallLabel(LinearLayout parent, String text) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextColor(Color.parseColor("#94A3B8"));
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(6);
        lp.bottomMargin = dp(3);
        parent.addView(tv, lp);
        return tv;
    }

    private CheckBox makeCheckBox(LinearLayout parent, String text, boolean checked) {
        CheckBox cb = new CheckBox(this);
        cb.setText(text);
        cb.setChecked(checked);
        cb.setTextColor(Color.parseColor("#CBD5E1"));
        cb.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(4);
        parent.addView(cb, lp);
        return cb;
    }

    private Spinner makeDarkSpinner(LinearLayout parent, String[] items, int selectedIdx) {
        Spinner sp = new Spinner(this);
        sp.setBackground(makeCardBg("#1E293B", "#334155", 10));
        int p = dp(6);
        sp.setPadding(p, dp(2), p, dp(2));
        ArrayAdapter<String> ad = new ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, items) {
            @Override
            public View getView(int position, View convertView, ViewGroup parentView) {
                TextView tv = (TextView) super.getView(position, convertView, parentView);
                tv.setTextColor(Color.parseColor("#F8FAFC"));
                tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
                tv.setPadding(dp(8), dp(8), dp(8), dp(8));
                return tv;
            }

            @Override
            public View getDropDownView(int position, View convertView, ViewGroup parentView) {
                TextView tv = (TextView) super.getDropDownView(position, convertView, parentView);
                tv.setBackgroundColor(Color.parseColor("#1E293B"));
                tv.setTextColor(Color.parseColor("#F8FAFC"));
                tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
                tv.setPadding(dp(12), dp(12), dp(12), dp(12));
                return tv;
            }
        };
        sp.setAdapter(ad);
        if (selectedIdx >= 0 && selectedIdx < items.length) {
            sp.setSelection(selectedIdx, false);
        }
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(4);
        parent.addView(sp, lp);
        return sp;
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

    private boolean isBackendReady() {
        return (serviceBound && patchService != null) || shellBackendReady;
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

        boolean backendReady = isBackendReady();

        if (!shizukuInstalled) {
            tvShizukuStatus.setText("🔴 Chưa cài ứng dụng Shizuku.\nNhấn 'Tải Shizuku' hoặc xem 'Hướng dẫn'.");
            btnOpenShizuku.setText("Tải Shizuku");
            btnGrantShizuku.setText("Cấp quyền");
            setBtnEnabled(btnGrantShizuku, false);
        } else if (!binderAlive) {
            tvShizukuStatus.setText("🟡 Đã cài Shizuku nhưng CHƯA BẬT.\nHãy mở Shizuku → Ghép đôi / Bắt đầu bằng Gỡ lỗi không dây.");
            btnOpenShizuku.setText("Mở Shizuku");
            btnGrantShizuku.setText("Cấp quyền");
            setBtnEnabled(btnGrantShizuku, false);
        } else if (!permGranted) {
            tvShizukuStatus.setText("🟡 Shizuku đang chạy! Cần bấm 'Cấp quyền' cho tool.");
            btnOpenShizuku.setText("Mở Shizuku");
            btnGrantShizuku.setText("Cấp quyền");
            setBtnEnabled(btnGrantShizuku, true);
        } else if (backendReady) {
            if (serviceBound && patchService != null) {
                tvShizukuStatus.setText("🟢 Shizuku sẵn sàng (UID 2000 — đọc/ghi được Android/data)");
            } else {
                tvShizukuStatus.setText("🟢 Shizuku sẵn sàng (Shell UID " + shellUid + " — chế độ tương thích Android 16 / XOS / HyperOS)");
            }
            btnOpenShizuku.setText("Mở Shizuku");
            btnGrantShizuku.setText("Đã sẵn sàng");
            setBtnEnabled(btnGrantShizuku, false);
        } else if (!lastConnectError.isEmpty()) {
            tvShizukuStatus.setText("🔴 Không kết nối được dịch vụ Shizuku (" + lastConnectError + ").\n"
                    + "Infinix XOS / Oppo / Realme: bật 'Tắt theo dõi quyền' (Disable permission monitoring) · Xiaomi: bật 'Gỡ lỗi USB (Cài đặt bảo mật)' & Pin 'Không hạn chế' cho Shizuku rồi bấm 'Thử lại'.");
            btnOpenShizuku.setText("Mở Shizuku");
            btnGrantShizuku.setText("Thử lại");
            setBtnEnabled(btnGrantShizuku, true);
        } else {
            tvShizukuStatus.setText("🟡 Đã cấp quyền Shizuku, đang kết nối (tự chuyển Shell sau 3s nếu ROM chặn)...");
            btnOpenShizuku.setText("Mở Shizuku");
            btnGrantShizuku.setText("Đang kết nối...");
            setBtnEnabled(btnGrantShizuku, false);
        }

        boolean ready = binderAlive && permGranted && backendReady && !busy;
        setBtnEnabled(btnInstallOnline, ready);
        setBtnEnabled(btnInstallOffline, ready);
        setBtnEnabled(btnRestore, ready);
        setBtnEnabled(btnOpenGame, isPackageInstalled(GAME_PKG));
        boolean sysReady = binderAlive && permGranted && backendReady && isPackageInstalled(GAME_PKG) && !busy;
        setBtnEnabled(btnApplyGameMode, sysReady);
        setBtnEnabled(btnResetGameMode, sysReady);
        updateInGamePerfUi();
        if (!binderAlive || !permGranted || !backendReady) {
            lastGameMode = null;
            lastPerfCaps = null;
            lastPerfState = null;
            updateGameModeUi();
        }
    }

    private void ensureServiceBound(boolean forceRetry) {
        try {
            if (!Shizuku.pingBinder()) return;
            if (Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) return;
            if (isBackendReady() || serviceBindingInFlight) return;
            if (!forceRetry && !lastConnectError.isEmpty()) return;

            serviceBindingInFlight = true;
            lastConnectError = "";
            runOnUiThread(this::updateShizukuUi);
            if (preferDirectShell) {
                log("Đang kết nối trực tiếp Shizuku Shell (chế độ tương thích)...");
                tryActivateShellFallbackAsync("prefer_direct_shell");
                return;
            }
            log("Đang kết nối dịch vụ Shizuku (UserService)...");

            mainHandler.removeCallbacks(bindTimeoutRunnable);
            mainHandler.postDelayed(bindTimeoutRunnable, USER_SERVICE_TIMEOUT_MS);

            Shizuku.bindUserService(userServiceArgs, serviceConnection);
        } catch (Throwable t) {
            mainHandler.removeCallbacks(bindTimeoutRunnable);
            tryActivateShellFallbackAsync("bindUserService lỗi: " + t.getMessage());
        }
    }

    private void onUserServiceBindTimeout() {
        try {
            if (!Shizuku.pingBinder() || Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) {
                serviceBindingInFlight = false;
                runOnUiThread(this::updateShizukuUi);
                return;
            }
            if ((serviceBound && patchService != null) || shellBackendReady) {
                serviceBindingInFlight = false;
                return;
            }
            log("⚠️ UserService không phản hồi sau 3s (thường gặp trên XOS / HyperOS / Android 16) → tự động chuyển sang Shizuku Shell trực tiếp...");
            try {
                Shizuku.unbindUserService(userServiceArgs, serviceConnection, true);
            } catch (Throwable ignored) {
            }
            tryActivateShellFallbackAsync("UserService timeout 3s");
        } catch (Throwable t) {
            tryActivateShellFallbackAsync("Timeout handler lỗi: " + t.getMessage());
        }
    }

    private void tryActivateShellFallbackAsync(String reason) {
        workerExecutor.execute(() -> {
            try {
                if ((serviceBound && patchService != null) || shellBackendReady) {
                    serviceBindingInFlight = false;
                    return;
                }
                String uid = ShizukuShellBackend.probeShellUid();
                shellUid = uid;
                shellBackendReady = true;
                serviceBindingInFlight = false;
                lastConnectError = "";
                log("🟢 Đã kết nối Shizuku Shell trực tiếp (UID " + uid + ")!");
                runOnUiThread(this::updateShizukuUi);
                probeGameAsync();
            } catch (Throwable t) {
                serviceBindingInFlight = false;
                shellBackendReady = false;
                String msg = t.getMessage() != null ? t.getMessage().trim() : "";
                lastConnectError = msg.isEmpty() ? reason : msg;
                log("❌ Không kết nối được UserService & Shell: " + lastConnectError);
                log("💡 Khắc phục trên Infinix XOS / Oppo / Xiaomi: vào Tùy chọn nhà phát triển bật 'Tắt theo dõi quyền' (Disable permission monitoring) hoặc 'Gỡ lỗi USB (Cài đặt bảo mật)'; đặt Pin 'Không hạn chế' cho Shizuku + dùng Shizuku bản GitHub mới nhất.");
                runOnUiThread(this::updateShizukuUi);
            }
        });
    }

    private void requestShizukuPermission() {
        try {
            if (!Shizuku.pingBinder()) {
                toast("Shizuku chưa chạy! Hãy mở Shizuku trước.");
                return;
            }
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
                lastConnectError = "";
                serviceBindingInFlight = false;
                if (!serviceBound && patchService == null && shellBackendReady) {
                    probeGameAsync();
                } else {
                    ensureServiceBound(true);
                }
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
                "5️⃣ Mục (3) Mod Đồ Họa & Hiệu Năng (Tùy chọn):\n" +
                "   • Máy yếu: Dùng 'Mod Mở Khóa Đồ Họa In-Game' để hạ Tỷ lệ kết xuất xuống 50% + tắt SSAA/GI/AO; hoặc dùng Preset 'Máy yếu (0.60×)' (nếu máy dùng WM hạ phân giải màn hình, nhớ bấm 'Về mặc định' sau khi chơi xong).\n" +
                "   • Máy Gaming / Android 15+: Preset 'Gaming Max' mở khóa giới hạn nhiệt (Thermal Unlock) & giới hạn 60Hz mặc định, hỗ trợ lên tới 120 FPS.\n\n" +
                "ℹ️ Lưu ý (Infinix XOS 16 / Xiaomi HyperOS / Realme / Oppo / Android 16):\n" +
                "   • Nếu bị kẹt kết nối Shizuku: vào Tùy chọn nhà phát triển bật 'Tắt theo dõi quyền' (Disable permission monitoring) hoặc 'Gỡ lỗi USB (Cài đặt bảo mật)', đặt Pin cho Shizuku thành 'Không hạn chế' và cho phép chạy nền.\n" +
                "   • App sẽ tự động chuyển sang chế độ Shizuku Shell trực tiếp sau 3 giây nếu ROM chặn UserService.\n" +
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

    private String backendProbeGameState(String gameFilesDir, String manifestJson) throws Exception {
        final IViPatchService svc = patchService;
        if (svc != null) {
            try {
                return svc.probeGameState(gameFilesDir, manifestJson);
            } catch (Throwable t) {
                if (!shellBackendReady) throw new RuntimeException(t);
            }
        }
        return ShizukuShellBackend.probeGameState(gameFilesDir, manifestJson);
    }

    private String backendForceStopGame(String pkg) {
        final IViPatchService svc = patchService;
        if (svc != null) {
            try {
                return svc.forceStopGame(pkg);
            } catch (Throwable ignored) {
            }
        }
        return ShizukuShellBackend.forceStopGame(pkg);
    }

    private String backendInstallFromStaging(String stagingDir, String gameFilesDir, String manifestJson) throws Exception {
        final IViPatchService svc = patchService;
        if (svc != null) {
            try {
                return svc.installFromStaging(stagingDir, gameFilesDir, manifestJson);
            } catch (Throwable t) {
                if (!shellBackendReady) throw new RuntimeException(t);
            }
        }
        return ShizukuShellBackend.installFromStaging(stagingDir, gameFilesDir, manifestJson);
    }

    private String backendRestoreFromBackup(String gameFilesDir, String manifestJson) throws Exception {
        final IViPatchService svc = patchService;
        if (svc != null) {
            try {
                return svc.restoreFromBackup(gameFilesDir, manifestJson);
            } catch (Throwable t) {
                if (!shellBackendReady) throw new RuntimeException(t);
            }
        }
        return ShizukuShellBackend.restoreFromBackup(gameFilesDir, manifestJson);
    }

    private void probeGameAsync() {
        if (!isBackendReady()) {
            runOnUiThread(() -> {
                if (!isPackageInstalled(GAME_PKG)) {
                    tvGameStatus.setText("❌ Chưa cài game Azur Promilia JP (" + GAME_PKG + ").");
                } else {
                    tvGameStatus.setText("⏳ Đã cài Azur Promilia JP. Bật & cấp quyền Shizuku ở mục (1) để kiểm tra & cài Việt hóa.");
                }
            });
            return;
        }
        final int seq = ++probeSeq;
        workerExecutor.execute(() -> {
            try {
                JSONObject caps = ShizukuShellBackend.detectPerfCapabilities(GAME_PKG);
                lastPerfCaps = caps;
                JSONObject gm = caps.optBoolean("has_game_mode", false)
                        ? ShizukuShellBackend.probeGameMode(GAME_PKG)
                        : new JSONObject("{\"supported\":false,\"reason\":\"ROM không bật GameManagerService\"}");
                lastGameMode = gm;
                lastPerfState = ShizukuShellBackend.probeUniversalPerfState(GAME_PKG, caps);
                String res = backendProbeGameState(getGameFilesDir(), currentPlanJson);
                if (seq != probeSeq) return;
                android.util.Log.i("AzurVI", "Probe(" + (patchService != null && !shellBackendReady ? "UserService" : "Shell") + "): " + res);
                JSONObject obj = new JSONObject(res);
                lastProbe = obj;
                runOnUiThread(() -> {
                    renderProbeState(obj);
                    updateGameModeUi();
                });
            } catch (Throwable t) {
                log("Lỗi kiểm tra thư mục game: " + t.getMessage());
            }
        });
    }

    private void renderProbeState(JSONObject obj) {
        updateInGamePerfUi();
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
        updateGameStatusText(obj);
        evaluateUpdateNotifications();
        maybeShowUpdatePopup();
    }

    private void updateGameStatusText(JSONObject obj) {
        if (obj == null || !isPackageInstalled(GAME_PKG) || obj.has("error") || !obj.optBoolean("res_exists", false)) {
            return;
        }
        String det = obj.optString("detected_version", "");
        int total = obj.optInt("total", 0);
        int vi = obj.optInt("vi_count", 0);
        int perf = obj.optInt("perf_count", 0);
        int orig = obj.optInt("orig_count", 0);
        int bak = obj.optInt("backup_count", 0);
        String verInstalled = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(KEY_INSTALLED_VER, "");

        StringBuilder sb = new StringBuilder();
        sb.append("• Game JP: Đã cài · Resource ver: ").append(det.isEmpty() ? "?" : det).append("\n");
        if (total > 0) {
            if (vi == total) {
                sb.append("✅ Đã Việt hóa ").append(vi).append("/").append(total).append(" file");
                if (!verInstalled.isEmpty()) sb.append(" (").append(verInstalled).append(")");
                if (perf > 0) sb.append(" · +Mod Đồ họa");
            } else if (orig == total) {
                sb.append("📦 Đang ở bản gốc JP (").append(orig).append("/").append(total).append(" file) — sẵn sàng cài!");
            } else {
                sb.append("ℹ️ Việt hóa: ").append(vi).append("/").append(total)
                  .append(" · Gốc: ").append(orig).append("/").append(total);
            }
            if (bak > 0) {
                sb.append(" · Backup gốc: ").append(bak).append("/").append(total);
            } else {
                sb.append(" · Chưa có backup gốc");
            }
        }
        tvGameStatus.setText(sb.toString());
        updateInGamePerfUi();
    }

    // -------------------------------------------------------------------------
    // Auto-Update Check (GitHub latest-vi.json + Releases API fallback)
    // -------------------------------------------------------------------------
    private long getAppVersionCode() {
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            return PackageInfoCompat.getLongVersionCode(pi);
        } catch (Throwable t) {
            return BuildConfig.VERSION_CODE;
        }
    }

    private String getAppVersionName() {
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            if (pi.versionName != null && !pi.versionName.trim().isEmpty()) {
                return pi.versionName.trim();
            }
        } catch (Throwable ignored) {
        }
        return BuildConfig.VERSION_NAME;
    }

    private boolean isRemoteApkNewer(JSONObject apk) {
        if (apk == null) return false;
        long remoteCode = apk.optLong("version_code", 0);
        long localCode = getAppVersionCode();
        String remoteVer = apk.optString("version", "");
        if (remoteCode > 0 && localCode > 0) {
            if (remoteCode != localCode) return remoteCode > localCode;
            return false;
        }
        return !remoteVer.isEmpty() && compareSemver(remoteVer, getAppVersionName()) > 0;
    }

    private boolean isRemotePatchNewer(JSONObject remote) {
        if (remote == null) return false;
        JSONObject an = remote.optJSONObject("android");
        if (an == null) return false;
        String remotePatchVer = remote.optString("version", "");
        String remotePayloadHash = an.optString("payload_hash", "");
        String remoteZipSha = an.optString("sha256", "");

        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String localPatchVer = prefs.getString(KEY_INSTALLED_VER, "");
        String installedZipSha = prefs.getString(KEY_INSTALLED_ZIP_SHA, "");
        String installedPayloadHash = prefs.getString(KEY_INSTALLED_PAYLOAD_HASH, "");

        boolean gameAlreadyVi = lastProbe != null
                && lastProbe.optInt("total", 0) > 0
                && lastProbe.optInt("vi_count", 0) == lastProbe.optInt("total", 0);
        String probePayloadHash = lastProbe != null ? lastProbe.optString("payload_hash", "") : "";

        if (gameAlreadyVi) {
            if (!remotePayloadHash.isEmpty() && remotePayloadHash.equalsIgnoreCase(probePayloadHash)) {
                if (!remotePatchVer.equals(localPatchVer) || !remotePayloadHash.equalsIgnoreCase(installedPayloadHash)) {
                    prefs.edit()
                            .putString(KEY_INSTALLED_VER, remotePatchVer)
                            .putString(KEY_INSTALLED_PAYLOAD_HASH, remotePayloadHash)
                            .apply();
                }
                return false;
            }
            if (!remoteZipSha.isEmpty() && remoteZipSha.equalsIgnoreCase(installedZipSha)) {
                return false;
            }
            if (!localPatchVer.isEmpty()) {
                return compareSemver(remotePatchVer, localPatchVer) > 0;
            }
            return false;
        }
        if (lastProbe == null) {
            return false; // Wait until game files are probed before claiming a patch update
        }
        return !localPatchVer.isEmpty() && compareSemver(remotePatchVer, localPatchVer) > 0;
    }

    private void cleanupStaleApkUpdate() {
        try {
            File apkFile = new File(new File(getExternalFilesDir(null), "updates"), "AzurPromilia-VI-Mobile-update.apk");
            if (apkFile.isFile()) apkFile.delete();
        } catch (Throwable ignored) {
        }
    }

    private void checkUpdatesAsync(boolean showPopupIfNew) {
        netExecutor.execute(() -> {
            try {
                log("Đang kiểm tra bản mới trên GitHub...");
                JSONObject data = fetchRemoteInfo();
                if (data == null) {
                    runOnUiThread(() -> tvRemoteStatus.setText("⚠️ Không kiểm tra được GitHub (vẫn cài được từ file .ZIP offline)."));
                    return;
                }
                remoteInfo = data;
                JSONObject anObj = data.optJSONObject("android");
                JSONObject apkObj = anObj != null ? anObj.optJSONObject("apk") : null;
                if (!isRemoteApkNewer(apkObj)) {
                    cleanupStaleApkUpdate();
                }
                runOnUiThread(() -> {
                    evaluateUpdateNotifications();
                    if (showPopupIfNew) maybeShowUpdatePopup();
                });
            } catch (Throwable t) {
                log("Lỗi check GitHub: " + t.getMessage());
            }
        });
    }

    private JSONObject fetchRemoteInfo() {
        // 1. Try GitHub Release latest download (no 5-minute raw CDN cache lag)
        try {
            String relJson = httpGetString(RELEASE_LATEST_JSON_URL);
            if (relJson != null && relJson.trim().startsWith("{")) {
                JSONObject j = new JSONObject(relJson);
                if (j.has("android")) return j;
            }
        } catch (Throwable ignored) {
        }
        // 2. Fallback to raw latest-vi.json with cache buster
        try {
            String raw = httpGetString(LATEST_JSON_URL + "?t=" + System.currentTimeMillis());
            if (raw != null && raw.trim().startsWith("{")) {
                JSONObject j = new JSONObject(raw);
                if (j.has("android")) return j;
            }
        } catch (Throwable ignored) {
        }
        // 3. Fallback to GitHub Releases API
        try {
            String api = httpGetString(RELEASES_API_URL);
            if (api != null) {
                JSONObject rel = new JSONObject(api);
                String tag = rel.optString("tag_name", "");
                JSONArray assets = rel.optJSONArray("assets");
                String zipUrl = "", zipName = "", latestJsonUrl = "";
                long zipSize = 0;
                if (assets != null) {
                    for (int i = 0; i < assets.length(); i++) {
                        JSONObject a = assets.getJSONObject(i);
                        String n = a.optString("name", "");
                        if (n.equals("latest-vi.json")) {
                            latestJsonUrl = a.optString("browser_download_url", "");
                        } else if (n.startsWith("AzurPromilia-Localization-Android-vi-") && n.endsWith(".zip")) {
                            zipUrl = a.optString("browser_download_url", "");
                            zipName = n;
                            zipSize = a.optLong("size", 0);
                        }
                    }
                }
                if (!latestJsonUrl.isEmpty()) {
                    try {
                        String assetJson = httpGetString(latestJsonUrl);
                        if (assetJson != null && assetJson.trim().startsWith("{")) {
                            JSONObject j = new JSONObject(assetJson);
                            if (j.has("android")) return j;
                        }
                    } catch (Throwable ignored) {
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
        String rVer = an != null ? an.optString("resource_version", "") : "";
        long sz = an != null ? an.optLong("size", 0) : 0;
        JSONObject apk = an != null ? an.optJSONObject("apk") : null;
        String remoteApkVer = apk != null ? apk.optString("version", "") : "";
        String localAppVer = getAppVersionName();

        boolean hasNewApk = isRemoteApkNewer(apk);
        boolean hasNewPatch = isRemotePatchNewer(remoteInfo);
        if (lastProbe != null) {
            updateGameStatusText(lastProbe);
        }
        updateInGamePerfUi();
        boolean gameAlreadyVi = lastProbe != null
                && lastProbe.optInt("total", 0) > 0
                && lastProbe.optInt("vi_count", 0) == lastProbe.optInt("total", 0);

        tvRemoteStatus.setText(String.format(Locale.ROOT,
                "🌐 GitHub: %s (Mobile res %s · %.1f MB%s%s)",
                remotePatchVer, rVer, sz / (1024.0 * 1024.0),
                remoteApkVer.isEmpty() ? "" : " · App " + remoteApkVer,
                (!hasNewApk && !hasNewPatch && gameAlreadyVi) ? " · Đã đồng bộ" : ""));

        String localPatchVer = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(KEY_INSTALLED_VER, "");

        if (hasNewApk) {
            tvUpdateBanner.setVisibility(View.VISIBLE);
            tvUpdateBanner.setBackground(makeCardBg("#1E3A8A", "#38BDF8", 12));
            tvUpdateBanner.setText("🔔 CÓ BẢN APP MỚI " + remoteApkVer + " (hiện tại " + localAppVer + ") — Chạm vào đây để cập nhật App!");
            tvUpdateBanner.setOnClickListener(v -> startSelfApkUpdate(apk));
        } else if (hasNewPatch) {
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

        if (isRemoteApkNewer(apk)) {
            autoUpdateDialogShown = true;
            new AlertDialog.Builder(this)
                    .setTitle("Có bản App Việt Hóa mới (" + remoteApkVer + ")")
                    .setMessage("Phiên bản app hiện tại: " + getAppVersionName() + "\nPhiên bản mới trên GitHub: " + remoteApkVer + "\n\n" + notes)
                    .setPositiveButton("Tải & Cài đặt App", (d, w) -> startSelfApkUpdate(apk))
                    .setNegativeButton("Để sau", null)
                    .show();
        } else if (lastProbe != null && isRemotePatchNewer(remoteInfo)) {
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
        netExecutor.execute(() -> {
            try {
                File dir = new File(getExternalFilesDir(null), "updates");
                dir.mkdirs();
                File apkFile = new File(dir, "AzurPromilia-VI-Mobile-update.apk");
                if (!apkFile.isFile() || expectedSha.isEmpty() || !sha256File(apkFile).equals(expectedSha)) {
                    log("Đang tải APK mới: " + url);
                    downloadFile(url, apkFile, apkObj.optLong("size", 0), "Đang tải APK mới");
                    if (!expectedSha.isEmpty()) {
                        String got = sha256File(apkFile);
                        if (!got.equals(expectedSha)) {
                            apkFile.delete();
                            throw new RuntimeException("SHA-256 APK tải về không khớp!");
                        }
                    }
                } else {
                    log("Dùng lại APK mới đã tải (SHA-256 khớp).");
                }

                PackageInfo archiveInfo = getPackageManager().getPackageArchiveInfo(apkFile.getAbsolutePath(), 0);
                if (archiveInfo == null || !getPackageName().equals(archiveInfo.packageName)) {
                    apkFile.delete();
                    throw new RuntimeException("File APK tải về không hợp lệ hoặc sai package.");
                }
                long archiveCode = PackageInfoCompat.getLongVersionCode(archiveInfo);
                if (archiveCode <= getAppVersionCode()) {
                    apkFile.delete();
                    log("ℹ️ Bản đang cài (" + getAppVersionName() + ") đã là mới nhất so với APK tải về.");
                    runOnUiThread(() -> {
                        setBusy(false);
                        setProgressUi(false, 0, "");
                        evaluateUpdateNotifications();
                        toast("Bạn đang ở bản APK mới nhất rồi!");
                    });
                    return;
                }

                log("Tải APK hoàn tất (code " + archiveCode + "), mở trình cài đặt...");
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 0, "");
                    launchApkInstaller(apkFile);
                });
            } catch (Throwable t) {
                log("❌ Lỗi tải APK mới: " + t.getMessage());
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 0, "");
                    toast("Lỗi tải APK: " + t.getMessage());
                });
            }
        });
    }

    private void launchApkInstaller(File apkFile) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !getPackageManager().canRequestPackageInstalls()) {
                pendingInstallApk = apkFile;
                toast("Hãy bật 'Cho phép từ nguồn này' rồi quay lại để tự mở cài đặt!");
                Intent permIntent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + getPackageName()));
                startActivity(permIntent);
                return;
            }
            Uri contentUri = FileProvider.getUriForFile(this, BuildConfig.APPLICATION_ID + ".fileprovider", apkFile);
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(contentUri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Throwable t) {
            log("Không mở được bộ cài trực tiếp (" + t.getMessage() + "), mở trình duyệt...");
            openUrl(RELEASES_PAGE_URL);
        }
    }

    // -------------------------------------------------------------------------
    // Graphics / Performance Mod (Cross-Device Engine + In-Game Unlock)
    // -------------------------------------------------------------------------
    private void updateGameModeUi() {
        if (tvGameModeStatus == null) return;
        JSONObject caps = lastPerfCaps;
        if (caps == null) {
            tvGameModeStatus.setText("⏳ Bật Shizuku để nhận diện phần cứng & tối ưu FPS (hỗ trợ cả máy yếu lẫn máy Gaming).");
            return;
        }

        StringBuilder badge = new StringBuilder();
        boolean hasGM = caps.optBoolean("has_game_mode", false);
        boolean hasDC = caps.optBoolean("has_device_config", false);
        boolean hasWM = caps.optBoolean("has_wm", false);
        boolean hasTH = caps.optBoolean("has_thermal", false);
        boolean hasFU = caps.optBoolean("has_fps_unlock", false);

        if (hasGM) badge.append("GameMode");
        if (hasDC) { if (badge.length() > 0) badge.append(" + "); badge.append("DevCfg"); }
        if (hasWM) { if (badge.length() > 0) badge.append(" + "); badge.append("WM"); }
        if (hasTH) { if (badge.length() > 0) badge.append(" + "); badge.append("Thermal"); }
        if (hasFU) { if (badge.length() > 0) badge.append(" + "); badge.append("Unlock120Hz"); }
        if (badge.length() > 0) badge.append(" + ");
        badge.append("RAM");

        if (cbThermalUnlock != null) cbThermalUnlock.setEnabled(hasTH && !busy);
        if (cbWmDownscale != null) {
            boolean wmNeeded = !hasGM && !hasDC && hasWM;
            cbWmDownscale.setVisibility(wmNeeded ? View.VISIBLE : View.GONE);
            cbWmDownscale.setEnabled(wmNeeded && !busy);
        }

        JSONObject st = lastPerfState;
        String dcConfig = st != null ? st.optString("dc_config", "") : "";
        boolean wmOvr   = st != null && st.optBoolean("wm_override", false);
        String wmSize   = st != null ? st.optString("wm_size", "") : "";
        boolean thOvr   = st != null && st.optBoolean("thermal_override", false);
        boolean fpsUnl  = st != null && st.optBoolean("fps_unlocked", false);

        String gmMode = "";
        if (hasGM && lastGameMode != null && lastGameMode.optBoolean("supported", false)) {
            String mode = lastGameMode.optString("mode", "standard");
            String sc   = lastGameMode.optString("scaling", "-1");
            String fps  = lastGameMode.optString("fps", "-1");
            if (!"standard".equalsIgnoreCase(mode) || (!sc.startsWith("-") && !sc.isEmpty())) {
                gmMode = "GameMode(" + mode.toUpperCase(Locale.ROOT)
                        + (sc.startsWith("-") ? "" : " " + sc + "×")
                        + (fps.startsWith("-") || "0".equals(fps) ? "" : " " + fps + "FPS") + ")";
            }
        }

        StringBuilder active = new StringBuilder();
        if (!gmMode.isEmpty()) active.append(gmMode);
        if (!dcConfig.isEmpty()) { if (active.length() > 0) active.append(" · "); active.append("DevCfg=").append(dcConfig); }
        if (wmOvr && !wmSize.isEmpty()) { if (active.length() > 0) active.append(" · "); active.append("⚠️ WM=").append(wmSize); }
        if (thOvr) { if (active.length() > 0) active.append(" · "); active.append("🌡️ ThermalUnlock"); }
        if (fpsUnl) { if (active.length() > 0) active.append(" · "); active.append("⚡ >60Hz ON"); }

        String modeNote = hasGM
                ? "Hỗ trợ GameMode chuẩn theo app"
                : "ROM không bật GameMode → tự chuyển sang chế độ Máy yếu (WM) / Gaming (Thermal + Hz)";

        if (active.length() == 0) {
            tvGameModeStatus.setText("🛡️ [" + badge + "]\n• " + modeNote + "\n• Trạng thái: Nguyên bản.");
        } else {
            tvGameModeStatus.setText("🛡️ [" + badge + "]\n⚡ Đang bật: " + active);
        }
    }

    private void updateInGamePerfUi() {
        if (tvInGamePerfStatus == null || btnToggleInGamePerf == null) return;
        boolean gameInstalled = isPackageInstalled(GAME_PKG);
        boolean gameVi = lastProbe != null && lastProbe.optInt("total", 0) > 0
                && lastProbe.optInt("vi_count", 0) == lastProbe.optInt("total", 0);
        boolean perfOn = lastProbe != null && lastProbe.optInt("perf_count", 0) > 0;
        boolean ready = isBackendReady() && gameInstalled && !busy && gameVi;

        if (!gameInstalled || !isBackendReady()) {
            tvInGamePerfStatus.setText("🎨 Mở Khóa Đồ Họa In-Game (Mọi máy): Tải riêng 1 file (~24 MB) mở khóa Tỷ lệ kết xuất 50%-170%, SSAA OFF, GI/AO/Phản chiếu, DoF, LightShaft.");
        } else if (!gameVi) {
            tvInGamePerfStatus.setText("🔒 Cần cài Việt hóa 7/7 ở mục (2) trước khi bật/tắt Mod Mở Khóa Đồ Họa In-Game.");
        } else if (perfOn) {
            tvInGamePerfStatus.setText("✅ Mod Mở Khóa Đồ Họa In-Game: ĐANG BẬT (Đã mở Tỷ lệ kết xuất 50%-170%, SSAA OFF, GI/AO/Phản chiếu, DoF, LightShaft/LensFlare/UVDistort, ASM|CSM).");
        } else {
            tvInGamePerfStatus.setText("🎨 Mod Mở Khóa Đồ Họa In-Game: CHƯA BẬT (Bấm nút dưới để mở toàn bộ thanh chỉnh đồ họa PC bị ẩn trên Mobile).");
        }

        if (perfOn) {
            btnToggleInGamePerf.setText("Tắt Mod In-Game (Về Việt hóa chuẩn)");
            btnToggleInGamePerf.setBackground(makeCardBg("#7C2D12", "#334155", 10));
        } else {
            btnToggleInGamePerf.setText("Bật Mở Khóa Đồ Họa In-Game");
            btnToggleInGamePerf.setBackground(makeCardBg("#0F766E", "#334155", 10));
        }
        setBtnEnabled(btnToggleInGamePerf, ready);
    }

    private void applySelectedGameMode() {
        if (busy || !isPackageInstalled(GAME_PKG)) return;
        if (!Shizuku.pingBinder() || Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) {
            toast("Shizuku chưa sẵn sàng!");
            return;
        }
        int pIdx = spPerfPreset.getSelectedItemPosition();
        int fpsIdx = spPerfFps.getSelectedItemPosition();
        int fps = PERF_FPS_VALUES[Math.max(0, Math.min(PERF_FPS_VALUES.length - 1, fpsIdx))];

        double customScale = 1.0;
        if (pIdx == 4) {
            int pct = 45 + sbCustomScale.getProgress() * 5; // 45%–150%
            customScale = pct / 100.0;
        }

        boolean thermal = cbThermalUnlock != null && cbThermalUnlock.isChecked();
        boolean allowWm = cbWmDownscale == null || cbWmDownscale.isChecked();

        final int finalPIdx = pIdx;
        final double finalScale = customScale;
        final int finalFps = fps;
        final boolean finalThermal = thermal;
        final boolean finalWm = allowWm;

        if (lastPerfCaps == null) {
            setBusy(true);
            workerExecutor.execute(() -> {
                JSONObject caps = ShizukuShellBackend.detectPerfCapabilities(GAME_PKG);
                lastPerfCaps = caps;
                lastPerfState = ShizukuShellBackend.probeUniversalPerfState(GAME_PKG, caps);
                runOnUiThread(() -> {
                    setBusy(false);
                    confirmOrApplyUniversalPreset(finalPIdx, finalScale, finalFps, finalWm, finalThermal);
                });
            });
        } else {
            confirmOrApplyUniversalPreset(finalPIdx, finalScale, finalFps, finalWm, finalThermal);
        }
    }

    private void confirmOrApplyUniversalPreset(int pIdx, double customScale, int fps,
                                               boolean allowWm, boolean thermal) {
        JSONObject caps = lastPerfCaps;
        if (caps == null) {
            toast("Không phát hiện được khả năng thiết bị.");
            return;
        }
        double scale = ShizukuShellBackend.presetScaleForIndex(pIdx, customScale);
        boolean willUseWm = !caps.optBoolean("has_game_mode", false)
                && !caps.optBoolean("has_device_config", false)
                && caps.optBoolean("has_wm", false)
                && scale < 0.99 && allowWm;
        boolean alreadyWm = lastPerfState != null && lastPerfState.optBoolean("wm_override", false);

        if (willUseWm && !alreadyWm) {
            int nw = caps.optInt("native_width", 0);
            int nh = caps.optInt("native_height", 0);
            int nd = caps.optInt("native_density", 0);
            int[] dim = ShizukuShellBackend.computeScaledWmDimensions(nw, nh, nd, scale);
            new AlertDialog.Builder(this)
                    .setTitle("Hạ độ phân giải màn hình cho máy yếu?")
                    .setMessage("Thiết bị không bật GameMode theo từng app.\n\n"
                            + "App sẽ tạm thời hạ độ phân giải màn hình từ " + nw + "×" + nh
                            + " xuống " + dim[0] + "×" + dim[1] + " (~" + Math.round(scale * 100) + "%) "
                            + "và dọn RAM nền để giảm tối đa tải GPU.\n\n"
                            + "⚠️ Toàn giao diện máy sẽ nhỏ/to hơn một chút trong lúc chơi. "
                            + "Sau khi chơi xong hãy bấm 'Về mặc định' để trả về độ phân giải gốc!")
                    .setPositiveButton("Hạ phân giải + Giảm lag",
                            (d, w) -> doApplyUniversalPreset(pIdx, customScale, fps, true, thermal, true))
                    .setNeutralButton("Chỉ dọn RAM / Không đổi màn",
                            (d, w) -> doApplyUniversalPreset(pIdx, customScale, fps, false, thermal, true))
                    .setNegativeButton("Hủy", null)
                    .show();
            return;
        }
        doApplyUniversalPreset(pIdx, customScale, fps, allowWm, thermal, true);
    }

    private void doApplyUniversalPreset(int pIdx, double customScale, int fps,
                                        boolean allowWm, boolean thermal, boolean clearRam) {
        JSONObject caps = lastPerfCaps;
        if (caps == null) {
            toast("Không phát hiện được khả năng thiết bị.");
            return;
        }
        setBusy(true);
        workerExecutor.execute(() -> {
            try {
                String res = ShizukuShellBackend.applyUniversalPreset(
                        GAME_PKG, caps, pIdx, customScale, fps, allowWm, thermal, clearRam);
                lastPerfCaps = ShizukuShellBackend.detectPerfCapabilities(GAME_PKG);
                if (lastPerfCaps.optBoolean("has_game_mode", false)) {
                    lastGameMode = ShizukuShellBackend.probeGameMode(GAME_PKG);
                }
                lastPerfState = ShizukuShellBackend.probeUniversalPerfState(GAME_PKG, lastPerfCaps);
                runOnUiThread(() -> {
                    setBusy(false);
                    updateGameModeUi();
                    if (res.startsWith("OK:")) {
                        String detail = res.substring(3).trim();
                        log("✅ Đã áp dụng [" + detail + "]. Hãy mở/khởi động lại game!");
                        toast("Áp dụng thành công! Nếu game đang chạy hãy đóng mở lại game.");
                    } else {
                        String msg = res.replaceFirst("^ERR:", "");
                        log("⚠️ " + msg);
                        toast(msg);
                    }
                });
            } catch (Throwable t) {
                log("❌ Lỗi áp preset: " + t.getMessage());
                runOnUiThread(() -> { setBusy(false); toast("Lỗi: " + t.getMessage()); });
            }
        });
    }

    private void resetSelectedGameMode() {
        if (busy || !isPackageInstalled(GAME_PKG)) return;
        if (!Shizuku.pingBinder() || Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) {
            toast("Shizuku chưa sẵn sàng!");
            return;
        }
        setBusy(true);
        workerExecutor.execute(() -> {
            JSONObject caps = lastPerfCaps != null ? lastPerfCaps
                    : ShizukuShellBackend.detectPerfCapabilities(GAME_PKG);
            lastPerfCaps = caps;
            String res = ShizukuShellBackend.resetUniversalPreset(GAME_PKG, caps);
            if (caps.optBoolean("has_game_mode", false)) {
                lastGameMode = ShizukuShellBackend.probeGameMode(GAME_PKG);
            }
            lastPerfState = ShizukuShellBackend.probeUniversalPerfState(GAME_PKG, caps);
            runOnUiThread(() -> {
                spPerfPreset.setSelection(2, false);
                spPerfFps.setSelection(0, false);
                if (cbThermalUnlock != null) cbThermalUnlock.setChecked(false);
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                        .putInt(KEY_PERF_PRESET, 2)
                        .putInt(KEY_PERF_FPS, 0)
                        .putBoolean(KEY_PERF_THERMAL, false)
                        .apply();
                setBusy(false);
                updateGameModeUi();
                if (res.startsWith("OK:")) {
                    log("🔄 Đã reset về mặc định hệ thống (" + res.substring(3).trim() + ").");
                    toast("Đã về mặc định — tắt ép GPU / WM / Thermal / FPS.");
                } else {
                    log("⚠️ " + res);
                    toast(res);
                }
            });
        });
    }

    private void toggleInGamePerfMod() {
        if (busy || !isBackendReady()) return;
        if (currentPlanJson == null || currentPlanJson.isEmpty()) {
            toast("Chưa có manifest android-deployment-vi.json.");
            return;
        }
        final boolean turnOn = !(lastProbe != null && lastProbe.optInt("perf_count", 0) > 0);
        setBusy(true);
        workerExecutor.execute(() -> {
            File staging = new File(getExternalFilesDir(null), "staging_perf");
            try {
                JSONObject plan = new JSONObject(currentPlanJson);
                String resVer = plan.getString("resource_version");
                JSONArray files = plan.getJSONArray("files");
                JSONObject perfRem = (remoteInfo != null && remoteInfo.optJSONObject("android") != null)
                        ? remoteInfo.optJSONObject("android").optJSONObject("perf")
                        : null;
                JSONObject androidRem = remoteInfo != null ? remoteInfo.optJSONObject("android") : null;

                String targetRel = perfRem != null
                        ? perfRem.optString("relative_path", "raw_streaming_package/BundleFiles/lgljnx3smdqqqfkgr8obq.r")
                        : "raw_streaming_package/BundleFiles/lgljnx3smdqqqfkgr8obq.r";

                JSONObject baseItem = null;
                for (int i = 0; i < files.length(); i++) {
                    JSONObject it = files.getJSONObject(i);
                    if (targetRel.equals(it.getString("relative_path").replace('\\', '/'))) {
                        baseItem = it;
                        break;
                    }
                }
                if (baseItem == null) {
                    throw new RuntimeException("Không tìm thấy entry " + targetRel + " trong manifest.");
                }

                String srcSha = baseItem.getString("source_sha256").toLowerCase(Locale.ROOT);
                String viSha = baseItem.getString("target_sha256").toLowerCase(Locale.ROOT);
                String perfSha = !baseItem.optString("perf_target_sha256", "").isEmpty()
                        ? baseItem.optString("perf_target_sha256").toLowerCase(Locale.ROOT)
                        : (perfRem != null ? perfRem.optString("perf_target_sha256", "").toLowerCase(Locale.ROOT) : "");
                if (perfSha.isEmpty()) {
                    throw new RuntimeException("Thiếu perf_target_sha256 — hãy bấm 'Check cập nhật' trước.");
                }
                long fileSize = baseItem.getLong("size");

                String dlUrl;
                String zipSha;
                long dlSize;
                File zipFile;
                String desiredSha;
                String altSha;

                if (turnOn) {
                    if (perfRem == null || perfRem.optString("url", "").isEmpty()) {
                        throw new RuntimeException("Chưa có thông tin gói Mod Đồ Họa từ GitHub. Bấm 'Check cập nhật' rồi thử lại!");
                    }
                    dlUrl = perfRem.getString("url");
                    zipSha = perfRem.optString("sha256", "").toLowerCase(Locale.ROOT);
                    dlSize = perfRem.optLong("zip_size", perfRem.optLong("size", 0));
                    zipFile = new File(getExternalFilesDir(null), "perf_patch_download.zip");
                    desiredSha = perfSha;
                    altSha = viSha;
                } else {
                    zipFile = new File(getExternalFilesDir(null), "android_patch_download.zip");
                    desiredSha = viSha;
                    altSha = perfSha;
                    if (zipFile.isFile() && extractEntryMatchingSha(zipFile, targetRel, fileSize, desiredSha, null)) {
                        dlUrl = "";
                        zipSha = "";
                        dlSize = 0;
                    } else if (androidRem != null && !androidRem.optString("url", "").isEmpty()) {
                        dlUrl = androidRem.getString("url");
                        zipSha = androidRem.optString("sha256", "").toLowerCase(Locale.ROOT);
                        dlSize = androidRem.optLong("size", 0);
                    } else {
                        throw new RuntimeException("Chưa có file gói Việt hóa chuẩn và không kết nối được GitHub. Bấm 'Check cập nhật'!");
                    }
                }

                if (!dlUrl.isEmpty()) {
                    boolean cachedOk = zipFile.isFile() && !zipSha.isEmpty() && sha256File(zipFile).equals(zipSha);
                    if (cachedOk) {
                        log("Dùng lại file ZIP đã lưu cục bộ (SHA-256 khớp).");
                    } else {
                        log(turnOn ? "Đang tải gói Mở Khóa Đồ Họa In-Game..." : "Đang tải lại bảng Đồ Họa chuẩn...");
                        downloadFile(dlUrl, zipFile, dlSize, turnOn ? "Tải Mod In-Game" : "Tải gói chuẩn");
                        if (!zipSha.isEmpty()) {
                            String got = sha256File(zipFile);
                            if (!got.equals(zipSha)) {
                                zipFile.delete();
                                throw new RuntimeException("SHA-256 file ZIP không khớp! (" + got + ")");
                            }
                        }
                    }
                }

                deleteRecursive(staging);
                staging.mkdirs();
                File outFile = new File(staging, targetRel);
                setProgressUi(true, 65, "Đang giải nén file cấu hình đồ họa...");
                if (!extractEntryMatchingSha(zipFile, targetRel, fileSize, desiredSha, outFile)) {
                    throw new RuntimeException("Không tìm thấy hoặc sai SHA-256 file " + targetRel + " trong gói ZIP.");
                }

                JSONObject singleItem = new JSONObject();
                singleItem.put("relative_path", targetRel);
                singleItem.put("size", fileSize);
                singleItem.put("source_sha256", srcSha);
                singleItem.put("target_sha256", desiredSha);
                singleItem.put("perf_target_sha256", altSha);
                JSONObject singlePlan = new JSONObject();
                singlePlan.put("resource_version", resVer);
                singlePlan.put("files", new JSONArray().put(singleItem));

                log("Đang đóng game & cập nhật bảng đồ họa In-Game...");
                backendForceStopGame(GAME_PKG);
                setProgressUi(true, 90, "Đang ghi file & kiểm tra SHA-256...");
                String result = backendInstallFromStaging(staging.getAbsolutePath(), getGameFilesDir(), singlePlan.toString());
                deleteRecursive(staging);

                if (result == null || !result.startsWith("OK:")) {
                    throw new RuntimeException(result == null ? "Không nhận được phản hồi Shizuku" : result.replaceFirst("^ERR:", ""));
                }
                log(turnOn
                        ? "✅ ĐÃ BẬT Mod Mở Khóa Đồ Họa In-Game! Vào game -> Cài đặt -> Đồ họa để chỉnh chi tiết."
                        : "🔄 Đã tắt Mod In-Game, trả về bảng Đồ Họa Việt hóa chuẩn.");
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 100, "");
                    probeGameAsync();
                    toast(turnOn ? "Đã bật Mod Mở Khóa Đồ Họa In-Game!" : "Đã tắt Mod In-Game!");
                });
            } catch (Throwable t) {
                deleteRecursive(staging);
                log("❌ Lỗi Mod In-Game: " + t.getMessage());
                runOnUiThread(() -> {
                    setBusy(false);
                    setProgressUi(false, 0, "");
                    toast("Lỗi: " + t.getMessage());
                });
            }
        });
    }

    private static boolean extractEntryMatchingSha(File zipFile, String relPath, long expectedSize,
                                                   String expectedSha, File destOrNull) throws Exception {
        String normTarget = relPath.replace('\\', '/');
        byte[] buf = new byte[524288];
        try (ZipInputStream zis = new ZipInputStream(new BufferedInputStream(new FileInputStream(zipFile)))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                if (entry.isDirectory()) continue;
                String name = entry.getName().replace('\\', '/');
                if (!name.endsWith(normTarget)) continue;
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                long totalRead = 0;
                FileOutputStream fos = null;
                if (destOrNull != null) {
                    destOrNull.getParentFile().mkdirs();
                    fos = new FileOutputStream(destOrNull);
                }
                try {
                    int n;
                    while ((n = zis.read(buf)) > 0) {
                        md.update(buf, 0, n);
                        if (fos != null) fos.write(buf, 0, n);
                        totalRead += n;
                    }
                } finally {
                    if (fos != null) fos.close();
                }
                byte[] d = md.digest();
                StringBuilder sb = new StringBuilder(64);
                for (byte b : d) sb.append(String.format(Locale.ROOT, "%02x", b & 0xFF));
                return totalRead == expectedSize && sb.toString().equals(expectedSha);
            }
        }
        return false;
    }

    // -------------------------------------------------------------------------
    // Install / Restore Flows
    // -------------------------------------------------------------------------
    private void startOnlineInstall() {
        if (busy) return;
        if (!isBackendReady()) {
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
        String ver = remoteInfo.optString("version", getAppVersionName());

        setBusy(true);
        workerExecutor.execute(() -> {
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
                applyFromZipStream(new FileInputStream(zipFile), ver, expectedSha);
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
            if (!isBackendReady()) {
                toast("Shizuku chưa sẵn sàng!");
                return;
            }
            setBusy(true);
            workerExecutor.execute(() -> {
                try {
                    log("Đang giải nén file ZIP đã chọn...");
                    InputStream is = getContentResolver().openInputStream(uri);
                    if (is == null) throw new RuntimeException("Không đọc được file đã chọn.");
                    applyFromZipStream(is, "offline", "");
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

    private void applyFromZipStream(InputStream rawIn, String labelVer, String expectedZipSha) throws Exception {
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
            extractedManifest = mergePerfHashesIfMissing(extractedManifest, currentPlanJson);
            currentPlanJson = extractedManifest;
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                    .putString(KEY_CACHED_PLAN, extractedManifest)
                    .putLong(KEY_CACHED_PLAN_APK_VER, BuildConfig.VERSION_CODE)
                    .apply();
        }

        log("Đang đóng game nếu còn chạy ngầm...");
        backendForceStopGame(GAME_PKG);

        setProgressUi(true, 85, "Đang sao lưu bản gốc & chép file Việt hóa (Shizuku)...");
        String result = backendInstallFromStaging(staging.getAbsolutePath(), getGameFilesDir(), extractedManifest);
        deleteRecursive(staging);

        if (result == null || !result.startsWith("OK:")) {
            throw new RuntimeException(result == null ? "Không nhận được phản hồi từ Shizuku" : result.replaceFirst("^ERR:", ""));
        }

        SharedPreferences.Editor ed = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit();
        if (!"offline".equals(labelVer)) {
            ed.putString(KEY_INSTALLED_VER, labelVer);
        }
        if (expectedZipSha != null && !expectedZipSha.isEmpty()) {
            ed.putString(KEY_INSTALLED_ZIP_SHA, expectedZipSha.toLowerCase(Locale.ROOT));
        }
        String payloadHash = computeManifestPayloadHash(extractedManifest);
        if (!payloadHash.isEmpty()) {
            ed.putString(KEY_INSTALLED_PAYLOAD_HASH, payloadHash);
        }
        ed.apply();

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
        if (busy || !isBackendReady()) return;
        int total = lastProbe != null ? lastProbe.optInt("total", 7) : 7;
        int bak = lastProbe != null ? lastProbe.optInt("backup_count", -1) : -1;
        if (bak >= 0 && bak < total) {
            new AlertDialog.Builder(this)
                    .setTitle("Chưa có bản sao lưu gốc (" + bak + "/" + total + ")")
                    .setMessage("Không tìm thấy đủ 7 file gốc trong bộ nhớ sao lưu của App.\n\nNguyên nhân thường gặp: bạn đã cài Việt hóa thủ công qua PC/ADB trước khi dùng App nên App chưa kịp sao lưu bản gốc.\n\nHãy mở game và dùng tính năng Verify / Repair tài nguyên để tải lại file gốc, hoặc chạy 'Apply-AndroidVI.ps1 -Action Restore' trên PC nếu có bản backup cũ.")
                    .setPositiveButton("Đã hiểu", null)
                    .show();
            return;
        }
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
        workerExecutor.execute(() -> {
            try {
                backendForceStopGame(GAME_PKG);
                setProgressUi(true, 50, "Đang khôi phục bản gốc...");
                String res = backendRestoreFromBackup(getGameFilesDir(), currentPlanJson);
                if (res == null || !res.startsWith("OK:")) {
                    throw new RuntimeException(res == null ? "Shizuku null" : res.replaceFirst("^ERR:", ""));
                }
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                        .remove(KEY_INSTALLED_VER)
                        .remove(KEY_INSTALLED_ZIP_SHA)
                        .remove(KEY_INSTALLED_PAYLOAD_HASH)
                        .apply();
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

    private static String mergePerfHashesIfMissing(String manifestJson, String fallbackJson) {
        if (manifestJson == null || fallbackJson == null || fallbackJson.trim().isEmpty()) {
            return manifestJson;
        }
        if (manifestJson.contains("perf_target_sha256")) {
            return manifestJson;
        }
        try {
            JSONObject cur = new JSONObject(manifestJson);
            JSONObject fb = new JSONObject(fallbackJson);
            if (!cur.optString("resource_version", "").equals(fb.optString("resource_version", ""))) {
                return manifestJson;
            }
            JSONArray fbArr = fb.optJSONArray("files");
            JSONArray curArr = cur.optJSONArray("files");
            if (fbArr == null || curArr == null) return manifestJson;

            java.util.Map<String, String> perfMap = new java.util.HashMap<>();
            for (int i = 0; i < fbArr.length(); i++) {
                JSONObject it = fbArr.getJSONObject(i);
                String p = it.optString("perf_target_sha256", "");
                if (!p.isEmpty()) {
                    perfMap.put(it.getString("relative_path").replace('\\', '/'), p);
                }
            }
            if (perfMap.isEmpty()) return manifestJson;

            boolean changed = false;
            for (int i = 0; i < curArr.length(); i++) {
                JSONObject it = curArr.getJSONObject(i);
                String rel = it.getString("relative_path").replace('\\', '/');
                String p = perfMap.get(rel);
                if (p != null && it.optString("perf_target_sha256", "").isEmpty()) {
                    it.put("perf_target_sha256", p);
                    changed = true;
                }
            }
            return changed ? cur.toString() : manifestJson;
        } catch (Throwable ignored) {
            return manifestJson;
        }
    }

    private static String computeManifestPayloadHash(String manifestJson) {
        if (manifestJson == null || manifestJson.trim().isEmpty()) return "";
        try {
            JSONObject plan = new JSONObject(manifestJson);
            JSONArray arr = plan.getJSONArray("files");
            List<String> rows = new ArrayList<>(arr.length());
            for (int i = 0; i < arr.length(); i++) {
                JSONObject item = arr.getJSONObject(i);
                String rel = item.getString("relative_path").replace('\\', '/');
                String tgt = item.getString("target_sha256").toLowerCase(Locale.ROOT);
                rows.add(rel + ":" + tgt + "\n");
            }
            java.util.Collections.sort(rows);
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            for (String r : rows) md.update(r.getBytes(StandardCharsets.UTF_8));
            byte[] d = md.digest();
            StringBuilder sb = new StringBuilder(64);
            for (byte b : d) sb.append(String.format(Locale.ROOT, "%02x", b & 0xFF));
            return sb.toString();
        } catch (Throwable t) {
            return "";
        }
    }

    // -------------------------------------------------------------------------
    // HTTP & File Helpers
    // -------------------------------------------------------------------------
    private String httpGetString(String urlStr) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        conn.setUseCaches(false);
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(15000);
        conn.setRequestProperty("Cache-Control", "no-cache");
        conn.setRequestProperty("Pragma", "no-cache");
        conn.setRequestProperty("User-Agent", "AzurPromiliaVIMobile/" + getAppVersionName());
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
        android.util.Log.i("AzurVI", s);
        String ts = new SimpleDateFormat("HH:mm:ss", Locale.ROOT).format(new Date());
        runOnUiThread(() -> {
            tvLog.append("[" + ts + "] " + s + "\n");
        });
    }

    private void toast(String s) {
        runOnUiThread(() -> Toast.makeText(this, s, Toast.LENGTH_LONG).show());
    }
}
