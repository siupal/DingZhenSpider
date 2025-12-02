import os
from glob import glob
from typing import List

import pandas as pd

from key_nodes_prepare import _score_text_continuous


def _load_candidate_weeks(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df if not df.empty else pd.DataFrame()


def _load_comments(cleaned_csv: str) -> pd.DataFrame:
    if not os.path.exists(cleaned_csv):
        return pd.DataFrame()
    df = pd.read_csv(cleaned_csv)
    if df.empty:
        return df
    ts = pd.to_datetime(df["ctime"], unit="s", errors="coerce")
    df = df.assign(
        ts=ts,
        week=ts.dt.to_period("W").astype(str),
    )
    return df


def _load_videos_from_data(data_dir: str) -> pd.DataFrame:
    """从本地已爬取的各类 CSV 中汇总视频元数据。

    优先使用本地数据目录（data/、data_click/、data_totalrank/、data_merged/、data_merged_relaxed），
    通过 bvid 去重后返回一个包含 title/view/reply/like 等字段的总表，
    以避免依赖联网补全。
    """
    base = os.path.abspath(data_dir)
    candidate_dirs: List[str] = [base]
    # 若存在其它采集输出目录，也一并纳入
    for sub in ["data_click", "data_totalrank", "data_merged", "data_merged_relaxed"]:
        p = os.path.join(os.path.dirname(base), sub)
        if os.path.isdir(p):
            candidate_dirs.append(p)

    files: List[str] = []
    for d in candidate_dirs:
        files.extend(glob(os.path.join(d, "comments_*.csv")))
        # data_merged / data_merged_relaxed 里也可能是按月合并后的 csv
        files.extend(glob(os.path.join(d, "*.csv")))

    if not files:
        return pd.DataFrame()

    dfs: List[pd.DataFrame] = []
    for fp in sorted(set(files)):
        try:
            df = pd.read_csv(fp)
            # 只保留含 bvid 的表作为候选元数据源
            if "bvid" in df.columns:
                dfs.append(df)
        except Exception:
            continue

    if not dfs:
        return pd.DataFrame()

    merged = pd.concat(dfs, ignore_index=True)
    # 按 bvid 去重，保留指标最高的一行（view 优先）
    if "view" in merged.columns:
        merged = merged.sort_values("view", ascending=False).drop_duplicates("bvid", keep="first")
    else:
        merged = merged.drop_duplicates("bvid", keep="first")
    return merged


def _compute_video_stats_for_week(wk_comments: pd.DataFrame) -> pd.DataFrame:
    if wk_comments.empty:
        return pd.DataFrame(columns=[
            "bvid", "comment_count", "comment_like_sum",
            "sent_mean", "sent_std",
        ])
    # 确保有连续情感分
    if "sent_raw" not in wk_comments.columns:
        wk_comments = wk_comments.copy()
        wk_comments["sent_raw"] = wk_comments["message"].fillna("").astype(str).apply(_score_text_continuous)
    # 仅对真正需要的列做聚合，避免 pandas 对分组列本身触发 FutureWarning
    g = wk_comments[["bvid", "like", "sent_raw"]].groupby("bvid", sort=False)
    stats = g.apply(
        lambda x: pd.Series({
            "comment_count": int(len(x)),
            "comment_like_sum": x["like"].fillna(0).astype(int).sum(),
            "sent_mean": float(x["sent_raw"].mean()),
            "sent_std": float(x["sent_raw"].std(ddof=0)) if len(x) > 1 else 0.0,
        }),
        include_groups=False,
    ).reset_index()
    return stats


def _attach_video_metrics(stats: pd.DataFrame, videos: pd.DataFrame) -> pd.DataFrame:
    if stats.empty:
        return stats
    if videos is None or videos.empty:
        return stats
    merged = stats.merge(videos, on="bvid", how="left", suffixes=("", "_video"))
    return merged


def _score_videos_in_week(df: pd.DataFrame, week_score: float) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    # 选择若干核心量纲做 z-score
    metric_cols = []
    for col in ["view", "reply", "like", "comment_count"]:
        if col in out.columns:
            metric_cols.append(col)
    for col in metric_cols:
        if out[col].notna().sum() >= 2:
            z = (out[col] - out[col].mean()) / out[col].std(ddof=0)
        else:
            z = 0.0
        out[f"z_{col}"] = z
    # 传播规模维度：这些 z 值中的最大值
    if metric_cols:
        z_cols = [f"z_{c}" for c in metric_cols]
        out["z_spread_max"] = out[z_cols].max(axis=1)
    else:
        out["z_spread_max"] = 0.0
    # 情绪偏离度：与当周整体情绪均值的差异
    out["sent_deviation"] = (out["sent_mean"] - float(week_score)).abs()
    # 简单重要性得分（可后续调优权重）
    out["importance"] = out["z_spread_max"] + out["sent_deviation"]
    return out


def extract_key_videos(
    candidate_weeks_csv: str,
    weekly_csv: str,
    cleaned_comments_csv: str,
    data_dir: str,
    output_dir: str,
    top_k_per_week: int = 5,
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    cand = _load_candidate_weeks(candidate_weeks_csv)
    weekly = pd.read_csv(weekly_csv) if os.path.exists(weekly_csv) else pd.DataFrame()
    comments = _load_comments(cleaned_comments_csv)
    videos = _load_videos_from_data(data_dir)

    if cand.empty or comments.empty:
        out = os.path.join(output_dir, "key_videos.csv")
        pd.DataFrame([], columns=[
            "window", "bvid", "title", "view", "reply", "like",
            "comment_count", "comment_like_sum", "sent_mean", "importance",
        ]).to_csv(out, index=False)
        return out

    weekly_mean = weekly.set_index("window") if not weekly.empty else None

    rows = []
    for _, w in cand.iterrows():
        window = w["window"]
        wk_comments = comments[comments["week"] == window]
        if wk_comments.empty:
            continue
        stats = _compute_video_stats_for_week(wk_comments)
        stats = _attach_video_metrics(stats, videos)
        # 获取该周整体情绪得分
        if weekly_mean is not None and window in weekly_mean.index:
            week_score = float(weekly_mean.loc[window, "score"])
        else:
            week_score = float(w.get("score", 0.0))
        scored = _score_videos_in_week(stats, week_score)
        scored["window"] = window
        # 每个周选前 top_k_per_week 个视频
        top = scored.sort_values("importance", ascending=False).head(top_k_per_week)
        rows.append(top)

    if rows:
        all_keys = pd.concat(rows, ignore_index=True)
    else:
        all_keys = pd.DataFrame([], columns=[
            "window", "bvid", "title", "view", "reply", "like",
            "comment_count", "comment_like_sum", "sent_mean", "importance",
        ])

    # 挑选输出字段，title/metrics 若不存在则自动填 NA
    cols = [
        "window", "bvid",
        "title", "view", "reply", "like",
        "comment_count", "comment_like_sum", "sent_mean",
        "z_spread_max", "sent_deviation", "importance",
    ]
    for c in cols:
        if c not in all_keys.columns:
            all_keys[c] = pd.NA
    all_keys = all_keys[cols]

    out = os.path.join(output_dir, "key_videos.csv")
    all_keys.to_csv(out, index=False)
    return out


def main() -> None:
    base_analysis = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    candidate_weeks_csv = os.path.join(base_analysis, "candidate_weeks.csv")
    weekly_csv = os.path.join(base_analysis, "sentiment_timeseries_weekly.csv")
    cleaned_comments_csv = os.environ.get(
        "DZ_CLEANED_COMMENTS",
        os.path.join(base_analysis, "cleaned", "comments_cleaned.csv"),
    )
    data_dir = os.environ.get("DZ_VIDEO_DATA", os.path.join("data"))
    out_dir = base_analysis
    path = extract_key_videos(
        candidate_weeks_csv=candidate_weeks_csv,
        weekly_csv=weekly_csv,
        cleaned_comments_csv=cleaned_comments_csv,
        data_dir=data_dir,
        output_dir=out_dir,
        top_k_per_week=5,
    )
    print(path)


if __name__ == "__main__":
    main()
