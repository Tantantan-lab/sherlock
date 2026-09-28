"""可疑点自动检测: 把手工侦查规则代码化。

每条可疑点输出统一结构: {rule, person, evidence, severity, note, score},
由 report.py 汇总成「可疑点清单」, 并可自动生成案件板线索流程。
"""
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

# 称呼类关键词: 出现在评论里会暴露现实关系
_TITLE_WORDS = ("师妹", "学妹", "学姐", "学长", "宝宝", "宝贝", "老婆",
                "姐妹", "舍友", "室友", "师兄", "师弟", "紫啧")
# 情绪型视频标题关键词(熟人却只发表情 = 集体沉默信号)
_EMOTION_WORDS = ("爱你", "想你", "眼泪", "独白", "委屈", "难过", "错了",
                  "舍不得", "荒谬", "温柔", "覆水")
# 深夜时段(亲近的人出没)
_NIGHT_HOURS = {0, 1, 2, 3}


def _parse_dt(s: str) -> Optional[datetime]:
    """'YYYY-MM-DD HH:MM' → datetime, 失败返回 None。"""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})", s or "")
    if not m:
        return None
    return datetime(*map(int, m.groups()))


def _days_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
    if not a or not b:
        return None
    return abs((b - a).days)


_LOVE_SIGNALS = ("理想型", "老公", "老婆", "宝贝", "在一起")


def detect(data: Dict[str, List[Dict[str, Any]]],
           exclude_uids: Optional[List[str]] = None,
           target_fans: int = 0,
           target_name: str = "") -> List[Dict[str, Any]]:
    """对采集数据运行全部可疑点规则。

    Args:
        data: load_all() 返回值(videos/comments/replies/fans/follows)。
        exclude_uids: 排除名单。
        target_fans: 目标账号粉丝数(用于大V反向关注阈值)。

    Returns:
        可疑点列表, 按 score 降序。每条含 rule/person/evidence/severity/note/score。
    """
    exclude = set(exclude_uids or [])
    suspects: List[Dict[str, Any]] = []

    # ---- 预处理 ----
    comments = [r for r in data.get("comments", [])
                if r.get("sec_uid") and r["sec_uid"] not in exclude]
    replies = data.get("replies", [])
    fans = {r["sec_uid"]: r for r in data.get("fans", [])
            if r.get("sec_uid") and r["sec_uid"] not in exclude}
    follows = {r["sec_uid"]: r for r in data.get("follows", [])
               if r.get("sec_uid") and r["sec_uid"] not in exclude}
    mutual = set(fans) & set(follows)

    by_user = defaultdict(list)
    first_comment = {}
    last_comment = {}
    for r in comments:
        u = r["sec_uid"]
        by_user[u].append(r)
        t = _parse_dt(r.get("created_at"))
        if t:
            if u not in first_comment or t < first_comment[u]:
                first_comment[u] = t
            if u not in last_comment or t > last_comment[u]:
                last_comment[u] = t

    now = max(last_comment.values()) if last_comment else None
    videos = data.get("videos", [])
    video_dates = [datetime.fromtimestamp(int(v["create_time"]))
                   for v in videos if v.get("create_time")]

    # ---- 规则 1: 退场者(曾是熟人/核心粉, 突然消失) ----
    for u, cs in by_user.items():
        if u not in (mutual | set(fans)):
            continue
        if now and last_comment.get(u) and _days_between(last_comment[u], now) >= 90:
            sev = "高" if (u in mutual and len(cs) >= 5) else "中"
            # 反证: 签名公开示爱/点名 → 停评不等于退场(可能转线下), 降级并备注
            sig = (fans.get(u) or {}).get("signature", "") or ""
            counter = ""
            if target_name and target_name in sig:
                counter = "反证: 签名公开点名目标"
            elif any(w in sig for w in _LOVE_SIGNALS):
                counter = "反证: 签名公开示爱(%s)" % sig[:16]
            if counter:
                sev = "中"
            # 证据取时间上最新的一条(CSV 按视频序, cs[-1] 不是最新评论)
            latest_cs = max(cs, key=lambda r: _parse_dt(r.get("created_at"))
                            or datetime(1970, 1, 1))
            suspects.append({
                "rule": "退场者",
                "person": (fans.get(u) or {}).get("nickname", "") or cs[0].get("nickname", ""),
                "evidence": "最后评论: %s「%s」" % (
                    latest_cs.get("created_at", "?")[:16],
                    (latest_cs.get("comment_text") or "")[:28]),
                "severity": sev,
                "note": "与目标%s, 但已 %d 天未评论(共 %d 条), 关注关系未解除。%s" % (
                    "互关" if u in mutual else "有粉丝关系",
                    _days_between(last_comment[u], now), len(cs), counter),
            })

    # ---- 规则 2: 全勤者(评论覆盖 ≥80% 视频, 非粉丝者更可疑) ----
    total_videos = len({v.get("id") for v in videos})
    if total_videos:
        for u, cs in by_user.items():
            cover = len({c.get("video_id") for c in cs})
            if cover >= total_videos * 0.8 and cover >= 10:
                suspects.append({
                    "rule": "全勤者",
                    "person": cs[0].get("nickname", ""),
                    "evidence": "%d/%d 个视频均评论" % (cover, total_videos),
                    "severity": "低" if u in fans else "中",
                    "note": "全勤却%s, 现实密友或高频关注者。" % (
                        "在粉丝名单中" if u in fans else "不在粉丝名单中(神秘好友特征)"),
                })

    # ---- 规则 3: 称呼异常(现实关系暴露) ----
    for r in comments:
        for w in _TITLE_WORDS:
            if w in (r.get("comment_text") or ""):
                suspects.append({
                    "rule": "称呼异常",
                    "person": r.get("nickname", ""),
                    "evidence": "[%s] %s「%s」" % (
                        r.get("created_at", "?")[:10], r.get("nickname", ""),
                        (r.get("comment_text") or "")[:36]),
                    "severity": "中" if w in ("宝宝", "老婆", "宝贝") else "低",
                    "note": "称呼「%s」暴露现实关系(同学/情侣/闺蜜)。" % w,
                })
                break

    # ---- 规则 4: 深夜出没(0-3 点评论者) ----
    night_users = {}
    for r in comments:
        t = _parse_dt(r.get("created_at"))
        if t and t.hour in _NIGHT_HOURS:
            night_users.setdefault(r["sec_uid"], []).append(r)
    for u, cs in night_users.items():
        if len(cs) >= 3:
            suspects.append({
                "rule": "深夜出没",
                "person": cs[0].get("nickname", ""),
                "evidence": "%d 条深夜(0-3点)评论, 如 %s「%s」" % (
                    len(cs), cs[0].get("created_at", "?")[5:16],
                    (cs[0].get("comment_text") or "")[:24]),
                "severity": "低",
                "note": "深夜固定出没, 多为关系亲近或作息同步的人。",
            })

    # ---- 规则 5: 大V反向关注 ----
    threshold = max(target_fans * 3, 5000)
    for u, fr in fans.items():
        n = int(fr.get("follower_count") or 0)
        if n >= threshold:
            suspects.append({
                "rule": "大V反向关注",
                "person": fr.get("nickname", ""),
                "evidence": "粉丝数 %d(目标约 %d), 签名: %s" % (
                    n, target_fans, (fr.get("signature") or "无")[:30]),
                "severity": "中",
                "note": "体量远超目标却反向关注: 商务合作或现实认识。",
            })

    # ---- 规则 6: 爆赞单条(只评1条却获赞极高) ----
    for u, cs in by_user.items():
        if len(cs) == 1:
            d = int(cs[0].get("digg_count") or 0)
            if d >= 25:
                suspects.append({
                    "rule": "爆赞单条",
                    "person": cs[0].get("nickname", ""),
                    "evidence": "仅 1 条评论「%s」获赞 %d" % (
                        (cs[0].get("comment_text") or "")[:24], d),
                    "severity": "低",
                    "note": "低频但单条引爆, 是传播节点而非关系节点。",
                })

    # ---- 规则 7: 时间巧合(事件对间隔 ≤ 7 天) ----
    # 锚点事件: 关键人物首次评论; 检验事件: 情绪性发言。
    # 输出显式给出两个日期与间隔天数——时间相近只是巧合信号,
    # 不等于因果, 必须回到时间线检验(分析守则③)。
    name_map = {}
    for r in comments:
        name_map.setdefault(r.get("sec_uid"), r.get("nickname", ""))
    emotion_words = ("戒断", "好久不见", "消失", "退出")
    for r in comments:
        text = r.get("comment_text") or ""
        if not any(w in text for w in emotion_words):
            continue
        t2 = _parse_dt(r.get("created_at"))
        if not t2:
            continue
        for u, t1 in first_comment.items():
            if u == r.get("sec_uid"):
                continue
            gap = (t2 - t1).days
            if 0 < gap <= 7:
                suspects.append({
                    "rule": "时间巧合",
                    "person": r.get("nickname", ""),
                    "evidence": "%s 首次评论于 %s, %d 天后 %s 发表「%s」" % (
                        name_map.get(u, "?"), t1.strftime("%Y-%m-%d"),
                        gap, r.get("created_at", "?")[:10], text[:18]),
                    "severity": "中",
                    "note": "两事件间隔仅 %d 天。时间相近不等于因果, "
                            "需对照时间线检验是否相关。" % gap,
                })

    # ---- 规则 8: 集体沉默(情绪型视频下熟人只发表情) ----
    for v in videos:
        title = v.get("title", "") or ""
        if not any(w in title for w in _EMOTION_WORDS):
            continue
        vcom = [r for r in comments if r.get("video_id") == v.get("id")]
        friends = [r for r in vcom if r["sec_uid"] in (mutual | set(fans))]
        texty = [r for r in friends if len(r.get("comment_text") or "") >= 4]
        if friends and not texty:
            suspects.append({
                "rule": "集体沉默",
                "person": "熟人圈",
                "evidence": "[%s] 视频「%s」: %d 位熟人仅发表情" % (
                    datetime.fromtimestamp(int(v["create_time"])).strftime("%Y-%m-%d"),
                    title[:24], len(friends)),
                "severity": "高",
                "note": "情绪型文案下熟人只发表情不接话, 事件可能真实且不便公开。",
            })

    # 按 (规则, 人物) 去重, 保留严重度最高的一条
    order = {"高": 0, "中": 1, "低": 2}
    seen = {}
    for s in suspects:
        key = (s["rule"], s["person"])
        if key not in seen or order[s["severity"]] < order[seen[key]["severity"]]:
            seen[key] = s
    suspects = list(seen.values())

    # 量化评估分: 严重度基础分 + 证据信息量 + 说明中的数字信号
    for s in suspects:
        base = {"高": 60, "中": 40, "低": 20}.get(s["severity"], 10)
        digits = sum(c.isdigit() for c in s.get("note", ""))
        s["score"] = min(99, base + len(s.get("evidence", "")) // 6
                         + min(digits, 20) // 2)

    # 按评估分排序
    suspects.sort(key=lambda s: -s["score"])
    return suspects
