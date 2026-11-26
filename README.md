# Azur Promilia — Vietnamese / English Localization (fork)

Fork của [xiayuan0817/Azur-Promilia-Chinese-Translation-Script](https://github.com/xiayuan0817/Azur-Promilia-Chinese-Translation-Script) (bản gốc: 台服/日服 → 简体中文), do [shimakazevn](https://github.com/shimakazevn) fork để thêm **Tiếng Việt** và **English**.

《蓝色星原：旅谣》台服、日服游戏及启动器的本地化工具，支持汉化/翻译、还原和文件状态检查。

> **如出现无法登录，请还原文件。本项目未进行反作弊测试，不保证后续版本兼容。**

## Trạng thái ngôn ngữ / Language status

| Ngôn ngữ | Trạng thái | Payload |
| --- | --- | --- |
| `zhcn` — 简体中文 | ✅ Dùng được như bản gốc | Có trong Release gốc (`AzurPromilia-Localization-Full-v3.zip`) |
| `vi` — Tiếng Việt | ✅ Đã phát hành (JP PC `3219598` + Launcher `1.8.1` + **Android `3219596`**) | Có trong [Releases](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/releases) (`AzurPromilia-VI-Setup.exe`, `AzurPromilia-VI-Mobile.apk`, gói Offline PC & Android) |
| `en` — English | 🛠️ Scaffolding only | ❌ **Not built yet** — `target_sha256` is 64 zeros, Apply refuses |

Bản source Git nhỏ gọn không chứa file payload (~268 MB) — các file thay thế + bộ cài tự động cập nhật nằm tại mục **Releases**. (`tw_game` & `tw_launcher` ở bản VI vẫn giữ nguyên bản gốc).

## Chọn ngôn ngữ

Mặc định là `vi`. Đổi trong `tools/language.json` (`"language": "vi" | "en" | "zhcn"`), hoặc chạy:

```powershell
tools\Manage-Localization.ps1 -Language en
tools\Manage-Localization.ps1 -Language zhcn
```

Mỗi ngôn ngữ dùng bộ清单 riêng và thư mục riêng, để không lẫn với bản Trung:

- 清单: `tools/tw-deployment-<lang>.json`, `tools/jp-deployment-<lang>.json`, `tools/launcher-deployment-<lang>.json` (`zhcn` giữ tên gốc, không hậu tố)
- Payload: `payload/` (zhcn), `payload-vi/`, `payload-en/` (đều đã thêm vào `.gitignore`)
- Backup: `.<lang>-crc-readonly-3221745-backup` (台服), `.<lang>-jp-crc-readonly-3219598-backup` (日服), launcher `resources/app.asar.before-<lang>-20261126.bak`
- Đóng gói: `build_release.py --language vi|en|zhcn` (mặc định `zhcn`)

## Tải về & Cài đặt nhanh (Tiếng Việt — Auto-Update)

Truy cập [Releases](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/releases/latest):

### A. Trên Windows PC (`AZUPRO_JP` — Resource `3219598`)
- **Cách 1 (Khuyên dùng — Web Installer + Auto-Update)**: Tải **`AzurPromilia-VI-Setup.exe`** (~40 KB) → Mở lên → Chọn **Cài đặt / Cập nhật Việt hóa** (tự nhận diện `AZUPRO_JP` & `AZUPRO_JP_Gamelauncher`, tải gói từ GitHub Releases, kiểm tra SHA256 + CRC32, tạo shortcut Desktop tự cập nhật khi mở game).
- **Cách 2 (Bản Full Offline)**: Tải **`AzurPromilia-Localization-Full-vi-v1.0.3.zip`** (~268 MB), giải nén rồi chạy `AzurPromilia-VI-Setup.exe` hoặc `双击运行.bat`.

### B. Trên Android Mobile (`com.Yostar.AzurpromiliaJP` — Resource `3219596`, Không cần Root)

Bản Mobile áp dụng kỹ thuật CRC32 đè trực tiếp vào 7 gói `.r` trong `/Android/data/com.Yostar.AzurpromiliaJP/files/.res/` — **không chỉnh sửa hay re-sign APK gốc**, giữ nguyên chữ ký Yostar và chống vỡ kiểm tra file. Có 2 cách cài:

#### Cách 1 — Cài thẳng trên điện thoại bằng App + Shizuku (Không cần PC)
1. **Cài game gốc & tải đủ tài nguyên:** Cài *Azur Promilia JP* từ store/APKPure, đăng nhập và tải xong toàn bộ dữ liệu trong game, sau đó **đóng hẳn game**.
2. **Cài [Shizuku](https://github.com/RikkaApps/Shizuku/releases)** (hoặc tải từ Google Play) và tải **`AzurPromilia-VI-Mobile.apk`** từ mục [Releases](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/releases/latest).
3. **Bật Shizuku bằng Wi-Fi ngay trên điện thoại:**
   - Vào **Cài đặt → Giới thiệu điện thoại** → chạm 7 lần vào **Số bản dựng (Build number)** để mở *Tùy chọn nhà phát triển*.
   - Vào **Hệ thống → Tùy chọn nhà phát triển** → bật **Gỡ lỗi không dây (Wireless debugging)**.
   - Mở **Shizuku** → mục *Bắt đầu qua Gỡ lỗi không dây* → bấm **Ghép đôi (Pairing)**, nhập mã 6 số hiện trên thông báo → quay lại Shizuku bấm **Bắt đầu (Start)**.
4. **Cài đặt Việt hóa:**
   - Mở **`Azur Promilia Việt Hóa`** → bấm **Cấp quyền** Shizuku → bấm **Tải & Cài Đặt Việt Hóa (GitHub)**.
   - App tự động **báo ngay khi GitHub có bản dịch hoặc APK mới**, tự sao lưu bản gốc trước khi cài và hỗ trợ nút **Khôi phục gốc** 1 chạm.

#### Cách 2 — Cài nhanh qua cáp USB bằng máy tính (ADB 1-Click)
1. Cài game gốc và tải xong tài nguyên trên điện thoại, bật **USB Debugging** trong *Tùy chọn nhà phát triển* rồi cắm cáp vào PC.
2. Tải **`AzurPromilia-Localization-Android-vi-v1.0.3.zip`**, giải nén rồi chạy **`CaiDat-Android-ADB.bat`** (cần có `adb.exe` trên PATH hoặc trong `%LOCALAPPDATA%\Android\Sdk\platform-tools\`).

> **Lưu ý Mobile:**
> - Do giữ nguyên APK gốc không sửa, màn hình loading đầu tiên khi vừa khởi chạy app (chữ nằm trong `builtInLangString` của APK) vẫn giữ nguyên gốc; toàn bộ UI, kỹ năng, cốt truyện và font chữ tiếng Việt khi vào game hiển thị đầy đủ.
> - Nếu game cập nhật phiên bản tài nguyên mới hơn `3219596`, server sẽ tải lại bundle mới — mở app **`Azur Promilia Việt Hóa`** để nhận thông báo ngay khi có bản patch mới trên GitHub.

**Lưu ý:** Repo mã nguồn không đính kèm file payload nhị phân; tải Source ZIP từ nút Code sẽ không có sẵn file thay thế. Để dùng bản Trung (`zhcn`) gốc, xem [Releases bản gốc](https://github.com/xiayuan0817/Azur-Promilia-Chinese-Translation-Script/releases).

## 操作方法

1. 完整解压汉化包，保留原有目录结构。
2. 完全退出游戏和启动器，包括托盘中的后台程序。
3. 双击 **`双击运行.bat`**。
4. 输入编号并回车执行。

| 选项 | 功能 |
| --- | --- |
| 1 | 全部汉化 / Dịch tất cả |
| 2 | 全部还原 |
| 3 | 选择项目汉化 |
| 4 | 选择项目还原 |
| 5 | 查看文件状态 |
| Q | 退出 |

选择部分项目时，可用逗号分隔多个编号，例如 `1,3`。

脚本会自动查找游戏和启动器目录。未找到时，可将安装文件夹拖到 **`双击运行.bat`** 图标上；也可在 `tools/安装路径.json` 中填写对应路径。

## 支持版本

| 项目 | 对应版本 |
| --- | --- |
| 台服游戏 | 资源版本 `3221745` |
| 日服游戏 | 资源版本 `3219598`，内置资源版本 `3075915` |
| 台服启动器 | `1.0.1.4` |
| 日服启动器 | `1.8.1` |

提示版本不匹配时，请停止操作，等待对应版本的汉化包。

## 汉化范围

- 台服游戏文本及相关字体资源。
- 日服游戏文本、内置启动文案及相关字体资源。
- 台服、日服启动器界面。

主要采用国服官方简体文案。服务器动态下发的内容及图片内文字可能仍显示原文。

## 资源校验

游戏资源汉化采用等长替换及 CRC 配平方案，目标是保留原版资源大小、分段 CRC 和整包 CRC。

## 备份与还原

汉化前会备份原版文件，请勿手动删除（`<lang>` là `zhcn`/`vi`/`en` tùy ngôn ngữ đã chọn）：

| 项目 | 备份位置 |
| --- | --- |
| 台服游戏 | 游戏目录下 `.<lang>-crc-readonly-3221745-backup` |
| 日服游戏 | 游戏目录下 `.<lang>-jp-crc-readonly-3219598-backup` |
| 启动器 | `resources/app.asar.before-<lang>-20261124.bak` (zhcn) / `.before-<lang>-20261126.bak` (vi/en) |

更新游戏或启动器前，建议先还原文件。

报错时请查看窗口提示；本次操作日志位于 `tools/logs`。

## 源码目录

```text
├─ 双击运行.bat        # 运行入口
├─ tools/              # 汉化菜单、路径查找、部署与还原
│  ├─ language.json    # [fork] Ngôn ngữ mặc định: vi
│  ├─ tw-deployment-vi.json / tw-deployment-en.json      # [fork] 清单 VI/EN (placeholder)
│  ├─ jp-deployment-vi.json / jp-deployment-en.json      # [fork] 清单 VI/EN (placeholder)
│  ├─ launcher-deployment-vi.json / launcher-deployment-en.json
│  └─ package-files-vi.json / package-files-en.json      # [fork] 清单 gói VI/EN (placeholder)
├─ CRC工具/
│  ├─ crc/             # 台服资源处理与校验工具
│  └─ jp_crc/          # 日服资源处理与校验工具
├─ build_release.py    # 发布包构建脚本 (thêm --language)
└─ README.md           # 项目说明
```

CRC 工具目录包含资源分析、构建、校验脚本及报告；部分脚本依赖原始资源、外部库和本地路径，不能直接作为独立程序运行。

## 问题反馈

请在 [Issues](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/issues) 中提供：

- 台服或日服，以及游戏或启动器版本。
- 操作选项和完整报错。
- 对应日志，或未汉化位置的截图。

提交日志前，请隐去账号、令牌等个人信息。

## 许可说明

项目源码许可见 [LICENSE](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/blob/main/LICENSE) (Apache 2.0, bản gốc).

游戏及第三方资源归原权利人所有，源码许可不代表对游戏资源的授权。
