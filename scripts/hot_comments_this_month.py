from __future__ import annotations
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any

# ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, merge_config  # type: ignore
from src.crawler import HttpClient, BiliCrawler  # type: ignore
from src.storage import persist_all, save_json  # type: ignore


def pick_top_this_month(crawler: BiliCrawler, pages: int = 10, ps: int = 20) -> List[Dict[str, Any]]:
    tz8 = timezone(timedelta(hours=8))
    now = datetime.now(tz8)
    y, m = now.year-10, now.month
    start_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=tz8)
    if m == 12:
        end_dt = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=tz8)
    else:
        end_dt = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=tz8)
    start_ts, end_ts = int(start_dt.timestamp()), int(end_dt.timestamp())

    # 用 popular 拉取若干页近期热门（当前月会较多出现）
    items = crawler.fetch_popular(pages=pages, ps=ps)
    month_items = BiliCrawler.filter_by_pubdate(items, start_ts, end_ts)
    month_items_sorted = sorted(month_items, key=lambda x: int(x.get("view") or 0), reverse=True)
    return month_items_sorted[:10]


def main():
    base_cfg = load_config("config.yaml")
    cfg = merge_config(base_cfg, {})

    output_dir = cfg.get("output_dir") or "data"
    os.makedirs(output_dir, exist_ok=True)

    http_cfg = cfg.get("http", {})
    headers = (cfg.get("headers") or {})
    client = HttpClient(
        headers=headers,
        timeout=int(http_cfg.get("timeout", 15)),
        retry=int(http_cfg.get("retry", 3)),
        backoff=float(http_cfg.get("backoff", 1.5)),
        proxy=http_cfg.get("proxy") or None,
    )
    crawler = BiliCrawler(client)

    tz8 = timezone(timedelta(hours=8))
    now = datetime.now(tz8)
    y, m = now.year, now.month
    ym = f"{y}{m:02d}"

    top_videos = pick_top_this_month(crawler, pages=10, ps=20)

    # 抓取每个视频的 Top5 热门评论
    payload = []
    for it in top_videos:
        bvid = it.get("bvid")
        try:
            cm = crawler.fetch_comments_hot_by_bvid(bvid=bvid, top_n=5)
        except Exception as e:
            cm = {"bvid": bvid, "error": str(e), "replies": []}
        payload.append({"video": it, "comments": cm})

    # 保存
    basename = f"hot_{ym}"
    save_json(payload, os.path.join(output_dir, f"{basename}.json"))
    persist_all(top_videos, output_dir=output_dir, basename=basename)
    print(f"Saved: {os.path.join(output_dir, f'{basename}.json')} and CSV/SQLite for top videos")


if __name__ == "__main__":
    main()
