# 文件用途

```text
双击运行.bat                         # 运行入口
使用说明.txt                         # 操作说明

tools/
├─ Manage-Localization.ps1            # 汉化菜单与任务调度
├─ Locate-Installations.ps1           # 查找游戏和启动器目录
├─ Apply-CRCZH.ps1                    # 台服游戏汉化与还原
├─ Apply-JPCRCZH.ps1                  # 日服游戏汉化与还原
├─ Apply-Launchers.ps1                # 两服启动器汉化与还原
├─ tw-deployment.json                 # 台服资源部署与校验配置
├─ jp-deployment.json                 # 日服资源部署与校验配置
├─ launcher-deployment.json           # 启动器部署与校验配置
├─ package-files.json                 # 汉化包文件校验清单
└─ 安装路径.json                       # 指定游戏和启动器目录

payload/tw_game/
├─ .res/raw_base_package/BundleFiles/
│  └─ v0k2cafcxjxawklow6skg.r          # 台服文本字符串池
├─ .res/raw_streaming_package/BundleFiles/
│  └─ 3iffxeedh2grvnbn2iag.r          # 台服语言表与文本索引
├─ .res/default_package/BundleFiles/
│  └─ owmxh3bjdhcwjoabqv67q.r         # 台服热更新字体配套资源
├─ StreamingAssets/.res/default_package/
│  ├─ a66pm5ie1rrjguuzlsyq.r          # 台服内置字体配套资源
│  ├─ p4hifvtlpthiunufa1lslg.r        # 台服内置字体配套资源
│  └─ db0aboccfhk0ruhzeueydq.r        # 台服内置字体配套资源
├─ StreamingAssets/.res/static_package/
│  └─ nkewfips4anrz2bqfjhpg.r         # 台服静态字体与本地化资源
└─ resources.assets                  # 台服内置本地化配套资源

payload/jp_game/
├─ .res/raw_base_package/BundleFiles/
│  └─ z5xzl3cg6ao0ilpbzykexg.r         # 日服文本字符串池
├─ .res/raw_streaming_package/BundleFiles/
│  └─ fcl0wxz2z6hoffogv4xgzw.r        # 日服语言表与文本索引
├─ .res/default_package/BundleFiles/
│  └─ yr49bxop0f3reujfsmyfca.r        # 日服热更新字体配置
├─ StreamingAssets/.res/default_package/
│  ├─ awcxxitzquckttvmx0c5q.r         # b00 字体资源
│  ├─ e5e4oijae8zliat91bgbw.r         # a00_jp_input_noheight 字体资源
│  ├─ hqqoy0ojvzpggukcf5m85w.r        # b00_jp_input_noheight 字体及配置
│  ├─ rpgxilrqhjgj9am5g799fa.r        # c00 字体资源
│  ├─ tqells6pca8ieju9qlbuw.r         # 日服内置字体配置
│  └─ xlpsyuxnoz1cjmawi1wcxa.r        # a00 字体资源
├─ StreamingAssets/.res/static_package/
│  └─ 6pq4a7hlp7zidu91dvvww.r         # 日服静态字体与文本资源
└─ resources.assets                  # 日服内置及启动阶段文案

payload/tw_launcher/resources/
└─ app.asar                          # 台服启动器界面汉化资源

payload/jp_launcher/resources/
└─ app.asar                          # 日服启动器界面汉化资源
```
