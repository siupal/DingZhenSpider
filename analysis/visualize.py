import os
import pandas as pd
import matplotlib.pyplot as plt
from wordcloud import WordCloud


def plot_sentiment(ts_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(ts_csv):
        return ""
    df = pd.read_csv(ts_csv)
    if df.empty:
        return ""
    df = df.sort_values("window")
    fig, ax = plt.subplots(figsize=(10,4))
    ax.plot(df["window"], df["score"], marker="o")
    ax.set_xlabel("window")
    ax.set_ylabel("weighted sentiment")
    ax.set_title("Sentiment over time")
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    path = os.path.join(output_dir, "visualizations", "sentiment_timeseries.png")
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
        wc = WordCloud(font_path=None, width=1200, height=600, background_color="white")
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
    print(a)
    print(b)


if __name__ == "__main__":
    main()
