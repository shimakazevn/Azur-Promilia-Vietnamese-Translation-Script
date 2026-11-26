# 汉化与还原运行工具

| 文件 | 用途 |
|---|---|
| `Manage-Localization.ps1` | 汉化与还原菜单、项目选择和操作日志 |
| `Locate-Installations.ps1` | 查找游戏和启动器安装位置（含快捷方式识别） |
| `Localization-Common.ps1` | 公共安全校验、进程检测及单遍 Slicing-by-8 CRC32/SHA-256 引擎 |
| `Apply-CRCZH.ps1` | 台服游戏备份、替换、校验与还原 |
| `Apply-JPCRCZH.ps1` | 日服游戏备份、替换、校验与还原 |
| `Apply-Launchers.ps1` | 两服启动器备份、汉化与还原 |
| `tw-deployment.json` | 台服游戏文件清单 |
| `jp-deployment.json` | 日服游戏文件清单 |
| `launcher-deployment.json` | 两服启动器文件清单 |
| `package-files.json` | 安装包文件校验清单 |
| `安装路径.json` | 手动指定安装位置 |

使用时请下载 Releases 中的完整包，包含运行所需的全部 payload 替换资源。
