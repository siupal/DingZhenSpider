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

## 脚本逻辑关系与协作（路线B：搜索+评论+防风控+分析）

本小节梳理“关键词搜索 + 月度评论抓取 + 防风控韧性采集 + 多排序合并 + 基线分析”的端到端流程，以及各脚本的职责与协作方式。

### 1) 采集层
- main.py
  - CLI 入口，包含四种模式：`popular`、`ranking`、`search`、`comments`。
  - 适合快速试跑与小规模验证。

- scripts/run_monthly_comments.py
  - 按年月遍历"关键词"搜索结果，选取 TopN 视频，抓取每视频的热门评论（含多排序兜底与分页）。
  - 特性：
    - 语义成功判定：防止被“空结果”覆盖已有较好结果。
    - 错误信息单独 CSV：例如“UP主已关闭评论区”。
    - 可跳过早期稀疏月份（如 2020-10）。

- scripts/run_resilient_collect.py（推荐批量生产用）
  - 在 monthly 脚本的基础上，加入“月份乱序 + Cookie/代理/UA 轮换 + 指数退避 + 检查点 + 尝试日志 + 自动待机”等防风控韧性策略。
  - 关键参数：
    - `--pages`、`--page_size`：搜索页数与每页条数（推荐 pages≥8，page_size=50）。
    - `--top_videos`、`--top_comments`：每月纳入的视频数量（我们测试至少300，不然爬到的csv相关行数太少）与每视频抓取评论数（可按带宽上调）。
    - `--orders`：排序维度（点击量 click、综合 totalrank、发布时间 pubdate）。
    - `--proxies`、`--cookies`、`--user_agents`：从文件轮换资源。
    - `--checkpoint`、`--attempt_log`：断点续跑与尝试日志。
    - `--initial_sleep`、`--sleep_cap`、`--jitter`：指数退避与抖动，缓解风控。

- 配置与资源文件
  - config.yaml：全局默认配置（headers、限速、输出路径等），命令行可覆盖。
  - cookies.txt：每行一组 Cookie（含 SESSDATA、bili_jct、buvid3 等关键字段）。
  - proxies.txt：每行一个代理（如 `http://127.0.0.1:7890`）。
  - uas.txt：每行一个 UA（User-Agent），建议混合常见浏览器 UA 以轮换。

### 2) 多排序合并与去重
- 目标：缓解单一排序导致的召回偏差。常用做法是分别按 `click` 与 `totalrank` 各跑一遍，再合并去重。
- 脚本：scripts/merge_dedup.py
  - 用法示例：
    ```powershell
    # 先分别输出到不同目录
    python scripts/run_resilient_collect.py ... --orders click     --output_dir data_click     --checkpoint analysis/resilient_checkpoint_click.json
    python scripts/run_resilient_collect.py ... --orders totalrank --output_dir data_totalrank --checkpoint analysis/resilient_checkpoint_totalrank.json

    # 合并去重
    python scripts/merge_dedup.py --dir_a data_click --dir_b data_totalrank --out_dir data_merged --keys rpid,id,reply_id
    ```
  - 去重键优先级：默认 `rpid,id,reply_id`；若缺失则回退到文本列（content/message/text）+ ID 列（rpid/id/reply_id/bvid/oid/mid/uid）的组合。

### 3) 分析层（analysis/）
- preprocess.py：从评论 JSON/CSV 提取与清洗，输出规范化 CSV（去重、时间标准化等）。
- sentiment_baseline.py：轻量情感基线（词典 + emoji 规则），按月度聚合情感分数。
- topics_baseline.py：关键词/话题基线（jieba 分词 + 停用词过滤），按月统计高频词 TopN。
- visualize.py：
  - 画情感时间序列折线图与月度词云。
  - 自动探测系统中文字体；WordCloud 指定中文字体防止乱码。
- closed_comments.py：汇总“评论区关闭/受限”的视频，并可与视频清单关联输出明细/汇总表。
- scripts/run_analysis.py：一键串联清洗、情感、话题与可视化（可按需选择阶段）。

### 4) 数据产物与目录
- data/、data_click/、data_totalrank/、data_merged/：分月度输出评论 CSV/JSON。
- analysis/visualizations/：图表与词云。
- analysis/resilient_checkpoint*.json：断点续跑检查点。
- analysis/resilient_attempts*.csv：韧性采集的尝试日志（包含风控等待、轮换信息等）。

### 5) 典型流水线
1. 防风控采集（示例：扩大采样 + 点击量排序）
   ```powershell
   python scripts/run_resilient_collect.py --config config.yaml --keyword "丁真" --from_ym 2020-11 --to_ym 2025-11 --orders click --pages 12 --page_size 50 --top_videos 100 --top_comments 200 --output_dir data_click --proxies proxies.txt --cookies cookies.txt --user_agents uas.txt --max_retries_per_month 5 --initial_sleep 8 --sleep_cap 1500 --jitter 0.35 --checkpoint analysis/resilient_checkpoint_click.json --attempt_log analysis/resilient_attempts_click.csv --shuffle_months
   ```
2. 再跑一次综合排序 totalrank（输出到 data_totalrank），随后执行：
   ```powershell
   python scripts/merge_dedup.py --dir_a data_click --dir_b data_totalrank --out_dir data_merged --keys rpid,id,reply_id
   ```
3. 基线分析与可视化：
   ```powershell
   python scripts/run_analysis.py --input_dir data_merged --font "C:\\Windows\\Fonts\\msyh.ttc" --months 2020-11:2025-11
   ```

### 6) 风控与恢复要点
- 风控信号：
  - 搜索结果突然为空/很弱；接口返回 code 非 0 或提示“账号未登录/权限不足”；日志出现“WindCtrl?”。
- 恢复策略：
  - 启用 `--shuffle_months`，跨月度错峰；
  - 轮换 `--proxies/--cookies/--user_agents`；
  - 调高 `--initial_sleep/--sleep_cap` 并加 `--jitter`；
  - 使用 `--checkpoint` 支持可中断续跑，不会重复已完成月份；
  - 合理控制 `--pages` 与 `--top_videos/--top_comments`，逐步放量，观察命中率再上调。

### 7) 常见问题（针对“样本弱关联/列较少”）
- 采样不足：提高 `--pages`、`--top_videos`、`--top_comments`；
- 排序偏置：增加 `totalrank`/`pubdate` 并合并去重；
- 登录/风控降级：确保 cookies 有效且可轮换，代理与 UA 生效；
- 字段不够：用 preprocess/analysis 流程扩展导出字段；如需更细的评论元数据，可提 Issue 说明需求.
