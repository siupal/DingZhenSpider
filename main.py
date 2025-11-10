from __future__ import annotations
import argparse
import logging
import os

from src.config import load_config, merge_config
from src.crawler import HttpClient, BiliCrawler
from src.storage import persist_all
from src.stats import generate_stats


def build_logger() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
    return logging.getLogger("dzspider")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bilibili 视频采集与统计（popular / ranking）")
    p.add_argument("mode", choices=["popular", "ranking"], help="采集模式")
    p.add_argument("--config", default="config.yaml")

    # popular
    p.add_argument("--pages", type=int, help="popular 页数，例如 10")
    p.add_argument("--ps", type=int, help="popular 每页条数，默认 20")

    # ranking
    p.add_argument("--rid", type=int, help="ranking 分区 0=全站")
    p.add_argument("--day", type=int, choices=[1, 3, 7], help="ranking 天数（部分接口支持）")
    p.add_argument("--rtype", dest="rtype", default="all", help="ranking 类型，默认 all")

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
