from __future__ import annotations
import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
import csv
from pathlib import Path

# ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, merge_config  # type: ignore
from src.crawler import HttpClient, BiliCrawler  # type: ignore
from src.storage import persist_all, save_json  # type: ignore
from tqdm import tqdm  # type: ignore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run monthly comments collection over a YM range with fallbacks")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--keyword", default="丁真")
    p.add_argument("--from_ym", default="2020-01")
    p.add_argument("--to_ym", default="2025-10")
    p.add_argument("--skip_before_ym", default=None, help="Skip months earlier than this YM (e.g., 2020-11)")
    p.add_argument("--top_videos", type=int, default=10)
    p.add_argument("--top_comments", type=int, default=20)
    p.add_argument("--pages", type=int, default=8)
    p.add_argument("--page_size", type=int, default=50)
    p.add_argument("--orders", nargs="+", default=["click", "totalrank", "pubdate"])
    p.add_argument("--sleep_sec", type=float, default=4.0)
    # http
    p.add_argument("--timeout", type=int)
    p.add_argument("--retry", type=int)
    p.add_argument("--backoff", type=float)
    p.add_argument("--proxy")
    # output
    p.add_argument("--output_dir")
    return p.parse_args()


def ym_iter(from_ym: str, to_ym: str):
    s_y, s_m = map(int, from_ym.split("-"))
    e_y, e_m = map(int, to_ym.split("-"))
    y, m = s_y, s_m
    while (y < e_y) or (y == e_y and m <= e_m):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def month_task(
    crawler: BiliCrawler,
    keyword: str,
    year: int,
    month: int,
    pages: int,
    page_size: int,
    order: str,
    top_v: int,
    top_c: int,
    output_dir: str,
) -> str:
    # 月份时间范围（东八区）
    tz8 = timezone(timedelta(hours=8))
    start_dt = datetime(int(year), int(month), 1, 0, 0, 0, tzinfo=tz8)
    if int(month) == 12:
        end_dt = datetime(int(year) + 1, 1, 1, 0, 0, 0, tzinfo=tz8)
    else:
        end_dt = datetime(int(year), int(month) + 1, 1, 0, 0, 0, tzinfo=tz8)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # 搜索+按月过滤（页级进度）
    pbar_pages = tqdm(total=pages, desc=f"Search {year}-{int(month):02d} ({order})", leave=False)
    def _on_page(pg, got):
        pbar_pages.set_postfix({"pg": pg, "got": got})
        pbar_pages.update(1)
    items_all = crawler.fetch_search_videos(keyword=keyword, pages=pages, page_size=page_size, order=order, on_page=_on_page)
    pbar_pages.close()
    items_month = BiliCrawler.filter_by_pubdate(items_all, start_ts, end_ts)
    items_month_sorted = sorted(items_month, key=lambda x: int(x.get("view") or 0), reverse=True)
    picked = items_month_sorted[:top_v]

    # 输出名
    safe_kw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5_]+", "_", keyword)
    basename = f"comments_{safe_kw}_{year}{int(month):02d}"
    json_path = os.path.join(output_dir, f"{basename}.json")
    err_csv_path = os.path.join(output_dir, f"{basename}_errors.csv")

    # 热评抓取（视频级进度）
    comments_payload = []
    pbar_vids = tqdm(total=len(picked), desc=f"Comments {year}-{int(month):02d}", leave=False)
    for it in picked:
        bvid = it.get("bvid")
        try:
            cm = crawler.fetch_comments_hot_by_bvid(bvid=bvid, top_n=top_c)
        except Exception as e:
            cm = {"bvid": bvid, "error": str(e), "replies": []}
        comments_payload.append({"video": it, "comments": cm})
        pbar_vids.set_postfix({"bvid": bvid})
        pbar_vids.update(1)
    pbar_vids.close()

    # 写出本月错误明细（如：UP主已关闭评论区）
    try:
        err_rows = []
        for it in (comments_payload or []):
            cm = (it or {}).get("comments") or {}
            if cm and not (cm.get("replies") or []) and (cm.get("error_code") is not None or cm.get("error_msg")):
                err_rows.append({
                    "bvid": cm.get("bvid") or (it.get("video") or {}).get("bvid"),
                    "error_code": cm.get("error_code"),
                    "error_msg": cm.get("error_msg") or "",
                })
        if err_rows:
            with open(err_csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["bvid","error_code","error_msg"])
                w.writeheader()
                w.writerows(err_rows)
    except Exception:
        pass

    # 如果已存在旧文件且更“丰富”，避免被较差结果覆盖
    def _score(payload):
        try:
            return sum(len(((it or {}).get("comments") or {}).get("replies") or []) for it in (payload or []))
        except Exception:
            return 0
    if os.path.exists(json_path):
        try:
            import json as _json
            with open(json_path, "r", encoding="utf-8") as _f:
                old_payload = _json.load(_f)
            if _score(old_payload) >= _score(comments_payload):
                return json_path
        except Exception:
            pass
    save_json(comments_payload, json_path)
    persist_all(picked, output_dir=output_dir, basename=basename)
    try:
        total_replies = sum(len(((it or {}).get("comments") or {}).get("replies") or []) for it in (comments_payload or []))
        print(f"[Monthly] {year}-{int(month):02d} picked={len(picked)} total_replies={total_replies} -> {json_path}")
    except Exception:
        pass
    return json_path


def main():
    args = parse_args()
    base_cfg = load_config(args.config)
    override = {
        "http": {
            "timeout": args.timeout,
            "retry": args.retry,
            "backoff": args.backoff,
            "proxy": args.proxy,
        },
        "output_dir": args.output_dir,
    }
    cfg = merge_config(base_cfg, override)

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

    months = list(ym_iter(args.from_ym, args.to_ym))
    # parse exemption boundary
    skip_y = skip_m = None
    if args.skip_before_ym:
        try:
            skip_y, skip_m = map(int, str(args.skip_before_ym).split("-"))
        except Exception:
            skip_y = skip_m = None
    with tqdm(total=len(months), desc="Monthly comments", unit="month") as pbar:
        for y, m in months:
            if skip_y and skip_m and ((y < skip_y) or (y == skip_y and m < skip_m)):
                print(f"[Skip] {y}-{int(m):02d} (before exemption {skip_y}-{int(skip_m):02d})")
                pbar.update(1)
                continue
            # 依次尝试 orders；若生成的 JSON 文件体积 > 4KB 视作有效
            for ord_ in args.orders:
                pbar.set_postfix({"month": f"{y}-{int(m):02d}", "order": ord_})
                try:
                    path = month_task(
                        crawler=crawler,
                        keyword=args.keyword,
                        year=y,
                        month=m,
                        pages=int(args.pages),
                        page_size=int(args.page_size),
                        order=ord_,
                        top_v=int(args.top_videos),
                        top_c=int(args.top_comments),
                        output_dir=output_dir,
                    )
                except Exception:
                    time.sleep(args.sleep_sec)
                    continue
                if os.path.exists(path):
                    ok = False
                    try:
                        # 更宽松的体积阈值，兼容“数据确实稀少”的月份
                        if os.path.getsize(path) >= 512:
                            ok = True
                        else:
                            import json
                            with open(path, "r", encoding="utf-8") as f:
                                payload = json.load(f)
                            # 若存在任意非空评论，或至少有选中的视频项，也视作有效结果
                            for it in (payload or []):
                                cm = (it or {}).get("comments") or {}
                                reps = cm.get("replies") or []
                                if reps:
                                    ok = True
                                    break
                            if not ok and len(payload or []) > 0:
                                ok = True
                    except Exception:
                        ok = False
                    if ok:
                        break
                time.sleep(args.sleep_sec)
            time.sleep(args.sleep_sec)
            pbar.update(1)


if __name__ == "__main__":
    main()
