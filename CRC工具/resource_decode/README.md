# 资源解码工具

| 文件 | 用途 |
| --- | --- |
| `decode_mmap.py` | 解码 mmap 加密资源 |
| `parse_language_tables.py` | 解析语言表并比对简繁文本 |
| `vstring_pool.py` | 读取字符串池及字符串位置 |
| `rebuild_vstring.py` | 重建字符串池并保留原键值 |
| `reencrypt_bundle.py` | 重新封装并加密 UnityFS Bundle |
| `nofog.py` | 生成等长、CRC32 不变的反虚化资源 |
| `crcpatch.py` | 在四字节自由位配平 CRC32 |

依赖关系：
- `crc/fit_raw.py`、`jp_crc/raw.py` 使用语言表、字符串池和 mmap 解码工具。
- `crc/fit_bundles.py`、`jp_crc/bundles.py` 使用 Bundle 加密工具。
- `parse_language_tables.py`、`rebuild_vstring.py` 依赖同目录的 `vstring_pool.py`。

注意事项：
- 解码需要 Node.js，以及同目录的 `local_mmap_key.bin`、`local_mmap_iv.bin`；密钥不提交仓库。
- `nofog.py` 需要 UnityPy、pycryptodome、lz4 及环境变量 `AZUR_BUNDLE_KEY`；密钥不提交仓库。
- `reencrypt_bundle.py` 示例入口还需外部 `unity_setup.py`；自定义文本追加功能还需 `vstring_hash.py`。
- 示例入口保留原研究环境的输入、输出路径，运行前须按实际位置调整。
- 仅供资源研究与构建；生成资源、缓存和密钥不上传，也不加入完整运行包。
