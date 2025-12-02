import os
import pandas as pd
import matplotlib.pyplot as plt
from wordcloud import WordCloud


def _pick_font():
    fp = os.environ.get("DZ_FONT")
    if fp and os.path.exists(fp):
        return fp
    candidates = [
        r"C:\\Windows\\Fonts\\msyh.ttc",
        r"C:\\Windows\\Fonts\\msyh.ttf",
        r"C:\\Windows\\Fonts\\SimHei.ttf",
        r"C:\\Windows\\Fonts\\simhei.ttf",
        r"/System/Library/Fonts/STHeiti Light.ttc",
        r"/Library/Fonts/Arial Unicode.ttf",
        r"/usr/share/fonts/truetype/arphic/ukai.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


_FONT_PATH = _pick_font()
if _FONT_PATH:
    try:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


def plot_sentiment(ts_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(ts_csv):
        return ""
    df = pd.read_csv(ts_csv)
    if df.empty:
        return ""
    df = df.sort_values("window")
    fig, ax = plt.subplots(figsize=(10,4))
    ax.plot(df["window"], df["score"], marker="o", label="Weighted score", color="#2196f3")
    ax.set_xlabel("window")
    ax.set_ylabel("weighted sentiment")
    ax.set_title("Sentiment over time")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    plt.xticks(rotation=45, ha="right")
    path = os.path.join(output_dir, "visualizations", "sentiment_timeseries.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _load_sentiment_with_ratios(ts_csv: str) -> pd.DataFrame:
    if not os.path.exists(ts_csv):
        return pd.DataFrame()
    df = pd.read_csv(ts_csv)
    if df.empty:
        return df
    df = df.sort_values("window")
    # 兼容老版本 CSV：若无比例列则按 count 现场计算
    if not {"pos_ratio", "neg_ratio", "neu_ratio"}.issubset(df.columns):
        count_safe = df["count"].replace(0, pd.NA).astype("Float64")
        df["pos_ratio"] = (df["pos"] / count_safe).fillna(0.0)
        df["neg_ratio"] = (df["neg"] / count_safe).fillna(0.0)
        df["neu_ratio"] = (df["neu"] / count_safe).fillna(0.0)
    return df


def plot_sentiment_ratios(ts_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    df = _load_sentiment_with_ratios(ts_csv)
    if df.empty:
        return ""
    fig, ax = plt.subplots(figsize=(10,5))
    x = df["window"]
    ax.stackplot(
        x,
        df["pos_ratio"],
        df["neu_ratio"],
        df["neg_ratio"],
        labels=["Positive", "Neutral", "Negative"],
        colors=["#4caf50", "#9e9e9e", "#f44336"],
        alpha=0.85,
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("Proportion")
    ax.set_xlabel("Month")
    ax.set_title("Monthly Sentiment Composition")
    ax.grid(alpha=0.2, axis="y")
    ax.legend(loc="upper right")
    plt.xticks(rotation=45, ha="right")
    path = os.path.join(output_dir, "visualizations", "sentiment_ratios.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_sentiment_ratio_and_score(ts_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    df = _load_sentiment_with_ratios(ts_csv)
    if df.empty:
        return ""
    fig, ax1 = plt.subplots(figsize=(10,5))
    x_idx = list(range(len(df)))
    x_labels = df["window"].tolist()

    width = 0.35
    ax1.bar(
        [i - width/2 for i in x_idx],
        df["pos_ratio"],
        width=width,
        color="#4caf50",
        alpha=0.85,
        label="Positive ratio",
    )
    ax1.bar(
        [i + width/2 for i in x_idx],
        df["neg_ratio"],
        width=width,
        color="#f44336",
        alpha=0.85,
        label="Negative ratio",
    )
    ax1.set_ylim(0, 1)
    ax1.set_ylabel("Pos/Neg ratio")
    ax1.set_xlabel("Month")
    ax1.grid(alpha=0.2, axis="y")

    ax2 = ax1.twinx()
    ax2.plot(x_idx, df["score"], color="#2196f3", marker="o", label="Weighted score")
    ax2.set_ylabel("Sentiment score")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")

    plt.xticks(x_idx, x_labels, rotation=45, ha="right")
    plt.title("Monthly Sentiment Ratios and Score")

    path = os.path.join(output_dir, "visualizations", "sentiment_ratio_score.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def wordcloud_from_topics(topics_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(topics_csv):
        return ""
    df = pd.read_csv(topics_csv)
    if df.empty:
        return ""
    wc_dir = os.path.join(output_dir, "visualizations", "wordclouds")
    os.makedirs(wc_dir, exist_ok=True)
    paths = []
    for window, sub in df.groupby("window"):
        freq = {r["word"]: int(r["freq"]) for _, r in sub.iterrows()}
        if not freq:
            continue
        wc = WordCloud(font_path=_FONT_PATH if _FONT_PATH else None, width=1200, height=600, background_color="white")
        img = wc.generate_from_frequencies(freq)
        p = os.path.join(wc_dir, f"wc_{window}.png")
        img.to_file(p)
        paths.append(p)
    return ";".join(paths)


def main():
    ts_csv = os.environ.get("DZ_SENT_TS", os.path.join("analysis","sentiment_timeseries.csv"))
    topics_csv = os.environ.get("DZ_TOPICS", os.path.join("analysis","topics_by_window.csv"))
    out_dir = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    a = plot_sentiment(ts_csv, out_dir)
    b = wordcloud_from_topics(topics_csv, out_dir)
    c = plot_sentiment_ratios(ts_csv, out_dir)
    d = plot_sentiment_ratio_and_score(ts_csv, out_dir)
    print(a)
    print(b)
    print(c)
    print(d)


if __name__ == "__main__":
    main()
