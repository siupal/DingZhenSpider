from __future__ import annotations
import argparse
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta

from src.config import load_config, merge_config
from src.crawler import HttpClient, BiliCrawler
from src.storage import persist_all, save_json
from src.stats import generate_stats


def build_logger() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
    return logging.getLogger("dzspider")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bilibili 视频采集与统计（popular / ranking / search / comments）")
    p.add_argument("mode", choices=["popular", "ranking", "search", "comments"], help="采集模式")
    p.add_argument("--config", default="config.yaml")

    # popular
    p.add_argument("--pages", type=int, help="popular 页数，例如 10")
    p.add_argument("--ps", type=int, help="popular 每页条数，默认 20")

    # ranking
    p.add_argument("--rid", type=int, help="ranking 分区 0=全站")
    p.add_argument("--day", type=int, choices=[1, 3, 7], help="ranking 天数（部分接口支持）")
    p.add_argument("--rtype", dest="rtype", default="all", help="ranking 类型，默认 all")

    # search
    p.add_argument("--keyword", help="搜索关键词")
    p.add_argument("--order", default="click", help="排序方式：click(播放量)/pubdate/totalrank 等，默认 click")
    p.add_argument("--page_size", type=int, help="搜索每页条数（默认 50）")
    # comments task
    p.add_argument("--year", type=int, help="筛选年份，例如 2024")
    p.add_argument("--month", type=int, help="筛选月份 1-12，例如 7")
    p.add_argument("--top_videos", type=int, help="选取播放量TopN视频，默认 3")
    p.add_argument("--top_comments", type=int, help="每个视频热门评论TopK，默认 10")

    # http
    p.add_argument("--timeout", type=int)
    p.add_argument("--retry", type=int)
    p.add_argument("--backoff", type=float)
    p.add_argument("--proxy")

    # output
    p.add_argument("--output_dir")
    return p.parse_args()


def main():
    logger = build_logger()
    args = parse_args()

    base_cfg = load_config(args.config)
    override = {
        "mode": args.mode,
        "popular": {"pages": args.pages, "ps": args.ps},
        "ranking": {"rid": args.rid, "day": args.day, "type": getattr(args, "rtype", None)},
        "search": {"keyword": getattr(args, "keyword", None), "pages": args.pages, "page_size": args.page_size, "order": getattr(args, "order", None)},
        "comments": {"keyword": getattr(args, "keyword", None), "pages": args.pages, "page_size": args.page_size, "order": getattr(args, "order", None), "year": args.year, "month": args.month, "top_videos": args.top_videos, "top_comments": args.top_comments},
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
    crawler = BiliCrawler(client, logger=logger)

    mode = cfg.get("mode")
    items = []
    if mode == "popular":
        pop = cfg.get("popular", {})
        pages = int(pop.get("pages", 10))
        ps = int(pop.get("ps", 20))
        logger.info(f"Start fetching popular: pages={pages}, ps={ps}")
        items = crawler.fetch_popular(pages=pages, ps=ps)
        basename = "popular"
    elif mode == "ranking":
        r = cfg.get("ranking", {})
        rid = int(r.get("rid", 0))
        day = int(r.get("day", 3))
        rtype = r.get("type", "all")
        logger.info(f"Start fetching ranking: rid={rid}, day={day}, type={rtype}")
        items = crawler.fetch_ranking(rid=rid, day=day, type_=rtype)
        basename = f"ranking_rid{rid}"
    elif mode == "search":
        s = cfg.get("search", {})
        kw = s.get("keyword") or ""
        if not kw:
            raise SystemExit("--keyword 不能为空")
        pages = int(s.get("pages", 4))
        page_size = int(s.get("page_size", 50))
        order = s.get("order", "click")
        logger.info(f"Start searching: keyword='{kw}', pages={pages}, page_size={page_size}, order={order}")
        items = crawler.fetch_search_videos(keyword=kw, pages=pages, page_size=page_size, order=order)
        safe_kw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5_]+", "_", kw)
        basename = f"search_{safe_kw}"
    elif mode == "comments":
        s = cfg.get("comments", {})
        kw = s.get("keyword") or ""
        year = s.get("year")
        month = s.get("month")
        if not kw or not year or not month:
            raise SystemExit("comments 模式需要 --keyword, --year, --month 三个参数")
        pages = int(s.get("pages", 6))  # 拉多一点，避免漏掉符合月份的高播放视频
        page_size = int(s.get("page_size", 50))
        order = s.get("order", "click")
        top_v = int(s.get("top_videos", 3))
        top_c = int(s.get("top_comments", 10))

        logger.info(f"Task comments: keyword='{kw}', y-m={year}-{month:02d}, pages={pages}*{page_size}, order={order}, top_videos={top_v}, top_comments={top_c}")

        # 计算该月的起止时间（东八区）
        tz8 = timezone(timedelta(hours=8))
        start_dt = datetime(int(year), int(month), 1, 0, 0, 0, tzinfo=tz8)
        if int(month) == 12:
            end_dt = datetime(int(year) + 1, 1, 1, 0, 0, 0, tzinfo=tz8)
        else:
            end_dt = datetime(int(year), int(month) + 1, 1, 0, 0, 0, tzinfo=tz8)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # 搜索并筛选该月视频
        items_all = crawler.fetch_search_videos(keyword=kw, pages=pages, page_size=page_size, order=order)
        items_month = BiliCrawler.filter_by_pubdate(items_all, start_ts, end_ts)
        # 选取播放量TopN
        items_month_sorted = sorted(items_month, key=lambda x: int(x.get("view") or 0), reverse=True)
        picked = items_month_sorted[:top_v]
        logger.info(f"Picked {len(picked)} videos for comments")

        # 拉取每个视频的热门评论TopK
        comments_payload = []
        for it in picked:
            bvid = it.get("bvid")
            try:
                cm = crawler.fetch_comments_hot_by_bvid(bvid=bvid, top_n=top_c)
            except Exception as e:
                logger.warning(f"comments fetch failed for {bvid}: {e}")
                cm = {"bvid": bvid, "error": str(e), "replies": []}
            comments_payload.append({
                "video": it,
                "comments": cm,
            })

        safe_kw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5_]+", "_", kw)
        basename = f"comments_{safe_kw}_{year}{int(month):02d}"
        json_path = os.path.join(output_dir, f"{basename}.json")
        save_json(comments_payload, json_path)
        # 同时保存被选中的视频列表（CSV/DB）
        paths = persist_all(picked, output_dir=output_dir, basename=basename)
        logger.info(f"Saved comments JSON: {json_path}; videos: {paths}")
        return
    else:
        raise SystemExit("Unknown mode")

    if not items:
        logger.warning("No items fetched.")
    paths = persist_all(items, output_dir=output_dir, basename=basename)
    logger.info(f"Saved to: {paths}")

    stat_paths = generate_stats(paths["csv"], output_dir)
    if stat_paths:
        logger.info(f"Generated stats: {stat_paths}")


if __name__ == "__main__":
    main()
