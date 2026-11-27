# 运行工具 / Localization tools

| 文件 | 用途 |
|---|---|
| `Manage-Localization.ps1` | 操作菜单与任务调度 (thêm `-Language vi\|en\|zhcn`, tùy chọn `安装路径.json`) |
| `Locate-Installations.ps1` | 查找、设置及保存安装目录 |
| `Localization-Common.ps1` | 公共校验、备份、还原及进程检查 |
| `Apply-CRCZH.ps1` | 台服游戏备份、替换、校验与还原 (hỗ trợ `-Language`) |
| `Apply-JPCRCZH.ps1` | 日服游戏备份、替换、校验与还原 (hỗ trợ `-Language`) |
| `Apply-JPDeblur.ps1` | 日服反虚化 (Bỏ làm mờ JP `3273853` / 5 file — mặc định tắt) |
| `Apply-TWDeblur.ps1` | 台服反虚化 (Bỏ làm mờ TW `3273850` / 7 file — hỗ trợ `-Language`) |
| `Apply-Launchers.ps1` | 两服启动器备份、汉化与还原 (hỗ trợ `-Language`) |
| `Apply-AndroidVI.ps1` | [fork] Cài đặt / khôi phục / verify gói Việt hóa Android (`3273851`) qua ADB |
| `tw-deployment.json` / `jp-deployment.json` / `launcher-deployment.json` | Bản gốc tiếng Trung (`zhcn`) |
| `tw-deployment-vi.json` / `jp-deployment-vi.json` / `launcher-deployment-vi.json` / `android-deployment-vi.json` | [fork] Bảng triển khai tiếng Việt (`vi`) cho JP PC (`3273853`), TW PC (`3273850`) & Android (`3273851`) |
| `jp-deblur-deployment.json` / `tw-deblur-deployment.json` | 清单 bỏ làm mờ (Deblur) |
| `package-files.json` / `package-files-vi.json` | 安装包文件校验清单 (`zhcn` / `vi`) |
| `language.json` | [fork] Cấu hình ngôn ngữ cho chế độ tương tác |
| `安装路径.json` | 手动指定安装位置 |

使用时请下载 Releases 中的完整包，包含运行所需的全部 payload 替换资源。
