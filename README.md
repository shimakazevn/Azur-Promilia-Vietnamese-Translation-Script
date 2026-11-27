# Azur Promilia — Việt Hóa (JP PC `3273853` & Android `3273851`)

Fork Việt hóa & đa ngôn ngữ từ [xiayuan0817/Azur-Promilia-Chinese-Translation-Script](https://github.com/xiayuan0817/Azur-Promilia-Chinese-Translation-Script).

> **Lưu ý an toàn:** Không chỉnh sửa hay ký lại APK gốc hay tệp thực thi `.exe`/`.dll`. Tất cả file `.r` Việt hóa và gói **Bỏ làm mờ (Deblur)** đều bảo toàn dung lượng và mã kiểm tra CRC32 gốc. Dự án chưa kiểm thử chống gian lận — nếu gặp lỗi đăng nhập, hãy bấm **Khôi phục bản gốc**.

## Trạng thái các bản dịch

| Ngôn ngữ | Trạng thái | Tải về & Chi tiết |
|---|---|---|
| `vi` — Tiếng Việt | ✅ Đã phát hành (JP PC `3273853` + Launcher `1.8.1` + **Android `3273851`** + **Bỏ làm mờ PC** + **Mod Đồ Họa Performance Mobile**) | Có trong [Releases](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/releases/latest) (`AzurPromilia-VI-Setup.exe`, `AzurPromilia-VI-Mobile.apk`, gói Offline PC & Android) |
| `zhcn` — 简体中文 | 🌏 Nguyên bản từ repo gốc (TW/JP + Deblur) | Tải gói gốc tại [Releases của xiayuan0817](https://github.com/xiayuan0817/Azur-Promilia-Chinese-Translation-Script/releases) |
| `en` — English | 🛠️ Khung chờ (`placeholder-no-payload`) | Chưa build payload |

## Tải về & Cài đặt nhanh (Tiếng Việt — Auto-Update)

Truy cập [Releases](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/releases/latest):

### A. Trên Windows PC (`AZUPRO_JP` — Resource `3273853`)
- **Cách 1 (Khuyên dùng — Web Installer + Auto-Update)**: Tải **`AzurPromilia-VI-Setup.exe`** (~5.2 MB) → Mở lên → Chọn **Cài đặt / Cập nhật Việt hóa**.
  - Giao diện Launcher kèm ảnh động & nhạc nền chính thức Azur Promilia (có nút bật/tắt ngay trên thanh tiêu đề), tự nhận diện `AZUPRO_JP` & `AZUPRO_JP_Gamelauncher`, tải gói từ GitHub Releases, kiểm tra SHA-256 + CRC32, tạo shortcut Desktop tự cập nhật khi mở game.
  - **Tùy chọn Bỏ làm mờ (Deblur — Tắt làm mờ nhân vật khi zoom gần / ngước camera):** **Mặc định TẮT** để an toàn tối đa. Bạn có thể bật/tắt bất kỳ lúc nào bằng nút **`Bật / Tắt Bỏ làm mờ`** ngay trong giao diện GUI cài đặt.
- **Cách 2 (Bản Full Offline)**: Tải **`AzurPromilia-Localization-Full-vi-v1.0.14.zip`** (~276 MB, kèm cả gói Bỏ làm mờ), giải nén rồi chạy `AzurPromilia-VI-Setup.exe` hoặc `双击运行.bat`.

### B. Trên Android Mobile (`com.Yostar.AzurpromiliaJP` — Resource `3273851`, Không cần Root)

Bản Mobile áp dụng kỹ thuật CRC32 đè trực tiếp vào 7 gói `.r` trong `/Android/data/com.Yostar.AzurpromiliaJP/files/.res/` — **không chỉnh sửa hay re-sign APK gốc**, giữ nguyên chữ ký Yostar.

#### Cách 1 — Cài thẳng trên điện thoại bằng App + Shizuku (Không cần PC)
1. **Cài game gốc & tải đủ tài nguyên:** Cài *Azur Promilia JP* từ store/APKPure, đăng nhập và tải xong toàn bộ dữ liệu trong game, sau đó **đóng hẳn game**.
2. **Cài [Shizuku](https://github.com/RikkaApps/Shizuku/releases)** (hoặc Google Play) và cài **`AzurPromilia-VI-Mobile.apk`** từ [Releases](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/releases/latest).
3. **Bật Shizuku bằng Wi-Fi ngay trên điện thoại:**
   - **Cài đặt → Giới thiệu điện thoại** → chạm 7 lần vào **Số bản dựng (Build number)** để bật *Tùy chọn nhà phát triển*.
   - **Hệ thống → Tùy chọn nhà phát triển** → bật **Gỡ lỗi không dây (Wireless debugging)**.
   - Mở **Shizuku** → mục *Bắt đầu qua Gỡ lỗi không dây* → bấm **Ghép đôi (Pairing)**, nhập mã 6 số → quay lại Shizuku bấm **Bắt đầu (Start)**.
4. **Cài đặt Việt hóa & Mod Đồ Họa Performance (Tùy chọn):**
   - Mở **`Azur Promilia Việt Hóa`** → bấm **Cấp quyền** Shizuku → bấm **Tải & Cài Đặt Việt Hóa (GitHub)**.
   - App tự báo khi GitHub có bản dịch hoặc APK mới, tự sao lưu bản gốc trước khi cài và hỗ trợ nút **Khôi phục gốc** 1 chạm.
   - **Mục (3) Mod Đồ Họa & Hiệu Năng (Đa thiết bị):** Tự nhận diện khả năng máy (máy yếu MediaTek/XOS/HyperOS, Snapdragon hay Gaming/Flagship) với **5 Preset** (Máy yếu `0.60×`, Cân bằng `0.75×`, Nguyên bản `1.00×`, Gaming Max + Mở khóa nhiệt/120Hz, **Tùy chỉnh Custom `0.45×–1.50×`**), chọn **Giới hạn FPS** (tới `120 FPS` + mở khóa giới hạn 60Hz Android 15+), **Hạ độ phân giải màn hình WM** cho máy yếu không có GameMode, **Thermal Unlock**, **Dọn RAM nền**, và nút **Bật / Tắt Mở Khóa Đồ Họa In-Game** (~24 MB, mở khóa *Tỷ lệ kết xuất 50%-170%*, *SSAA OFF*, *Chiếu sáng toàn cục / AO / Phản chiếu*, *DoF*, *LightShaft / LensFlare / UVDistort*, *ASM|CSM*).

#### Cách 2 — Cài nhanh qua cáp USB bằng máy tính (ADB 1-Click)
1. Bật **USB Debugging** trên điện thoại rồi cắm cáp vào PC.
2. Tải **`AzurPromilia-Localization-Android-vi-v1.0.14.zip`**, giải nén rồi chạy **`CaiDat-Android-ADB.bat`**.

## Thao tác bằng script (`双击运行.bat` — PC)

Khi dùng bản Full ZIP offline, chạy **`双击运行.bat`** (hỗ trợ kéo-thả thư mục game vào biểu tượng file `.bat`):

| Phím | Chức năng |
|---|---|
| `1` | Cài đặt Việt hóa toàn bộ (Game JP + Launcher, **không tự bật Bỏ làm mờ**) |
| `2` | Khôi phục toàn bộ về nguyên bản |
| `3` / `4` | Cài đặt / Khôi phục từng mục |
| `5` / `6` | Xem trạng thái file & backup / Kiểm tra CRC32 đầy đủ |
| `7` | Thêm/sửa đường dẫn game thủ công (lưu vào `tools/安装路径.json`) |
| `8` / `9` | **BẬT / TẮT Bỏ làm mờ JP (`1.0.2`, mặc định tắt)** |

## 资源基线与启动器版本 / Phiên bản gốc hỗ trợ

| Mục | Phiên bản |
|---|---|
| JP PC Game (`AZUPRO_JP`) | Resource `3273853`, Builtin `3075915` (Deblur: `1.0.2`) |
| JP Android Game (`com.Yostar.AzurpromiliaJP`) | Resource `3273851`, Builtin `2929638` |
| JP Launcher (`AZUPRO_JP_Gamelauncher`) | `1.8.1` |
| TW Game / Launcher | Resource `3221745` (`zhcn`), Launcher `1.0.1.4` |

## Phát triển & Tự build
- Chi tiết thuật toán CRC32, bộ giải mã (`CRC工具/resource_decode/` gồm `nofog.py`, `decode_mmap.py`, `reencrypt_bundle.py`) và kiểm thử tự động nằm trong [tools/README.md](tools/README.md) và `tests/run_tests.py`.
- Đóng gói release Việt hóa: `python build_release.py --payload payload-vi --version v1.0.14 --language vi`
- Báo lỗi tại [Issues](https://github.com/shimakazevn/Azur-Promilia-Vietnamese-Translation-Script/issues). Mã nguồn theo giấy phép [LICENSE](LICENSE) (Apache 2.0).
