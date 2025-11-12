import argparse
import os
import random
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

# ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, merge_config  # type: ignore
from src.crawler import HttpClient, BiliCrawler  # type: ignore
from scripts.run_monthly_comments import ym_iter, month_task  # type: ignore


def parse_list_arg(val: Optional[str]) -> List[str]:
    if not val:
        return []
    # allow comma-separated inline list
    if "," in val and os.path.exists(val) is False:
        return [s.strip() for s in val.split(",") if s.strip()]
    # or a file path with one per line
    if os.path.exists(val):
        with open(val, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    return []


essay = """
Resilient monthly collector
- Randomize month order
- Rotate proxies and Cookies between attempts
- Backoff-and-retry when results look wind-controlled (empty search/comments)
- Write through to the same data files as month_task
- No refactor of existing modules
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Resilient monthly collector with rotation and backoff")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--keyword", required=True)
    p.add_argument("--from_ym", required=True)
    p.add_argument("--to_ym", required=True)
    p.add_argument("--orders", nargs="+", default=["click"])  # keep single order for efficiency
    p.add_argument("--pages", type=int, default=4)
    p.add_argument("--page_size", type=int, default=50)
    p.add_argument("--top_videos", type=int, default=10)
    p.add_argument("--top_comments", type=int, default=30)
    p.add_argument("--output_dir", default="data")
    # resilience
    p.add_argument("--proxies", help="comma-separated proxies or a file path with one per line")
    p.add_argument("--cookies", help="a file path with one Cookie header string per line, or a single inline 'k=v; ...' string")
    p.add_argument("--user_agents", help="comma-separated UAs or a file path with one per line")
    p.add_argument("--max_retries_per_month", type=int, default=4)
    p.add_argument("--initial_sleep", type=float, default=6.0)
    p.add_argument("--sleep_cap", type=float, default=900.0)  # 15 min
    p.add_argument("--jitter", type=float, default=0.3)
    p.add_argument("--shuffle_months", action="store_true", default=True)
    p.add_argument("--checkpoint", default=os.path.join("analysis", "resilient_checkpoint.json"))
    p.add_argument("--attempt_log", default=os.path.join("analysis", "resilient_attempts.csv"))
    return p.parse_args()


def semantic_ok(path: str) -> bool:
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) >= 1024:
        return True
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        # any non-empty replies or any picked items means ok
        for it in (payload or []):
            cm = (it or {}).get("comments") or {}
            reps = cm.get("replies") or []
            if reps:
                return True
        if len(payload or []) > 0:
            return True
    except Exception:
        return False
    return False


def build_client(cfg: dict, cookie_header: Optional[str], proxy: Optional[str], user_agent: Optional[str]) -> BiliCrawler:
    http_cfg = cfg.get("http", {}) or {}
    headers = (cfg.get("headers") or {}).copy()
    if cookie_header:
        headers["Cookie"] = cookie_header
    if user_agent:
        headers["User-Agent"] = user_agent
    client = HttpClient(
        headers=headers,
        timeout=int(http_cfg.get("timeout", 15)),
        retry=int(http_cfg.get("retry", 3)),
        backoff=float(http_cfg.get("backoff", 1.5)),
        proxy=proxy or http_cfg.get("proxy") or None,
    )
    return BiliCrawler(client)


def load_checkpoint(path: str) -> Dict[str, Any]:
    try:
        import json
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {"ok": [], "giveup": []}


def save_checkpoint(path: str, data: Dict[str, Any]) -> None:
    try:
        import json
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def append_attempt_log(path: str, row: Dict[str, Any]) -> None:
    import csv
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = [
        "ts","ym","attempt","order","proxy","cookie_idx","ua_idx","result","message","output_path"
    ]
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow(row)


def main():
    args = parse_args()
    base_cfg = load_config(args.config)
    cfg = merge_config(base_cfg, {"output_dir": args.output_dir})
    os.makedirs(args.output_dir, exist_ok=True)

    # prepare rotation pools
    proxies = parse_list_arg(args.proxies)
    cookies_pool: List[str] = []
    if args.cookies:
        if os.path.exists(args.cookies):
            with open(args.cookies, "r", encoding="utf-8") as f:
                cookies_pool = [ln.strip() for ln in f if ln.strip()]
        else:
            cookies_pool = [args.cookies.strip()]
    uas_pool: List[str] = parse_list_arg(args.user_agents)

    months = list(ym_iter(args.from_ym, args.to_ym))
    if args.shuffle_months:
        random.shuffle(months)

    proxy_idx = 0
    cookie_idx = 0
    ua_idx = 0

    ckpt = load_checkpoint(args.checkpoint)

    for (y, m) in months:
        # attempt loop per month
        backoff = max(1.0, float(args.initial_sleep))
        attempt = 0
        last_path = ""
        ym = f"{int(y)}{int(m):02d}"
        # skip if checkpoint says ok and file still semantically ok
        if ym in (ckpt.get("ok") or []) and semantic_ok(os.path.join(args.output_dir, f"comments_{args.keyword}_{ym}.json")):
            print(f"[Skip-OK] {y}-{int(m):02d} already good in checkpoint")
            continue
        while attempt <= int(args.max_retries_per_month):
            proxy = proxies[proxy_idx % len(proxies)] if proxies else None
            cookie_header = cookies_pool[cookie_idx % len(cookies_pool)] if cookies_pool else None
            ua = uas_pool[ua_idx % len(uas_pool)] if uas_pool else None
            crawler = build_client(cfg, cookie_header, proxy, ua)
            # randomize order choice across attempts if multiple provided
            order = random.choice(args.orders) if args.orders else "click"
            try:
                last_path = month_task(
                    crawler=crawler,
                    keyword=args.keyword,
                    year=int(y),
                    month=int(m),
                    pages=int(args.pages),
                    page_size=int(args.page_size),
                    order=order,
                    top_v=int(args.top_videos),
                    top_c=int(args.top_comments),
                    output_dir=args.output_dir,
                )
            except Exception as e:
                # rotate and backoff then retry
                attempt += 1
                # 优先轮换代理，其次 Cookie，再换 UA
                proxy_idx += 1
                if attempt % 2 == 0:
                    cookie_idx += 1
                if attempt % 3 == 0:
                    ua_idx += 1
                sleep_s = min(args.sleep_cap, backoff * (1.5 + random.random()) )
                msg = f"exception: {e}"
                print(f"[Retry] {y}-{int(m):02d} attempt={attempt} {msg}. rotate and sleep {sleep_s:.1f}s")
                append_attempt_log(args.attempt_log, {
                    "ts": int(time.time()),
                    "ym": ym,
                    "attempt": attempt,
                    "order": order,
                    "proxy": proxy or "",
                    "cookie_idx": cookie_idx,
                    "ua_idx": ua_idx,
                    "result": "exception",
                    "message": msg,
                    "output_path": last_path,
                })
                time.sleep(sleep_s)
                backoff *= (1.8 + random.random() * args.jitter)
                continue

            if semantic_ok(last_path):
                print(f"[OK] {y}-{int(m):02d} saved -> {last_path}")
                append_attempt_log(args.attempt_log, {
                    "ts": int(time.time()),
                    "ym": ym,
                    "attempt": attempt,
                    "order": order,
                    "proxy": proxy or "",
                    "cookie_idx": cookie_idx,
                    "ua_idx": ua_idx,
                    "result": "ok",
                    "message": "",
                    "output_path": last_path,
                })
                ok_list = set(ckpt.get("ok") or [])
                ok_list.add(ym)
                ckpt["ok"] = sorted(ok_list)
                save_checkpoint(args.checkpoint, ckpt)
                # small random jitter between months to be less predictable
                time.sleep(max(1.0, args.initial_sleep * (0.4 + random.random())))
                break

            # not ok -> likely wind control or sparse data; rotate and retry
            attempt += 1
            # 轮换策略：先换代理；部分尝试换 Cookie；偶尔换 UA
            proxy_idx += 1
            if attempt % 2 == 1:
                cookie_idx += 1
            if attempt % 3 == 1:
                ua_idx += 1
            sleep_s = min(args.sleep_cap, backoff * (1.5 + random.random()))
            print(f"[WindCtrl?] {y}-{int(m):02d} empty/weak result. rotate proxy/cookie and sleep {sleep_s:.1f}s")
            append_attempt_log(args.attempt_log, {
                "ts": int(time.time()),
                "ym": ym,
                "attempt": attempt,
                "order": order,
                "proxy": proxy or "",
                "cookie_idx": cookie_idx,
                "ua_idx": ua_idx,
                "result": "empty",
                "message": "",
                "output_path": last_path,
            })
            time.sleep(sleep_s)
            backoff *= (1.8 + random.random() * args.jitter)
        else:
            # attempts exhausted
            print(f"[GiveUp] {y}-{int(m):02d} after {args.max_retries_per_month} retries -> {last_path}")
            append_attempt_log(args.attempt_log, {
                "ts": int(time.time()),
                "ym": ym,
                "attempt": attempt,
                "order": "",
                "proxy": "",
                "cookie_idx": cookie_idx,
                "ua_idx": ua_idx,
                "result": "giveup",
                "message": "",
                "output_path": last_path,
            })
            giveup_list = set(ckpt.get("giveup") or [])
            giveup_list.add(ym)
            ckpt["giveup"] = sorted(giveup_list)
            save_checkpoint(args.checkpoint, ckpt)


if __name__ == "__main__":
    main()
