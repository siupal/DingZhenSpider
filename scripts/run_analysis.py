import argparse
import os
import sys
from pathlib import Path

# ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.preprocess import load_and_clean
from analysis.sentiment_baseline import run as run_sent
from analysis.topics_baseline import run as run_topics
from analysis.visualize import plot_sentiment, wordcloud_from_topics


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", default="data")
    p.add_argument("--analysis_dir", default="analysis")
    return p.parse_args()


def main():
    args = parse_args()
    cleaned_csv = load_and_clean(args.data_dir, os.path.join(args.analysis_dir, "cleaned"))
    sent_csv = run_sent(cleaned_csv, args.analysis_dir)
    topics_csv = run_topics(cleaned_csv, args.analysis_dir)
    plot_sentiment(sent_csv, args.analysis_dir)
    wordcloud_from_topics(topics_csv, args.analysis_dir)


if __name__ == "__main__":
    main()
