from __future__ import annotations
import time
import random
import logging
from typing import Any, Dict, List, Optional

import requests


class HttpClient:
    def __init__(self, headers: dict, timeout: int = 15, retry: int = 3, backoff: float = 1.5, proxy: str | None = None):
        self.headers = headers or {}
        self.timeout = timeout
        self.retry = max(1, retry)
        self.backoff = backoff
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    def get_json(self, url: str, params: dict | None = None) -> dict:
        last_exc: Optional[Exception] = None
        for i in range(self.retry):
            try:
                resp = requests.get(url, params=params, headers=self.headers, timeout=self.timeout, proxies=self.proxies)
                if resp.status_code == 200:
                    return resp.json()
                # 常见风控或错误，尝试退避重试
                time.sleep(self.backoff ** (i + 1) + random.random())
            except Exception as e:
                last_exc = e
                time.sleep(self.backoff ** (i + 1) + random.random())
        if last_exc:
            raise last_exc
        raise RuntimeError(f"GET {url} failed after {self.retry} retries")


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    # 兼容 popular 与 ranking 两种不同结构
    # popular: data.list[]  ranking: data.list[] or data.ranking_list[]
    # 尝试从不同层级提取相同字段
    def g(path: List[str], default=None):
        cur = item
        for p in path:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return cur

    # 对 ranking 可能数据在 'archive' 字段
    base = item.get("archive") if isinstance(item.get("archive"), dict) else item

    owner = g(["owner", "name"]) or g(["author"]) or g(["owner", "mid"])  # ranking 可能为 author
    bvid = base.get("bvid") or g(["bvid"]) or g(["short_link_v2"]) or ""
    title = base.get("title") or g(["title"]) or ""
    tname = base.get("tname") or g(["tname"]) or ""
    pubdate = base.get("pubdate") or g(["pubdate"]) or 0
    duration = base.get("duration") or g(["duration"]) or 0
    stat = base.get("stat") or g(["stat"]) or {}

    view = stat.get("view") or stat.get("play") or g(["play"], 0) or 0
    danmaku = stat.get("danmaku") or g(["danmaku"], 0) or 0
    reply = stat.get("reply") or g(["reply"], 0) or 0
    favorite = stat.get("favorite") or g(["favorite"], 0) or 0
    coin = stat.get("coin") or g(["coin"], 0) or 0
    share = stat.get("share") or g(["share"], 0) or 0
    like = stat.get("like") or g(["like"], 0) or 0

    return {
        "bvid": bvid,
        "title": title,
        "tname": tname,
        "pubdate": pubdate,
        "duration": duration,
        "owner": owner,
        "view": view,
        "danmaku": danmaku,
        "reply": reply,
        "favorite": favorite,
        "coin": coin,
        "share": share,
        "like": like,
    }


class BiliCrawler:
    def __init__(self, http: HttpClient, logger: Optional[logging.Logger] = None, sleep_between: float = 0.8):
        self.http = http
        self.logger = logger or logging.getLogger(__name__)
        self.sleep_between = sleep_between

    def fetch_popular(self, pages: int = 10, ps: int = 20) -> List[Dict[str, Any]]:
        url = "https://api.bilibili.com/x/web-interface/popular"
        results: List[Dict[str, Any]] = []
        for pn in range(1, pages + 1):
            params = {"ps": ps, "pn": pn}
            data = self.http.get_json(url, params=params)
            lst = ((data or {}).get("data") or {}).get("list") or []
            batch = [normalize_item(x) for x in lst]
            results.extend(batch)
            self.logger.info(f"popular page {pn} got {len(batch)} items")
            time.sleep(self.sleep_between)
        return results

    def fetch_ranking(self, rid: int = 0, day: int = 3, type_: str = "all") -> List[Dict[str, Any]]:
        # ranking v2 接口（不同分区/时段），不分页
        url = "https://api.bilibili.com/x/web-interface/ranking/v2"
        params = {"rid": rid, "type": type_}
        data = self.http.get_json(url, params=params)
        lst = ((data or {}).get("data") or {}).get("list") or []
        batch = [normalize_item(x) for x in lst]
        self.logger.info(f"ranking rid={rid} type={type_} got {len(batch)} items")
        # 旧接口按 day 提供榜单；若需要 day 细分，可在扩展时切换到旧版或其他端点
        return batch
