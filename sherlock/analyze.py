"""分析层: 关系交叉推演 / 人物档案 / 内容主题情感。

输入为 data/ 下最新一批采集 CSV(见 sherlock.collect),
输出为可读的结构化结果, 供报告脚本渲染。
"""
import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _latest(pattern: str) -> Optional[str]:
    """data/ 目录下匹配 pattern 的最新文件路径。"""
    files = sorted(glob.glob(os.path.join(_DATA_DIR, pattern)))
    return files[-1] if files else None


# 旧版中文表头 → 英文规范表头(兼容 2026-09 之前采集的存量 CSV)
_LEGACY_HEADERS = {
    "视频ID": "video_id", "评论ID": "comment_id", "昵称": "nickname",
    "用户sec_uid": "sec_uid", "抖音号": "douyin_id", "评论": "comment_text",
    "时间": "created_at", "IP属地": "ip_label", "点赞数": "digg_count",
    "回复数": "reply_count", "回复者昵称": "reply_nickname",
    "主评论ID": "main_comment_id", "回复ID": "reply_id",
    "回复者sec_uid": "reply_sec_uid", "回复对象": "reply_to",
    "回复内容": "reply_text", "粉丝数": "follower_count",
    "关注数": "following_count", "获赞数": "favorited_count",
    "签名": "signature",
}


def _load_csv(path: str) -> List[Dict[str, Any]]:
    """读取 CSV, 旧中文表头自动映射为英文规范名。"""
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and any(k in _LEGACY_HEADERS for k in rows[0]):
        rows = [{_LEGACY_HEADERS.get(k, k): v for k, v in r.items()}
                for r in rows]
    return rows


def load_all() -> Dict[str, List[Dict[str, Any]]]:
    """加载活跃案数据: data/data.json(统一 JSON, 唯一存储)。

    兼容回退: data.json 不存在时读旧版 CSV 批次(2026-09 之前的存量数据),
    仍会给出迁移提示。

    Returns:
        {"videos": [...], "comments": [...], "replies": [...],
         "fans": [...], "follows": [...], "profile": {}},
        缺失的类型为空列表/空 dict。
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    jp = os.path.join(_DATA_DIR, "data.json")
    if os.path.exists(jp):
        with open(jp, encoding="utf-8") as f:
            data = json.load(f)
        for key in ("videos", "comments", "replies", "fans", "follows"):
            out[key] = data.get(key, []) or []
        out["profile"] = data.get("profile", {}) or {}
        return out
    # ---- 旧 CSV 批次回退(仅存量数据迁移期) ----
    found: Dict[str, str] = {}
    for key, pattern in (("videos", "videos_*.csv"),
                         ("comments", "comments_*.csv"),
                         ("replies", "replies_*.csv"),
                         ("fans", "fans_*.csv"),
                         ("follows", "follows_*.csv")):
        path = _latest(pattern)
        if path:
            found[key] = os.path.basename(path).split("_")[-1].split(".")[0]
        out[key] = _load_csv(path) if path else []
    profile = _latest("profile_*.csv")
    out["profile"] = (_load_csv(profile)[0] if profile else {})
    ts = set(found.values())
    if len(ts) > 1:
        print("⚠️ data/ 批次时间戳不一致(可能混了两个案件/批次): %s" % found)
    print("ℹ️ 检测到旧 CSV 批次, 建议迁到 data.json(跑一次采集即自动生成)")
    return out


def relationship_report(data: Dict[str, List[Dict[str, Any]]],
                        exclude_uids: Optional[List[str]] = None
                        ) -> Dict[str, Any]:
    """交叉分析: 粉丝∩评论者 / 互关 / 评论时段 / IP 属地。

    Args:
        data: load_all() 的返回值。
        exclude_uids: 需要从分析中排除的 sec_uid(如隐私账号)。

    Returns:
        统计字典: fans/follows/commenters/core_fans/mutual 计数,
        top_hours 与 top_ips 高频榜。
    """
    exclude = set(exclude_uids or [])
    comments = data.get("comments", [])
    fans = {r["sec_uid"]: r for r in data.get("fans", [])
            if r.get("sec_uid") and r["sec_uid"] not in exclude}
    follows = {r["sec_uid"]: r for r in data.get("follows", [])
               if r.get("sec_uid") and r["sec_uid"] not in exclude}
    commenters = Counter()
    hours = Counter()
    ips = Counter()
    for r in comments:
        uid = r.get("sec_uid")
        if not uid or uid in exclude:
            continue
        commenters[uid] += 1
        m = re.match(r"\d{4}-\d{2}-\d{2} (\d{2}):", r.get("created_at") or "")
        if m:
            hours[int(m.group(1))] += 1
        if r.get("ip_label"):
            ips[r["ip_label"]] += 1
    return {
        "fans": len(fans),
        "follows": len(follows),
        "commenters": len(commenters),
        "core_fans": len(set(fans) & set(commenters)),
        "mutual": len(set(fans) & set(follows)),
        "top_hours": hours.most_common(5),
        "top_ips": ips.most_common(8),
    }


def person_profiles(data: Dict[str, List[Dict[str, Any]]],
                    exclude_uids: Optional[List[str]] = None
                    ) -> List[Dict[str, Any]]:
    """全员人物档案: 评论/获赞/覆盖/时段/IP/签名(与旧版同口径 12 列)。

    Returns:
        按评论数降序的档案列表, 每项含昵称/身份/评论数/总获赞/
        覆盖视频/被作者回复/活跃高峰/IP属地/TA的粉丝数/签名/评论样例/情感均值。
    """
    exclude = set(exclude_uids or [])
    comments = data.get("comments", [])
    fans = {r["sec_uid"]: r for r in data.get("fans", [])
            if r.get("sec_uid") and r["sec_uid"] not in exclude}
    follows = {r["sec_uid"]: r for r in data.get("follows", [])
               if r.get("sec_uid") and r["sec_uid"] not in exclude}
    author_uid = (data.get("profile") or {}).get("sec_uid", "")
    # 被作者回复: 作者在"谁的评论下"回复(旧数据的 reply_to 多为空, 需经主评论归属)
    main_author = {r.get("comment_id"): r.get("sec_uid") for r in comments
                   if r.get("comment_id")}
    replied_by = Counter()
    for r in data.get("replies", []):
        if author_uid and r.get("reply_sec_uid") == author_uid:
            replied_by[main_author.get(r.get("main_comment_id"))] += 1
    profiles = defaultdict(lambda: {
        "n": 0, "digg": 0, "videos": set(), "hours": Counter(),
        "ips": Counter(), "name": "", "sample": "", "texts": []})
    for r in comments:
        uid = r.get("sec_uid")
        if not uid or uid in exclude:
            continue
        d = profiles[uid]
        d["n"] += 1
        d["digg"] += int(r.get("digg_count") or 0)
        d["videos"].add(r.get("video_id"))
        d["name"] = d["name"] or r.get("nickname", "")
        if not d["sample"]:
            d["sample"] = (r.get("comment_text") or "")[:30]
        d["texts"].append(r.get("comment_text") or "")
        if r.get("ip_label"):
            d["ips"][r["ip_label"]] += 1
        m = re.match(r"\d{4}-\d{2}-\d{2} (\d{2}):", r.get("created_at") or "")
        if m:
            d["hours"][int(m.group(1))] += 1
    # 情感均值: 每人的评论逐条 SnowNLP 取平均(懒加载, 失败则留空)
    senti: Dict[str, float] = {}
    try:
        from snownlp import SnowNLP
        for uid, d in profiles.items():
            scores = []
            for t in d["texts"]:
                try:
                    scores.append(SnowNLP(t).sentiments)
                except Exception:
                    pass
            if scores:
                senti[uid] = round(sum(scores) / len(scores), 2)
    except ImportError:
        pass
    out = []
    for uid, d in profiles.items():
        if uid in fans and uid in follows:
            role = "互关"
        elif uid in fans:
            role = "核心粉"
        elif uid in follows:
            role = "关注"
        else:
            role = "路人"
        out.append({
            "nickname": d["name"],
            "role": role,
            "comment_count": d["n"],
            "total_digg": d["digg"],
            "videos_covered": len(d["videos"]),
            "replied_by_author": replied_by.get(uid, 0),
            "peak_hours": "/".join(
                f"{h}时" for h, _ in d["hours"].most_common(2)),
            "ip_label": d["ips"].most_common(1)[0][0] if d["ips"] else "",
            "follower_count": int((fans.get(uid) or {}).get("follower_count") or 0),
            "signature": (fans.get(uid) or {}).get("signature", ""),
            "comment_sample": d["sample"],
            "sentiment_avg": senti.get(uid, ""),
        })
    out.sort(key=lambda p: -p["comment_count"])
    return out


def content_topics(comments: List[Dict[str, Any]],
                   exclude_uids: Optional[List[str]] = None,
                   n_topics: int = 6) -> Dict[str, Any]:
    """评论文本层: LDA 主题聚类 + SnowNLP 情感分布。

    Args:
        comments: 评论列表(load_all 的 comments)。
        exclude_uids: 排除名单。
        n_topics: LDA 主题数, 默认 6。

    Returns:
        {"topics": [[关键词...]...], "sentiment": {positive/neutral/
        negative: 百分比}}。
    """
    import jieba
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import TfidfVectorizer
    from snownlp import SnowNLP

    exclude = set(exclude_uids or [])
    docs = []
    raw_texts = []
    for r in comments:
        if (not r.get("sec_uid") or r["sec_uid"] in exclude
                or not r.get("comment_text")):
            continue
        text = re.sub(r"\[[^\]]*\]|@\S+|#\S+#?|https?://\S+", " ", r["comment_text"])
        docs.append(" ".join(
            w.strip() for w in jieba.cut(text) if len(w.strip()) >= 2))
        raw_texts.append((r.get("comment_text") or "")[:36])
    # 小样本(<10 条)或词表过小时跳过 LDA, 只做情感统计(9 条评论也能出结果)
    topics = []
    if len(docs) >= 10:
        try:
            vectorizer = TfidfVectorizer(max_features=800, max_df=0.5,
                                         min_df=2)
            matrix = vectorizer.fit_transform(docs)
            if matrix.shape[1] >= 2:
                model = LatentDirichletAllocation(
                    n_components=min(n_topics, len(docs), matrix.shape[1]),
                    random_state=42)
                model.fit(matrix)
                words = vectorizer.get_feature_names_out()
                topics = [[words[j] for j in comp.argsort()[-8:][::-1]]
                          for comp in model.components_]
        except ValueError:
            topics = []  # 词汇表为空/剪枝后无词(重复或表情刷屏), 跳过 LDA
    pos = neg = neu = 0
    scored = []
    # 情感在原始文本上打分(jieba 分词会丢否定词, 如"不好看"→"好看")
    for raw in raw_texts:
        try:
            score = SnowNLP(raw).sentiments
        except Exception:
            score = 0.5
        scored.append((score, raw))
        pos += score >= 0.6
        neg += score <= 0.4
        neu += 0.4 < score < 0.6
    total = len(scored) or 1
    pos_samples = [(round(s, 2), t) for s, t in sorted(scored, key=lambda x: -x[0]) if s >= 0.6][:3]
    neg_samples = [(round(s, 2), t) for s, t in sorted(scored, key=lambda x: x[0]) if s <= 0.4][:3]
    return {
        "topics": topics,
        "sentiment": {
            "positive": round(pos / total * 100),
            "neutral": round(neu / total * 100),
            "negative": round(neg / total * 100),
        },
        "positive_samples": pos_samples,
        "negative_samples": neg_samples,
    }

_REGIONS = ("广东", "湖南", "浙江", "四川", "广西", "福建", "江西", "重庆",
            "江苏", "湖北", "河南", "山东", "安徽", "陕西", "云南", "贵州",
            "北京", "上海", "天津", "河北", "山西", "辽宁", "吉林",
            "黑龙江", "内蒙古", "甘肃", "宁夏", "青海", "新疆", "西藏",
            "海南", "香港", "澳门", "台湾")


def _ip_region(ip: str) -> str:
    """IP 属地 → 省份(未知返回 未知)。"""
    ip = (ip or "").strip()
    if not ip:
        return "未知"
    for r in _REGIONS:
        if r in ip:
            return r
    return "其他"


def _display_name(name: str, fallback_id: str = "") -> str:
    """昵称兜底: 仅空名退回抖音号(emoji 昵称浏览器可正常渲染, 保留)。"""
    name = (name or "").strip()
    return name if name else (fallback_id or "用户")


def author_name_from(data: Dict[str, Any]) -> str:
    """从作者自己的回复/评论还原作者昵称(需要 profile 有 sec_uid)。"""
    author_uid = (data.get("profile") or {}).get("sec_uid", "")
    if not author_uid:
        return ""
    for r in data.get("replies", []):
        if r.get("reply_sec_uid") == author_uid:
            return r.get("reply_nickname", "")
    for r in data.get("comments", []):
        if r.get("sec_uid") == author_uid:
            return r.get("nickname", "")
    return ""


def case_name(data: Dict[str, Any]) -> str:
    """案件目录名: 作者昵称净化(中文/字母/数字), 无法还原时回退 case。"""
    name = author_name_from(data)
    name = re.sub(r"[^\w一-鿿]", "", name or "")
    return name or "case"


def build_graph_data(data: Dict[str, List[Dict[str, Any]]],
                     exclude_uids: Optional[List[str]] = None,
                     author_id: str = "AUTHOR",
                     author_name: str = "",
                     author_uid: str = ""
                     ) -> Dict[str, Any]:
    """采集数据 → 关系图数据(作者/用户节点 + 四类边)。

    供 graph.render_sherlock 使用; 角色优先级: 互关 > 核心粉 > 粉丝
    > 关注 > 路人。边: 粉丝/关注/互关(关注关系) + 回复(用户→用户)。
    视频不进图(按用户要求), 视频与评论的关系看情报整理页。

    Args:
        data: load_all() 返回值。
        exclude_uids: 排除名单。
        author_id: 目标作者的节点 id(图中固定为 AUTHOR)。

    Returns:
        {"nodes": [...], "edges": [...]}。
    """
    exclude = set(exclude_uids or [])
    prof = data.get("profile") or {}
    # 作者 sec_uid: 优先调用参数, 否则取采集时写入 profile 的 sec_uid
    author_uid = author_uid or prof.get("sec_uid", "")
    # 作者昵称: 从作者自己的回复/评论里还原
    if not author_uid:
        print("⚠️ profile 无 sec_uid: 作者身份未知, 若作者本人有评论/回复, "
              "会生成幽灵用户节点与 AUTHOR 冲突; 请先跑一次 collect 补齐 profile")
    if not author_name:
        author_name = author_name_from(data)
    comments = [r for r in data.get("comments", [])
                if r.get("sec_uid") and r["sec_uid"] not in exclude]
    fans = {r["sec_uid"]: r for r in data.get("fans", [])
            if r.get("sec_uid") and r["sec_uid"] not in exclude}
    follows = {r["sec_uid"]: r for r in data.get("follows", [])
               if r.get("sec_uid") and r["sec_uid"] not in exclude}

    by_user = defaultdict(lambda: {"n": 0, "ips": Counter(), "name": ""})
    for r in comments:
        d = by_user[r["sec_uid"]]
        d["n"] += 1
        d["name"] = d["name"] or r.get("nickname", "")
        if r.get("ip_label"):
            d["ips"][r["ip_label"]] += 1

    def role(uid: str) -> str:
        """身份判定(纯关注关系 + 评论活跃度)。

        注意: 粉丝名单受 API 可见上限影响, 部分真实粉丝会被
        判为路人/高频路人——这是数据边界, 不是行为边界。
        """
        if uid in fans and uid in follows:
            return "互关"
        if uid in fans and uid in by_user:
            return "核心粉"
        if uid in fans:
            return "粉丝"
        if uid in follows:
            return "关注"
        if by_user.get(uid, {}).get("n", 0) >= 5:
            return "高频路人"
        return "路人"

    # 抖音号来源: 粉丝/关注表的 short_id, 缺失时用评论表
    douyin_id = {}
    for r in list(data.get("fans", [])) + list(data.get("follows", [])):
        if r.get("sec_uid") and r.get("douyin_id"):
            douyin_id.setdefault(r["sec_uid"], r["douyin_id"])
    for r in data.get("comments", []):
        if r.get("sec_uid") and r.get("douyin_id"):
            douyin_id.setdefault(r["sec_uid"], r["douyin_id"])

    nodes = [{"id": author_id, "label": author_name or "目标",
              "type": "author", "role": "作者", "size": 48,
              "comment_n": 0, "ip": "", "ip_region": "未知",
              "douyin_id": "", "name_full": author_name or "目标",
              "follows_count": prof.get("follows_count", ""),
              "fans_count": prof.get("fans_count", ""),
              "likes_count": prof.get("likes_count", "")}]
    for uid, d in by_user.items():
        if uid == author_uid:
            continue
        full = _display_name(d["name"], douyin_id.get(uid, ""))
        nodes.append({
            "id": uid,
            "label": full[:12],
            "name_full": full,
            "type": "user",
            "role": role(uid),
            "size": 8 + min(d["n"] * 2, 26),
            "comment_n": d["n"],
            "ip": d["ips"].most_common(1)[0][0] if d["ips"] else "",
            "ip_region": _ip_region(d["ips"].most_common(1)[0][0]
                                    if d["ips"] else ""),
            "douyin_id": douyin_id.get(uid, ""),
        })

    for uid, fr in fans.items():
        if uid not in by_user:
            nodes.append({"id": uid,
                          "label": _display_name(fr.get("nickname", ""),
                                                 fr.get("douyin_id", ""))[:12],
                          "name_full": _display_name(fr.get("nickname", ""),
                                                     fr.get("douyin_id", "")),
                          "type": "user", "role": role(uid),
                          "size": 8, "comment_n": 0, "ip": "", "ip_region": "未知",
                          "douyin_id": fr.get("douyin_id", "")})
    for uid, fr in follows.items():
        if uid not in by_user and uid not in fans:
            nodes.append({"id": uid,
                          "label": _display_name(fr.get("nickname", ""),
                                                 fr.get("douyin_id", ""))[:12],
                          "name_full": _display_name(fr.get("nickname", ""),
                                                     fr.get("douyin_id", "")),
                          "type": "user", "role": role(uid),
                          "size": 8, "comment_n": 0, "ip": "", "ip_region": "未知",
                          "douyin_id": fr.get("douyin_id", "")})

    edges = []
    mutual = set(fans) & set(follows)
    for uid in fans:
        edges.append({"source": uid, "target": author_id,
                      "type": "互关" if uid in mutual else "粉丝"})
    for uid in follows:
        if uid not in mutual:
            edges.append({"source": author_id, "target": uid, "type": "关注"})
    main_author = {r["comment_id"]: r["sec_uid"] for r in comments
                   if r.get("comment_id")}
    for r in data.get("replies", []):
        u, a = r.get("reply_sec_uid"), main_author.get(r.get("main_comment_id"))
        if not u or not a or u == a:
            continue
        if author_uid and u == author_uid:
            u = author_id
        if author_uid and a == author_uid:
            a = author_id
        if u in exclude or a in exclude:
            continue
        edges.append({"source": u, "target": a, "type": "回复"})

    # 关系度数与亲密度(供图: 球大小按亲密度)
    degree: Dict[str, int] = defaultdict(int)
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    for n in nodes:
        n["degree"] = degree.get(n["id"], 0)
        # 亲密度 = 互关10 + 粉丝5 + 评论0.6 + 被回复1.5(与 predict 同口径)
        n["closeness"] = round(
            (10 if n["role"] == "互关" else 0)
            + (5 if n["role"] in ("核心粉", "粉丝") else 0)
            + min(n.get("comment_n", 0), 20) * 0.6
            + min(degree.get(n["id"], 0), 10) * 1.5, 1)
    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    data = load_all()
    if not data.get("comments"):
        print("❌ data/ 无数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    rel = relationship_report(data)
    print("粉丝 %d / 关注 %d / 评论者 %d / 核心粉 %d / 互关 %d" % (
        rel["fans"], rel["follows"], rel["commenters"],
        rel["core_fans"], rel["mutual"]))
    print("高峰:", rel["top_hours"][:4], "IP:", rel["top_ips"][:4])
    for p in person_profiles(data)[:10]:
        print("- %s [%s] 评论%d 获赞%d" % (
            p["nickname"], p["role"], p["comment_count"], p["total_digg"]))
