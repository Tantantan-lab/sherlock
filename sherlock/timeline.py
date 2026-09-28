"""时间线还原: 从视频标题/发布时间 + 评论内容重建账号经历。

方法论: 视频标题是"日记"(发布时间的锚点), 评论内容是"旁证"。
按情感/生活事件/地点关键词切分阶段, 输出带证据的时间线。
"""
import re
from datetime import datetime
from typing import Any, Dict, List

# 情感事件关键词(标题中的情绪信号)
_EMOTION = ("爱你", "想你", "眼泪", "独白", "委屈", "难过", "错了", "舍不得",
            "荒谬", "温柔", "覆水", "好久不见", "回忆")
# 生活事件关键词
_LIFE = {"开学": "开学", "毕业": "毕业", "上班": "上班/工作", "生日": "生日",
         "留校": "假期留校", "放假": "放假", "离职": "离职"}
# 地点关键词
_PLACE = {"海边": "海边", "海洋馆": "海洋馆", "海岛": "海岛"}


def _fmt(ts: int) -> str:
    if not ts:
        return "?"
    return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")


def reconstruct(videos: List[Dict[str, Any]],
                comments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """重建时间线。

    Args:
        videos: 采集的视频列表(id/create_time/title)。
        comments: 采集的评论列表(用于旁证关键词)。

    Returns:
        {"timeline": [(日期, 标题, 事件标签, 情绪标签)],
         "events": [(日期, 事件, 证据)],
         "phases": [(阶段名, 起始日期, 依据)]}
    """
    videos = sorted(videos, key=lambda v: int(v.get("create_time") or 0))
    timeline = []
    events: List[tuple] = []
    for v in videos:
        title = v.get("title", "") or ""
        date = _fmt(v.get("create_time") or 0)
        tags = []
        for kw, label in _LIFE.items():
            if kw in title:
                tags.append(label)
                events.append((date, label, "视频标题: %s" % title[:36]))
        emotion = [e for e in _EMOTION if e in title]
        places = [p for p, name in _PLACE.items() if p in title]
        timeline.append({
            "date": date, "title": title[:48],
            "tags": tags, "emotion": bool(emotion), "places": places,
        })

    # 评论旁证: 时间线相关的关键评论
    for r in comments:
        text = r.get("comment_text") or ""
        if "毕业" in text or "上班" in text:
            events.append((str(r.get("created_at", "?"))[:10], "生活事件旁证",
                           "%s: %s" % (r.get("nickname", ""), text[:32])))

    # 阶段切分: 情感密度变化
    phases = []
    prev_emotion = False
    start = timeline[0]["date"] if timeline else "?"
    for i, t in enumerate(timeline):
        if i and t["emotion"] != prev_emotion:
            phases.append(("情绪期" if prev_emotion else "平稳期", start,
                           "情绪/平稳切换于 %s" % t["date"]))
            start = t["date"]
        prev_emotion = t["emotion"]
    phases.append(("情绪期" if prev_emotion else "平稳期", start, "至今"))
    return {"timeline": timeline, "events": events, "phases": phases}
