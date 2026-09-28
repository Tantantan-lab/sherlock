"""采集器: 作品/评论/回复/粉丝/关注 → data/data.json(统一 JSON 落盘)。

全部经 API 分页拉取(见 sherlock.api), 自带 sec_uid 去重。
"""
import datetime
import os
import sys
import time
from typing import Any, Dict, List

from sherlock import api
from sherlock.headless import new_page

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_INTERVAL = 1.0


def collect_videos(tab, sec_uid: str) -> List[Dict[str, Any]]:
    """拉取目标账号全部作品(含发布时间, 用于时间线重建)。"""
    out = []
    cursor = 0
    for _ in range(100):
        items, has_more, cursor = api.post_list(tab, sec_uid, cursor)
        out.extend(items)
        if not has_more:
            break
        time.sleep(_INTERVAL)
    return out


def collect_comments(tab, aweme_ids: List[str]) -> List[Dict[str, Any]]:
    """批量拉取视频评论(昵称/属地/点赞/回复数/时间戳)。"""
    rows = []
    for vid in aweme_ids:
        cursor = 0
        for _ in range(500):
            comments, has_more, cursor = api.comment_list(tab, vid, cursor)
            for c in comments:
                user = c.get("user") or {}
                rows.append({
                    "video_id": vid,
                    "comment_id": c.get("cid", ""),
                    "nickname": user.get("nickname", ""),
                    "sec_uid": user.get("sec_uid", ""),
                    "douyin_id": user.get("short_id", ""),
                    "comment_text": c.get("text", ""),
                    "created_at": datetime.datetime.fromtimestamp(
                        c.get("create_time", 0)).strftime("%Y-%m-%d %H:%M"),
                    "ip_label": c.get("ip_label", ""),
                    "digg_count": c.get("digg_count", 0),
                    "reply_count": c.get("reply_comment_total", 0),
                })
            if not has_more:
                break
            time.sleep(_INTERVAL)
    return rows


def collect_replies(tab, comment_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """只对回复数>0 的主评论拉回复链(用户→用户互动边)。"""
    edges = []
    for r in comment_rows:
        if int(r["reply_count"] or 0) <= 0:
            continue
        cursor = 0
        for _ in range(50):
            comments, has_more, cursor = api.reply_list(
                tab, r["video_id"], r["comment_id"], cursor)
            for c in comments:
                user = c.get("user") or {}
                edges.append({
                    "video_id": r["video_id"],
                    "main_comment_id": r["comment_id"],
                    "reply_id": c.get("cid", ""),
                    "reply_nickname": user.get("nickname", ""),
                    "reply_sec_uid": user.get("sec_uid", ""),
                    "reply_to": c.get("reply_to_username", ""),
                    "reply_text": c.get("text", ""),
                    "created_at": datetime.datetime.fromtimestamp(
                        c.get("create_time", 0)).strftime("%Y-%m-%d %H:%M"),
                    "ip_label": c.get("ip_label", ""),
                    "digg_count": c.get("digg_count", 0),
                })
            if not has_more:
                break
            time.sleep(_INTERVAL)
    return edges


def collect_users(tab, sec_uid: str, kind: str) -> List[Dict[str, Any]]:
    """拉取粉丝/关注列表(sec_uid 去重, API 游标偶发重复)。"""
    users = []
    seen = set()
    cursor = 0
    for _ in range(300):
        items, has_more, cursor = api.user_list(tab, sec_uid, kind, cursor)
        for u in items:
            key = u.get("sec_uid") or u.get("uid") or u.get("nickname")
            if key in seen:
                continue
            seen.add(key)
            users.append({
                "nickname": u.get("nickname", ""),
                "douyin_id": u.get("short_id", ""),
                "sec_uid": u.get("sec_uid", ""),
                "uid": u.get("uid", ""),
                "signature": u.get("signature", ""),
                "follower_count": u.get("follower_count", 0),
                "following_count": u.get("following_count", 0),
                "favorited_count": u.get("total_favorited", 0),
            })
        if not has_more:
            break
        time.sleep(_INTERVAL)
    return users


def collect_profile(tab, sec_uid: str) -> Dict[str, Any]:
    """主页公开计数(关注/粉丝/获赞)——列表可私有, 数字始终可见。

    Args:
        tab: 已登录标签页。
        sec_uid: 目标 sec_uid。

    Returns:
        {"follows_count", "fans_count", "likes_count"} 字符串形式
        (如 "265"/"1.2万"), 抓取失败返回空串。
    """
    tab.get("https://www.douyin.com/user/" + sec_uid)
    import json as _json
    # SPA 渲染有延迟, 循环等"关注/粉丝"两个数字都出现(最长 ~20s)
    for _ in range(40):
        r = tab.run_js("""
        try {
          var txt = document.body.innerText;
          var m1 = txt.match(/关注[\\s\\n]*([\\d.]+[万千]?)/);
          var m2 = txt.match(/粉丝[\\s\\n]*([\\d.]+[万千]?)/);
          if (!m1 || !m2) return 'null';
          var m3 = txt.match(/获赞[\\s\\n]*([\\d.]+[万千]?)/);
          return JSON.stringify({follows: m1[1], fans: m2[1],
                                 likes: m3 ? m3[1] : ''});
        } catch(e) { return 'null'; }
        """)
        d = _json.loads(r or "null")
        if d:
            return {"follows_count": d.get("follows", ""),
                    "fans_count": d.get("fans", ""),
                    "likes_count": d.get("likes", "")}
        time.sleep(0.5)
    return {"follows_count": "", "fans_count": "", "likes_count": ""}


def main(sec_uid: str, profile: str = None, headless: bool = True) -> None:
    """全量采集入口。

    Args:
        sec_uid: 目标账号 sec_uid(抖音个人主页 URL 中提取)。
        profile: 浏览器配置目录, None=默认项目下 browser_data_hd。
        headless: True=无窗口; False=可见窗口(可现场扫码)。
    """
    os.makedirs(_DATA_DIR, exist_ok=True)
    page = new_page(profile=profile, headless=headless)
    tab = page.new_tab()
    tab.get("https://www.douyin.com/")

    videos = collect_videos(tab, sec_uid)

    profile_row = collect_profile(tab, sec_uid)
    profile_row["sec_uid"] = sec_uid

    comments = collect_comments(tab, [v["id"] for v in videos])

    replies = collect_replies(tab, comments)

    fans = collect_users(tab, sec_uid, "follower")

    follows = collect_users(tab, sec_uid, "following")

    # 统一 JSON 落盘(data.json, 活跃案唯一数据文件)
    import json as _json
    data = {"videos": videos, "comments": comments, "replies": replies,
            "fans": fans, "follows": follows, "profile": profile_row}
    with open(os.path.join(_DATA_DIR, "data.json"), "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=1)

    tab.close()
    page.quit()
    print(f"采集完成: videos={len(videos)} comments={len(comments)} "
          f"replies={len(replies)} fans={len(fans)} follows={len(follows)} "
          f"→ data/data.json")
    if not fans or not follows:
        print("⚠️ 粉丝/关注列表为空: 目标列表可能设为仅互关/仅自己可见, "
              "需用有权限的账号会话重新采集(可疑点规则 1/5/8 将失效)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法: python -m sherlock.collect <sec_uid> [--profile 目录] [--visible]")
        sys.exit(1)
    profile = None
    headless = True
    if "--profile" in args:
        i = args.index("--profile")
        if i + 1 >= len(args) or args[i + 1].startswith("--"):
            print("用法: python -m sherlock.collect <sec_uid> [--profile 目录] [--visible]")
            sys.exit(1)
        profile = args[i + 1]
    if "--visible" in args:
        headless = False
    main(args[0], profile=profile, headless=headless)
