"""互关账号交叉探索: 查圈内人是否在互关们自己的视频下留过评论。

回答: "她关注的人发的视频, 我们圈子里谁去评论了" ——
交叉足迹矩阵, 用于发现隐藏的双向互动。
"""
import time
from typing import Any, Dict, List, Optional, Set

from sherlock import api
from sherlock.headless import new_page

_MAX_VIDEOS_PER_USER = 5
_MAX_COMMENT_PAGES = 2


def _known_uids(data: Dict[str, List[Dict[str, Any]]]) -> Set[str]:
    """圈内已知 uid 集合(粉丝+关注+评论者)。"""
    uids: Set[str] = set()
    for key in ("fans", "follows", "comments"):
        for r in data.get(key, []):
            u = r.get("sec_uid")
            if u:
                uids.add(u)
    return uids


def explore_cross_comments(data: Dict[str, List[Dict[str, Any]]],
                           top_n: int = 19,
                           interval: float = 1.2
                           ) -> List[Dict[str, Any]]:
    """互关们自己的视频 → 圈内人的评论足迹。

    Args:
        data: load_all() 返回值。
        top_n: 最多探索的互关人数。
        interval: 请求间隔(防风控)。

    Returns:
        每行: {互关, 圈内评论者, 评论内容, 时间}。
    """
    fans = {r["sec_uid"]: r for r in data.get("fans", []) if r.get("sec_uid")}
    follows = {r["sec_uid"]: r for r in data.get("follows", []) if r.get("sec_uid")}
    mutual = [u for u in fans if u in follows][:top_n]
    if not mutual:
        return []
    known = _known_uids(data)
    name_map = {}
    for key in ("fans", "follows", "comments"):
        for r in data.get(key, []):
            if r.get("sec_uid") and r.get("nickname"):
                name_map.setdefault(r["sec_uid"], r["nickname"])

    page = new_page()
    tab = page.new_tab()
    tab.get("https://www.douyin.com/")
    time.sleep(6)

    out = []
    for u in mutual:
        owner = fans[u].get("nickname", "?")
        try:
            videos, has_more, cursor = api.post_list(tab, u)
            videos = videos[:_MAX_VIDEOS_PER_USER]
        except Exception:
            videos = []
        for v in videos:
            cursor2 = 0
            for _ in range(_MAX_COMMENT_PAGES):
                try:
                    comments, has_more2, cursor2 = api.comment_list(
                        tab, str(v.get("id")), cursor2)
                except Exception:
                    break
                for c in comments:
                    user = c.get("user") or {}
                    cu = user.get("sec_uid", "")
                    if cu and cu in known and cu != u:
                        out.append({
                            "owner": owner,
                            "commenter": name_map.get(cu, user.get("nickname", "?")),
                            "text": (c.get("text") or "")[:40],
                            "time": time.strftime("%Y-%m-%d %H:%M",
                                                  time.localtime(int(c.get("create_time") or 0))),
                            "video_id": str(v.get("id") or ""),
                        })
                if not has_more2:
                    break
                time.sleep(interval)
        time.sleep(interval)
    tab.close()
    page.quit()
    return out


if __name__ == "__main__":
    import json
    from sherlock import analyze
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ data/ 无数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    print("互关足迹交叉排查(需浏览器会话与代理):")
    print(json.dumps(explore_cross_comments(data),
                     ensure_ascii=False, indent=2, default=str))
