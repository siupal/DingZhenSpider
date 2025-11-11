# DingZhenSpider – Bilibili 视频采集与统计（路线A）

本项目基于公开 Web 接口（popular、ranking）采集 B 站视频数据，支持保存到 CSV 与 SQLite，并生成基础统计报表。

注意：本实现优先使用无需 WBI 的公开接口，适合作为热门与排行榜的快速采集方案。若后续需要搜索、UP 主投稿等，需要适配 WBI 签名或改用 SDK/APP 接口。

## 功能
- popular 热门分页采集（pn/ps）
- ranking 排行（全站或分区 rid，day=1/3/7）
- search 关键词搜索（order、pages、page_size），支持时间过滤与导出
- comments 热门评论抓取（按 bvid 取 TopK 热评，包含楼层关系）
- 输出 CSV 与 SQLite（按 bvid 去重，支持更新）
- 统计与报表（总播放/点赞、TopN）
- 词云生成（scripts/make_wordcloud.py）：
  - 中文分词（jieba）与停用词过滤
  - 蒙版/形状：阈值（二值化）或 GrabCut 分割（可用 --rect 精调）
  - 颜色：
    - 单色词语（--word_color "#000000" 等）
    - 从参考图取色（--color_ref 或默认用 --ref）
  - 形态：剪影内填充，支持反转蒙版（--invert_mask）
  - 合成：将词云前景叠加到参考图（--composite_on --opacity）
  - 画布：尺寸/词数可调（--width --height --max_words）

## 快速开始
1. 创建与激活虚拟环境（Windows PowerShell）：
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. 安装依赖：
   ```powershell
   pip install -r requirements.txt
   ```
3. 运行（示例）：
   - 抓取热门前 10 页（每页 20 条，默认）：
     ```powershell
     python main.py popular --pages 10 --ps 20
     ```
   - 抓取全站排行榜 day=3：
     ```powershell
     python main.py ranking --day 3 --rid 0
     ```
   - 关键词搜索并保存（示例：关键词“丁真”，按播放量）：
     ```powershell
     python main.py search --keyword 丁真 --order view --pages 5 --page_size 40
     ```
   - 抓取 2024-07 的“丁真”视频中按播放量最高的 3 个视频的热门评论（每个 10 条）：
     ```powershell
     python main.py comments --keyword 丁真 --year_month 2024-07 --topn 3 --k 10
     ```
   - 生成剪影词云（黑字白底，参考图做蒙版，GrabCut 分割）：
     ```powershell
     python .\scripts\make_wordcloud.py --csv .\data\popular.csv --columns title tname --font "C:\Windows\Fonts\msyh.ttc" --ref .\assets\dingzhen2.jpeg --segment grabcut --invert_mask --contour_width 0 --background white --max_words 1200 --width 2048 --height 2048 --out .\data\wordcloud_silhouette.png
     ```
   - 生成彩色剪影（形状来自 --ref，颜色取自 --color_ref）：
     ```powershell
     python .\scripts\make_wordcloud.py --csv .\data\popular.csv --columns title tname --font "C:\Windows\Fonts\msyh.ttc" --ref .\assets\badapple.jpg --segment grabcut --invert_mask --color_ref .\assets\dingzhen2.jpeg --contour_width 0 --background white --max_words 1200 --width 2048 --height 2048 --out .\data\wordcloud_badapple_color.png
     ```
   - 将词云叠加在参考图前景：
     ```powershell
     python .\scripts\make_wordcloud.py --csv .\data\popular.csv --columns title tname --font "C:\Windows\Fonts\msyh.ttc" --ref .\assets\dingzhen2.jpeg --segment grabcut --invert_mask --contour_width 0 --background white --max_words 1200 --width 2048 --height 2048 --composite_on .\assets\dingzhen2.jpeg --opacity 1.0 --out .\data\wordcloud_silhouette_color_composite.png
     ```

数据将保存到 `data/` 目录，并生成 `summary.csv` 与 TopN 报表。

## 配置
- 在 `config.yaml` 中可配置输出目录、代理、限速、默认请求头等；命令行参数可覆盖配置文件。
- 如遇 412/反爬，建议在 `config.yaml` 的 headers 中加入登录后的 Cookie（SESSDATA、buvid3 等），并按需配置代理。

## 常见问题
- 词云透明背景与描边冲突：开启透明（或合成）时请将 `--contour_width 0`。
- PIL 保存报错：请使用 `.png` 后缀输出（透明/合成推荐 PNG）。
- 词云“无处可画/空间不足”错误：减小 `--max_words`，或提高画布尺寸，或用 `--rect`/提高分割质量，或使用阈值法 `--segment threshold --threshold 140`。
- 词云跑到背景：加 `--invert_mask` 使人物区域成为可填充（白色）区域。

## 法律与合规
- 仅用于学习与研究，请遵守目标网站的服务条款与相关法律法规。
- 请合理控制抓取频率，避免对站点造成压力。
