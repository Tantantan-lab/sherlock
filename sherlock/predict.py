"""预测分析: 系统基于数据自己下判断(无需交互)。

三个预测:
- 亲密度评分: 多因子加权, 谁是目标最亲近的人
- 退场风险: 评论频率衰减 + 距最后评论天数, 谁可能下一个消失
- 情绪周期: 月度情绪文案密度, 判断情绪低谷/高峰规律
"""
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from sherlock.suspects import _parse_dt


def closeness_ranking(data: Dict[str, List[Dict[str, Any]]],
                     exclude_uids: Optional[List[str]] = None,
                     author_uid: str = "") -> List[Dict[str, Any]]:
    """亲密度评分: 互关/核心粉/评论量/被回复/深夜共现/时间跨度加权。

    Args:
        data: load_all() 返回值。
        exclude_uids: 排除名单。
        author_uid: 目标 sec_uid(其本人不参与排名)。

    Returns:
        按分数降序的排名列表, 每项含各因子分解。
    """
    exclude = set(exclude_uids or [])
    comments = [r for r in data.get("comments", [])
                if r.get("sec_uid") and r["sec_uid"] not in exclude]
    replies = data.get("replies", [])
    fans = {r["sec_uid"]: r for r in data.get("fans", [])
            if r.get("sec_uid") and r["sec_uid"] not in exclude}
    follows = {r["sec_uid"]: r for r in data.get("follows", [])
               if r.get("sec_uid") and r["sec_uid"] not in exclude}
    mutual = set(fans) & set(follows)

    by_user = defaultdict(lambda: {"n": 0, "hours": Counter(), "days": []})
    for r in comments:
        u = r.get("sec_uid")
        if not u or u == author_uid:
            continue
        d = by_user[u]
        d["n"] += 1
        t = _parse_dt(r.get("created_at"))
        if t:
            d["hours"][t.hour] += 1
            d["days"].append(t)

    main_author = {r.get("comment_id"): r.get("sec_uid") for r in comments
                   if r.get("comment_id")}
    replied = Counter()
    for r in replies:
        a = main_author.get(r.get("main_comment_id"))
        if r.get("reply_sec_uid") == author_uid and a:
            replied[a] += 1

    name_map = {}
    for r in comments:
        if r.get("sec_uid") and r.get("nickname"):
            name_map.setdefault(r["sec_uid"], r["nickname"])
    out = []
    for u, d in by_user.items():
        span = (max(d["days"]) - min(d["days"])).days if d["days"] else 0
        night = sum(n for h, n in d["hours"].items() if h in (0, 1, 2, 3))
        score = (10 if u in mutual else 0) + (5 if u in fans else 0) \
            + min(d["n"], 20) * 0.6 + min(replied.get(u, 0), 10) * 1.5 \
            + min(span, 600) * 0.005 + min(night, 10) * 0.4
        out.append({
            "person": name_map.get(u) or (fans.get(u) or {}).get("nickname", "") or "?",
            "role": "互关" if u in mutual else ("核心粉" if u in fans else "路人"),
            "score": round(score, 1),
            "comments": d["n"],
            "replied": replied.get(u, 0),
            "span_days": span,
            "night_comments": night,
        })
    out.sort(key=lambda x: -x["score"])
    return out


def churn_risk(data: Dict[str, List[Dict[str, Any]]],
               exclude_uids: Optional[List[str]] = None,
               author_uid: str = "") -> List[Dict[str, Any]]:
    """退场风险: 近期评论频率衰减 + 距最后评论天数。

    Returns:
        高风险在前。风险 = 早期活跃但近 60 天零评论。
    """
    exclude = set(exclude_uids or [])
    comments = [r for r in data.get("comments", [])
                if r.get("sec_uid") and r["sec_uid"] not in exclude]
    now = max((_parse_dt(r.get("created_at")) for r in comments
               if _parse_dt(r.get("created_at"))), default=None)
    if not now:
        return []
    by_user = defaultdict(list)
    for r in comments:
        if r.get("sec_uid") != author_uid:
            by_user[r["sec_uid"]].append(r)
    name_map = {}
    for r in comments:
        if r.get("sec_uid") and r.get("nickname"):
            name_map.setdefault(r["sec_uid"], r["nickname"])
    out = []
    for u, cs in by_user.items():
        times = sorted(t for t in (_parse_dt(c.get("created_at")) for c in cs) if t)
        if not times:
            continue
        last = times[-1]
        age = (now - last).days
        # 预测对象: 近 120 天仍活跃且基数足够的人
        if len(times) < 5 or age > 120:
            continue
        recent30 = sum(1 for t in times if (now - t).days <= 30)
        prev60 = sum(1 for t in times if 30 < (now - t).days <= 90)
        # 衰减比 = 近30天频率 / 前60天月均频率; <0.5 视为正在衰减
        ratio = (recent30 / 30.0) / max(prev60 / 60.0, 0.001)
        if ratio >= 0.5:
            continue
        out.append({"person": name_map.get(u) or cs[0].get("nickname", ""),
                    "last_comment": last.strftime("%Y-%m-%d"),
                    "age_days": age, "comments": len(times),
                    "recent30": recent30, "prev60": prev60,
                    "decline_ratio": round(ratio, 2),
                    "risk": round((0.5 - ratio) * 100 + age / 10, 1)})
    out.sort(key=lambda x: -x["risk"])
    return out[:10]


def emotion_cycle(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """月度情绪密度 → 周期规律(供预判情绪高峰)。

    Returns:
        {"monthly": [(月, 情绪文案数, 总视频数)], "peak": 最高月,
         "note": 规律描述}
    """
    _EMOTION = ("爱你", "想你", "眼泪", "独白", "委屈", "难过", "错了",
                "舍不得", "荒谬", "温柔", "覆水", "好久不见", "回忆")
    monthly = defaultdict(lambda: [0, 0])
    for v in videos:
        ts = int(v.get("create_time") or 0)
        if not ts:
            continue
        month = datetime.fromtimestamp(ts).strftime("%Y-%m")
        title = v.get("title", "") or ""
        monthly[month][1] += 1
        if any(w in title for w in _EMOTION):
            monthly[month][0] += 1
    rows = [(m, e, t) for m, (e, t) in sorted(monthly.items())]
    peak = max(rows, key=lambda r: r[1] / max(r[2], 1)) if rows else None
    return {"monthly": rows,
            "peak": peak,
            "note": "情绪密度峰值月为 %s(%d/%d 条视频含情绪文案)。"
                    "观察周期规律可预判下一次情绪低谷窗口。" % (
                        peak[0], peak[1], peak[2]) if peak else "数据不足。"}


if __name__ == "__main__":
    import json
    from sherlock import analyze
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ data/ 无数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    print("== 亲密度排名 ==")
    print(json.dumps(closeness_ranking(data), ensure_ascii=False, indent=2))
    print("== 退场风险 ==")
    print(json.dumps(churn_risk(data), ensure_ascii=False, indent=2))
    print("== 情绪周期 ==")
    print(json.dumps(emotion_cycle(data.get("videos", [])),
                     ensure_ascii=False, indent=2))
