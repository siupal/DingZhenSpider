import os
from typing import Dict, Any

import pandas as pd
from wordcloud import WordCloud

from topics_baseline import tokenize  # 复用已有分词与停用词逻辑
from visualize import _pick_font  # 复用字体选择


def build_weekly_wordclouds(
    cleaned_comments_csv: str,
    candidate_weeks_csv: str,
    output_dir: str,
    max_words: int = 200,
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(cleaned_comments_csv) or not os.path.exists(candidate_weeks_csv):
        return ""

    comments = pd.read_csv(cleaned_comments_csv)
    if comments.empty:
        return ""

    # 补一个与 weekly 相同格式的 week 列
    ts = pd.to_datetime(comments["ctime"], unit="s", errors="coerce")
    comments = comments.assign(
        ts=ts,
        week=ts.dt.to_period("W").astype(str),
    )

    cweeks = pd.read_csv(candidate_weeks_csv)
    if cweeks.empty:
        return ""

    font_path = _pick_font()
    base_wc_dir = os.path.join(output_dir, "visualizations", "week_wordclouds")
    os.makedirs(base_wc_dir, exist_ok=True)

    out_paths = []

    for _, row in cweeks.iterrows():
        window = str(row["window"])
        wk = comments[comments["week"] == window]
        if wk.empty:
            continue
        # 构造该周的所有 message 文本
        texts = wk["message"].fillna("").astype(str).tolist()
        if not texts:
            continue
        # 分词 + 计数
        freq: Dict[str, int] = {}
        for s in texts:
            for w in tokenize(s):
                freq[w] = freq.get(w, 0) + 1
        if not freq:
            continue
        # 限制 max_words
        freq_sorted = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:max_words]
        freq_top = dict(freq_sorted)

        wc = WordCloud(
            font_path=font_path,
            width=1200,
            height=600,
            background_color="white",
        )
        img = wc.generate_from_frequencies(freq_top)
        safe_window = window.replace("/", "_")
        out_path = os.path.join(base_wc_dir, f"wc_week_{safe_window}.png")
        img.to_file(out_path)
        out_paths.append(out_path)

    return ";".join(out_paths)


def main() -> None:
    base_analysis = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    cleaned_csv = os.environ.get(
        "DZ_CLEANED_COMMENTS",
        os.path.join(base_analysis, "cleaned", "comments_cleaned.csv"),
    )
    cand_weeks = os.path.join(base_analysis, "candidate_weeks.csv")
    paths = build_weekly_wordclouds(cleaned_csv, cand_weeks, base_analysis)
    print(paths)


if __name__ == "__main__":
    main()
