"""抖音网页端 API 封装(经浏览器登录会话 XHR 同步调用)。

比 DOM 解析稳定: 抖音 DOM 类名频繁变更, API 结构相对稳定。
"""
import json
import time
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode

_AID = 6383
_User = Dict[str, Any]


def _call(tab, path: str, params: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    """同步 XHR 调用抖音 API, 失败自动重试。

    Args:
        tab: ChromiumPage 的标签页(须在 douyin.com 域下执行)。
        path: API 路径, 如 /aweme/v1/web/aweme/post/。
        params: URL 查询参数。
        retries: 最大重试次数。

    Returns:
        解析后的 JSON dict; 全部失败时返回空 dict。
    """
    query = path + "?" + urlencode(params)
    for _ in range(retries):
        raw = tab.run_js("""
        var xhr = new XMLHttpRequest();
        xhr.open('GET', %s, false);
        xhr.withCredentials = true;
        try { xhr.send(null); } catch(e) { return JSON.stringify({err: String(e)}); }
        if (xhr.status !== 200) return JSON.stringify({http: xhr.status});
        return xhr.responseText;
        """ % json.dumps(query))
        try:
            return json.loads(raw)
        except Exception:
            time.sleep(3)
    return {}


def _common(sec_uid: str) -> Dict[str, Any]:
    """公共查询参数。"""
    return {"device_platform": "webapp", "aid": _AID,
            "channel": "channel_pc_web", "sec_user_id": sec_uid}


def post_list(tab, sec_uid: str, cursor: int = 0,
              count: int = 35) -> Tuple[List[Dict[str, Any]], bool, int]:
    """作品列表, 分页游标 max_cursor。

    Returns:
        (作品条目列表, 是否还有更多, 下一页游标)。
    """
    p = _common(sec_uid)
    p.update({"max_cursor": cursor, "count": count,
              "publish_video_strategy_type": 2})
    j = _call(tab, "/aweme/v1/web/aweme/post/", p)
    items = [{"id": a.get("aweme_id"), "create_time": a.get("create_time"),
              "title": a.get("desc", "")} for a in (j.get("aweme_list") or [])]
    return items, bool(j.get("has_more")), j.get("max_cursor") or 0


def comment_list(tab, aweme_id: str, cursor: int = 0,
                 count: int = 20) -> Tuple[List[Dict[str, Any]], bool, int]:
    """视频评论列表, 分页游标 cursor。"""
    p = _common("")
    p.update({"aweme_id": aweme_id, "cursor": cursor,
              "count": count, "item_type": 0})
    j = _call(tab, "/aweme/v1/web/comment/list/", p)
    return j.get("comments") or [], bool(j.get("has_more")), j.get("cursor") or 0


def reply_list(tab, aweme_id: str, comment_id: str, cursor: int = 0,
               count: int = 20) -> Tuple[List[Dict[str, Any]], bool, int]:
    """评论回复列表, 分页游标 cursor。"""
    p = _common("")
    p.update({"item_id": aweme_id, "comment_id": comment_id,
              "cursor": cursor, "count": count})
    j = _call(tab, "/aweme/v1/web/comment/list/reply/", p)
    return j.get("comments") or [], bool(j.get("has_more")), j.get("cursor") or 0


def user_list(tab, sec_uid: str, kind: str = "follower", cursor: int = 0,
              count: int = 20) -> Tuple[List[_User], bool, int]:
    """粉丝/关注列表。

    注意: 请求发 max_time(=上页游标), 下一页游标取响应里的 min_time;
    若拿响应的 max_time 当下一页游标, 每页约 80% 重复。

    Args:
        kind: follower(粉丝) 或 following(关注)。

    Returns:
        (用户条目列表, 是否还有更多, 下一页游标)。
    """
    path = f"/aweme/v1/web/user/{kind}/list/"
    p = _common(sec_uid)
    p.update({"count": count, "source_type": 1, "max_time": cursor})
    j = _call(tab, path, p)
    arr = j.get("followers") if kind == "follower" else j.get("followings")
    return arr or [], bool(j.get("has_more")), j.get("min_time") or 0
