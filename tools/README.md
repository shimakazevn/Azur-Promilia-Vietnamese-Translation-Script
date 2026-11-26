# 汉化与还原运行工具 / Localization tools

| 文件 | 用途 |
|---|---|
| `Manage-Localization.ps1` | 汉化与还原菜单、项目选择和操作日志 (thêm `-Language vi|en|zhcn`) |
| `Locate-Installations.ps1` | 查找游戏和启动器安装位置 |
| `Apply-CRCZH.ps1` | 台服游戏备份、替换、校验与还原 |
| `Apply-JPCRCZH.ps1` | 日服游戏备份、替换、校验与还原 |
| `Apply-Launchers.ps1` | 两服启动器备份、汉化与还原 |
| `language.json` | [fork] Ngôn ngữ mặc định (`vi`); đổi `vi`/`en`/`zhcn` tại đây |
| `tw-deployment.json` | 台服游戏文件清单 (zhcn, bản gốc) |
| `jp-deployment.json` | 日服游戏文件清单 (zhcn, bản gốc) |
| `launcher-deployment.json` | 两服启动器文件清单 (zhcn, bản gốc) |
| `tw-deployment-vi.json` / `tw-deployment-en.json` | [fork] 台服清单 VI/EN — `status: placeholder-no-payload`, `target_sha256` toàn 0 |
| `jp-deployment-vi.json` / `jp-deployment-en.json` | [fork] 日服清单 VI/EN — placeholder |
| `launcher-deployment-vi.json` / `launcher-deployment-en.json` | [fork] 启动器清单 VI/EN — placeholder |
| `package-files.json` | 安装包文件校验清单 (zhcn) |
| `package-files-vi.json` / `package-files-en.json` | [fork] 清单 gói VI/EN — placeholder, chưa có file nào |
| `安装路径.json` | 手动指定安装位置 |

使用时请下载 Releases 中的完整包，包含运行所需的全部 payload 替换资源。

**VI/EN:** payload chưa có nên Apply/ValidatePayload sẽ từ chối với thông báo rõ ràng. Chỉ `zhcn` mới áp dụng được như bản gốc. Khi build xong payload VI/EN (bằng `CRC工具/`, giữ nguyên độ dài + CRC), cập nhật `target_sha256` trong các file `*-deployment-vi/en.json`, đổi `status` thành `ready`, và tạo lại `package-files-vi/en.json` bằng `build_release.py --language vi|en`.
