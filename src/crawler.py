from __future__ import annotations
import time
import random
import logging
from typing import Any, Dict, List, Optional

import requests


class HttpClient:
    def __init__(self, headers: dict, timeout: int = 15, retry: int = 3, backoff: float = 1.5, proxy: str | None = None):
        self.headers = headers or {}
        if "User-Agent" not in self.headers:
            self.headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        if "Referer" not in self.headers:
            self.headers["Referer"] = "https://www.bilibili.com/"
        if "Origin" not in self.headers:
            self.headers["Origin"] = "https://www.bilibili.com"
        # Helpful defaults to mitigate 412
        self.headers.setdefault("Accept", "application/json, text/plain, */*")
        self.headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        self.headers.setdefault("Cache-Control", "no-cache")
        self.timeout = timeout
        self.retry = max(1, retry)
        self.backoff = backoff
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        # Use a persistent session to keep cookies like buvid3/_uuid
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if self.proxies:
            self.session.proxies.update(self.proxies)
        self._warmup()

    def _warmup(self) -> None:
        """Visit homepage and nav to obtain cookies (e.g., buvid3) before WBI calls."""
        try:
            self.session.get("https://www.bilibili.com/", timeout=self.timeout)
        except Exception:
            pass
        try:
            # Also touch nav which WBI signer will need
            self.session.get("https://api.bilibili.com/x/web-interface/nav", timeout=self.timeout)
        except Exception:
            pass

    def get_json(self, url: str, params: dict | None = None) -> dict:
        last_exc: Optional[Exception] = None
        last_status: Optional[int] = None
        last_body_snippet: Optional[str] = None
        for i in range(self.retry):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception as e:
                        last_exc = e
                        time.sleep(self.backoff ** (i + 1) + random.random())
                        continue
                # 常见风控或错误，尝试退避重试
                last_status = resp.status_code
                try:
                    last_body_snippet = resp.text[:300]
                except Exception:
                    last_body_snippet = None
                time.sleep(self.backoff ** (i + 1) + random.random())
            except Exception as e:
                last_exc = e
                time.sleep(self.backoff ** (i + 1) + random.random())
        if last_exc:
            detail = f" last_status={last_status}, last_body_snippet={(last_body_snippet or '')!r}"
            raise RuntimeError(f"GET {url} failed after {self.retry} retries due to {last_exc}.{detail}")
        detail = f" last_status={last_status}, last_body_snippet={(last_body_snippet or '')!r}"
        raise RuntimeError(f"GET {url} failed after {self.retry} retries.{detail}")


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


class WbiSigner:
    """Minimal WBI 签名实现，用于 Web 端搜索等接口。
    参考社区文档：通过 nav 接口获取 wbi_img 的 img_key 与 sub_key，混淆后生成 mixin_key。
    然后对查询参数做字符过滤、按键排序，追加 wts，并以 md5(params_query + mixin_key) 得到 w_rid。
    """

    MIXIN_INDEX = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 52, 44,
    ]

    def __init__(self, http: HttpClient):
        self.http = http
        self._mixin_key: Optional[str] = None

    def _fetch_keys(self) -> tuple[str, str]:
        data = self.http.get_json("https://api.bilibili.com/x/web-interface/nav")
        wbi = (data or {}).get("data", {}).get("wbi_img", {})
        img_url = wbi.get("img_url", "")
        sub_url = wbi.get("sub_url", "")
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        return img_key, sub_key

    @staticmethod
    def _mixin(a: str, b: str) -> str:
        import itertools
        s = a + b
        mix = "".join(s[i] for i in WbiSigner.MIXIN_INDEX)
        return mix[:32]

    @staticmethod
    def _filter_chars(val: str) -> str:
        # 只保留特定字符集，其他字符过滤（与官方 JS 行为一致）
        allowed = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_."
        return "".join(ch for ch in str(val) if ch in allowed)

    def get_mixin_key(self) -> str:
        if not self._mixin_key:
            img_key, sub_key = self._fetch_keys()
            self._mixin_key = self._mixin(img_key, sub_key)
        return self._mixin_key

    def sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        import hashlib
        out = {k: v for k, v in params.items() if v is not None}
        filtered = {k: self._filter_chars(v) for k, v in out.items()}
        wts = int(time.time())
        filtered.update({"wts": wts})
        query = "&".join(f"{k}={filtered[k]}" for k in sorted(filtered.keys()))
        mixin_key = self.get_mixin_key()
        w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
        out.update({"wts": wts, "w_rid": w_rid})
        return out


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

    # ---- Utilities for time filtering and comments ----
    @staticmethod
    def filter_by_pubdate(items: List[Dict[str, Any]], start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
        out = []
        for it in items:
            ts = int(it.get("pubdate") or 0)
            if start_ts <= ts < end_ts:
                out.append(it)
        return out

    def get_aid_by_bvid(self, bvid: str) -> Optional[int]:
        url = "https://api.bilibili.com/x/web-interface/view"
        data = self.http.get_json(url, params={"bvid": bvid})
        aid = (((data or {}).get("data") or {}).get("aid"))
        try:
            return int(aid)
        except Exception:
            return None

    def _shape_comment(self, c: Dict[str, Any]) -> Dict[str, Any]:
        member = c.get("member", {})
        content = c.get("content", {})
        return {
            "rpid": c.get("rpid"),
            "parent": c.get("parent"),
            "floor": c.get("floor"),
            "like": c.get("like"),
            "ctime": c.get("ctime"),
            "uname": member.get("uname"),
            "mid": member.get("mid"),
            "message": content.get("message"),
        }

    def fetch_comments_hot_by_bvid(self, bvid: str, top_n: int = 10) -> Dict[str, Any]:
        """Fetch top hot comments for a video via web comment API without WBI.
        Endpoint: x/v2/reply with sort=2 (hot). Build root comments and their child replies.
        """
        aid = self.get_aid_by_bvid(bvid)
        if not aid:
            return {"bvid": bvid, "aid": None, "replies": []}
        url = "https://api.bilibili.com/x/v2/reply"
        params = {"type": 1, "oid": aid, "sort": 2, "ps": max(10, top_n), "pn": 1}
        data = self.http.get_json(url, params=params)
        root = (data or {}).get("data") or {}
        replies = root.get("replies") or []
        out: List[Dict[str, Any]] = []
        for c in replies[:top_n]:
            shaped = self._shape_comment(c)
            # include first few children to show floor relation
            children = []
            for cc in (c.get("replies") or [])[:10]:
                children.append(self._shape_comment(cc))
            shaped["replies"] = children
            out.append(shaped)
        return {"bvid": bvid, "aid": aid, "replies": out}

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

    def fetch_search_videos(self, keyword: str, pages: int = 4, page_size: int = 50, order: str = "click") -> List[Dict[str, Any]]:
        """使用 Web WBI 搜索接口，按播放量(click)排序，抓取若干页视频结果。
        目标总量 pages*page_size，建议设置为 4*50=200。
        """
        url = "https://api.bilibili.com/x/web-interface/wbi/search/type"
        signer = WbiSigner(self.http)
        results: List[Dict[str, Any]] = []
        for page in range(1, pages + 1):
            base = {
                "search_type": "video",
                "keyword": keyword,
                "order": order,            # click=播放量, pubdate=最新, totalrank=综合
                "page": page,
                "page_size": page_size,
            }
            params = signer.sign(base)
            data = self.http.get_json(url, params=params)
            lst = ((data or {}).get("data") or {}).get("result") or []
            # 搜索结果项字段与 popular/ranking 不同，这里手动映射
            batch: List[Dict[str, Any]] = []
            for x in lst:
                bvid = x.get("bvid") or x.get("bvid_new") or ""
                title = x.get("title") or ""
                # 搜索结果播放量字段通常为 'play'
                view = x.get("play") or 0
                duration = x.get("duration") or x.get("duration_ms") or 0
                pubdate = x.get("pubdate") or 0
                owner = x.get("author") or x.get("uname") or ""
                danmaku = x.get("video_review") or x.get("danmaku") or 0
                like = x.get("like") or 0
                favorite = x.get("favorites") or 0
                coin = x.get("coin") or 0
                share = x.get("share") or 0
                tname = (x.get("typename") or x.get("tname") or "")

                item = {
                    "bvid": bvid,
                    "title": title,
                    "tname": tname,
                    "pubdate": pubdate,
                    "duration": duration,
                    "owner": owner,
                    "view": int(view) if str(view).isdigit() else view,
                    "danmaku": int(danmaku) if str(danmaku).isdigit() else danmaku,
                    "reply": x.get("review") or x.get("reply") or 0,
                    "favorite": favorite,
                    "coin": coin,
                    "share": share,
                    "like": like,
                }
                if item["bvid"]:
                    batch.append(item)
            results.extend(batch)
            self.logger.info(f"search page {page} got {len(batch)} items")
            time.sleep(self.sleep_between)
        return results
