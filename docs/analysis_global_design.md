# 丁真形象演变数据分析：全局设计

## 1. 目标与研究问题
- 追踪“丁真”互联网形象的诞生与演变，解析其在评论与话语中的情感、话题与语义迁移。
- 定位关键历史节点（事件/媒体曝光/话题拐点），并对典型视频与评论做深描。
- 产出直观可视化：
  - 情感-时间热力图（加权）。
  - 话题演化流图/河流图。
  - 时间线与节点注释。
  - 关键词词云与共现网络。

## 2. 范围与时间粒度
- 时间范围：从 2020-10 起至今（先覆盖 2020-10 ~ 2021-03 作为首批）。
- 时间粒度：半月为主；对峰值区间下钻到周/日粒度。
- 平台：哔哩哔哩（视频与评论）。
- 语种：中文为主，保留 emoji 与常见符号用于情感判别。

## 3. 关键词体系（迭代扩展）
- 核心：丁真、一眼丁真、甜野男孩、理塘。
- 相关与抽象文化：锐克/瑞克/Rick、康巴、藏族小伙、甘孜、川西、理塘丁真、丁真宇宙、抽象丁真、质朴、纯真。
- 异形/误拼：丁钲/汀真/丁針、Dingzhen。
- 扩展策略：
  - 从月度评论高频词与共现图挖掘新词，滚动加入词表；维护黑/白名单降噪（如 Rick 语境歧义）。

## 4. 采集数据与方法
- 主语料（搜索→按月筛→抓热评）：
  - 每关键词，每月抓取搜索结果 N 页×M 条（默认 8×50），筛选当月发布视频，按播放量排序取 TopK（10~20），抓取每个视频热门评论 TopC（20~50）。
  - 入口脚本：`scripts/run_monthly_comments.py`（已优化“小月成功判定”）。
- 基线语料：
  - 定期抓取全站 `popular`/`ranking` 作为背景对照，识别平台整体波动对结果的影响。
- 稳健性：
  - 支持代理、重试、指数退避；必要时在评论接口热评为空时回退点赞/时间排序（可小改实现）。

### 4.1 运行示例（PowerShell 单行，批量关键词）
```powershell
$kwList = @("丁真","一眼丁真","理塘","甜野男孩")
foreach ($kw in $kwList) {
  python scripts/run_monthly_comments.py --keyword "$kw" --from_ym 2020-10 --to_ym 2021-03 --orders click totalrank pubdate --pages 8 --page_size 50 --top_videos 10 --top_comments 30 --retry 5 --backoff 2.0 --sleep_sec 6 --output_dir data
}
```
可选代理：追加 `--proxy http://127.0.0.1:7890`。

## 5. 数据模式与存储
- 视频表（CSV/SQLite，项目已实现）
  - 字段：`bvid,title,tname,pubdate,duration,owner,view,danmaku,reply,favorite,coin,share,like`；按 `bvid` 去重。
- 评论 JSON（项目已实现）
  - 列表项：`{ video: <视频字段子集>, comments: { bvid, aid, replies: [{rpid,parent,floor,like,ctime,uname,mid,message}, ...] } }`。
- 元数据（建议新增旁路 meta，不改现有 schema）
  - 采集时间、关键词、排序、pages/page_size、top_videos/top_comments、HTTP 参数（proxy/timeout/retry）、脚本版本。
  - 作用：保证可追溯与结果对比。
- 目录建议：
  - `data/`
    - `comments_{keyword}_{yyyymm}.json`
    - `comments_{keyword}_{yyyymm}.csv` / `.sqlite`
    - `summary.csv`, `top_view.csv`, `top_like.csv`
    - `meta/run_{timestamp}_{keyword}_{from_ym}_{to_ym}.meta.json`
  - `analysis/`
    - `cleaned/`, `tokens/`, `sentiment_timeseries.csv`, `topics_by_window.csv`
    - `visualizations/heatmap.png`, `river.png`, `timeline.png`, `wordclouds/`

## 6. 预处理
- 文本清洗：HTML/表情去噪（保留 emoji 原字符），全角半角标准化，去 URL/@/话题标签。 
- 去重：评论按 `rpid` 去重，保留首见；视频按 `bvid` 已处理。
- 语言与长度过滤：过滤极短/重复性强评论（单表情/纯标点等）。
- 分词与词表：jieba 自定义词典（核心词、地名、专有名）；维护停用词清单。

## 7. 分析方法
- 情感/情绪分析：
  - 基线：规则/词典 + 轻量模型（正/负/中）。
  - 标注与校准：人工标注小样本，微调或选择更适配的中文模型（如 RoBERTa）。
  - 加权聚合：按评论点赞、楼层热度、视频播放量加权到时间窗。
- 话题与关键词演化：
  - 关键词：TF-IDF/YAKE/KeyBERT（中文需向量化支持）
  - 主题：LDA（基线）→ BERTopic（增强）；在时间窗上做主题簇追踪与相似度连边。
- 关键节点检测：
  - 指标：发布/评论量、情感均值与方差、负向/讽刺占比、关键词新颖度、话题分布突变。
  - 方法：移动 Z-Score、CUSUM；必要时 BOCPD。

## 8. 可视化方案
- 情感-时间热力图（窗×情感维度，颜色=加权强度）。
- 话题演化河流图/桑基图（主题簇随时间分裂与汇合）。
- 时间线+节点注释（峰值处标注代表视频与评论）。
- 词云（每窗/节点）。

## 9. 质量控制与风险
- 风控与限流：使用代理、重试、退避；必要时在评论接口做排序回退。
- 噪音与误配：关键词黑/白名单、共现过滤、人工抽检。
- 数据稀疏：已放宽“小月”成功判定，确保可用样本沉淀。
- 可复现性：记录 meta；固定依赖版本；关键步骤保留随机种子。

## 10. 里程碑
- M1 采集与清洗（核心词 2020-10~2021-03）。
- M2 情感时间序列 + 基础可视化。
- M3 话题演化与关键节点检测。
- M4 典型节点深描与报告。

## 11. 与现有代码的衔接
- 采集：`main.py` 与 `scripts/run_monthly_comments.py` 已满足主体抓取；可选增加“热评为空→点赞/时间”兜底。
- 存储：`src/storage.py` 负责 CSV/SQLite；`src/stats.py` 产出概览统计。
- 依赖：`requirements.txt` 已包含 requests/PyYAML/pandas/wordcloud/jieba/matplotlib 等。

## 12. 后续工作
- 批量跑核心与扩展关键词，生成首批数据与 meta。
- 实现预处理与情感/话题基线脚本；输出首版可视化模板。
- 人工审阅关键节点并优化词表与模型。
