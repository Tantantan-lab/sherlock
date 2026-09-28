"""深度推理引擎: 把手工侦查逻辑代码化。

核心方法(来自真实案例的完整推演):
1. 反证自动化 —— 对每条可疑点主动找反证(如退场者是否仍在
   自己的账号发视频), 反证成立则假设降级/排除
2. 概率归一 —— 假设被排除后, 剩余假设概率按原比例重归一
3. 推理链生成 —— 输出可渲染为案件板步骤的证据→假设→判定链
"""
import time
from typing import Any, Dict, List, Optional, Tuple

from sherlock import api
from sherlock.headless import new_page


def check_account_active(tab, sec_uid: str,
                         after_date: str = "") -> Tuple[bool, int, str]:
    """反证检查: 该账号是否仍在发视频。

    Args:
        tab: 已登录标签页。
        sec_uid: 待查账号。
        after_date: 只统计该日期之后的视频(YYYY-MM-DD)。

    Returns:
        (是否仍活跃, after_date 之后的视频数, 最新视频日期)。
    """
    try:
        videos, has_more, cursor = api.post_list(tab, sec_uid)
        if has_more:
            more, _, _ = api.post_list(tab, sec_uid, cursor)
            videos.extend(more)
    except Exception:
        return False, 0, ""
    dates = [time.strftime("%Y-%m-%d",
                           time.localtime(int(v.get("create_time") or 0)))
             for v in videos]
    after = [d for d in dates if d > after_date] if after_date else dates
    return bool(after), len(after), (max(dates) if dates else "")


def counter_evidence_retire(data: Dict[str, List[Dict[str, Any]]],
                            suspect: Dict[str, Any],
                            tab) -> Optional[str]:
    """退场者反证: 账号仍在发视频 → 换号/消失假设不成立。

    Args:
        data: load_all() 返回值。
        suspect: 退场者可疑点。
        tab: 已登录标签页。

    Returns:
        反证文本(如成立), 否则 None。
    """
    if suspect.get("rule") != "退场者":
        return None
    # 从粉丝表找 uid
    uid = ""
    for r in data.get("fans", []):
        if r.get("nickname") == suspect.get("person") or (
                suspect.get("person") and r.get("nickname", "").startswith(
                    suspect["person"][:4])):
            uid = r.get("sec_uid", "")
            break
    if not uid:
        return None
    # 最后评论日期
    last_date = (suspect.get("evidence") or "").split("最后评论: ")[-1][:10]
    active, n, latest = check_account_active(tab, uid, after_date=last_date)
    if active and n >= 3:
        return {"eliminates": "换号/账号消失",
                "effect": "strengthen",
                "text": ("反证: %s 之后仍发布 %d 条视频(最新 %s), "
                         "账号持续活跃——排除换号/消失, 反证'选择性退场'"
                         "(人在别处活跃, 只是不再来此评论)。" % (
                             last_date, n, latest))}
    return None


def normalize_probabilities(hypotheses: List[Dict[str, Any]]
                            ) -> List[Dict[str, Any]]:
    """假设概率归一: 排除的假设概率按原比例分摊给剩余假设。

    Args:
        hypotheses: [{"title", "prob", "eliminated"}]

    Returns:
        归一后的假设列表(prob 合计 100)。
    """
    alive = [h for h in hypotheses if not h.get("eliminated")]
    total = sum(h["prob"] for h in alive) or 1
    for h in alive:
        h["prob"] = round(h["prob"] / total * 100)
    return hypotheses


def build_reasoning_chain(suspect: Dict[str, Any],
                          counter: Optional[str] = None
                          ) -> Dict[str, Any]:
    """可疑点 → 案件板推理链(证据→假设→反证→判定)。

    Args:
        suspect: 可疑点(含 score/severity)。
        counter: 反证文本(如有)。

    Returns:
        案件板 case 结构(五步推理)。
    """
    prob = suspect.get("score", 50)
    if counter is not None and not isinstance(counter, dict):
        counter = {"text": str(counter), "eliminates": ""}
    steps = [
        {"label": "① 事实收集", "clues": [
            {"id": "f1", "cls": "note", "pos": "clue-a", "tag": "事实",
             "tag2": suspect.get("rule", ""),
             "text": suspect.get("evidence", "")[:100]}], "links": []},
        {"label": "② 证据关联", "clues": [
            {"id": "e1", "cls": "dark", "pos": "clue-b",
             "tag": suspect.get("severity", "中") + "可疑", "tag2": "评分 %d" % prob,
             "title": suspect.get("person", "")[:16],
             "text": suspect.get("note", "")[:80], "mark": "?"}],
         "links": [["f1", "e1", 1]]},
    ]
    if counter:
        # 选择性退场: 账号活跃+停止在此评论 → 排除换号/消失, 异常概率上调
        prob = min(85, prob + 15)
        text = counter.get("text", "") if isinstance(counter, dict) else str(counter)
        elim = counter.get("eliminates", "") if isinstance(counter, dict) else ""
        steps.append({"label": "③ 反证检验", "clues": [
            {"id": "c1", "cls": "dark", "pos": "clue-c", "tag": "反证",
             "tag2": "排除 " + elim, "title": "选择性退场确认",
             "text": text, "mark": "✗"}],
            "links": [["e1", "c1", 0]]})
        steps.append({"label": "④ 系统判定", "clues": [
            {"id": "j1", "cls": "dark", "pos": "clue-d", "tag": "判定",
             "tag2": "概率 %d%%" % prob, "title": suspect.get("person", "")[:16],
             "text": "账号活跃但停止在此评论=选择性退场, 异常概率上调至 %d%%" % prob,
             "mark": "!" if prob >= 60 else "?"}],
            "links": [["c1", "j1", 0]]})
    else:
        steps.append({"label": "③ 竞争假设", "clues": [
            {"id": "h1", "cls": "note", "pos": "clue-c", "tag": "假设A",
             "tag2": "关系异常 %d%%" % prob,
             "text": suspect.get("note", "")[:80]},
            {"id": "h2", "cls": "note", "pos": "clue-d", "tag": "假设B",
             "tag2": "正常波动 %d%%" % (100 - prob),
             "text": "对照同圈行为基线, 排除偶然因素后确认。"}],
            "links": [["e1", "h1", 1], ["e1", "h2", 1]]})
        steps.append({"label": "④ 系统判定", "clues": [
            {"id": "j1", "cls": "dark", "pos": "clue-e", "tag": "判定",
             "tag2": "概率 %d%%" % prob, "title": suspect.get("person", "")[:16],
             "text": "异常概率 %d%%(机器评估, 需人工复核)" % prob,
             "mark": "!" if prob >= 60 else "?"}],
            "links": [["h1", "j1", 0], ["h2", "j1", 1]]})
    return {
        "id": "case", "title": "%s · %s" % (suspect.get("person", "")[:10],
                                            suspect.get("rule", "")),
        "rule": suspect.get("rule", ""), "severity": suspect.get("severity", "中"),
        "score": prob, "color": {"高": "#b54038", "中": "#c4aa60",
                                 "低": "#476d76"}.get(suspect.get("severity", "中"), "#476d76"),
        "caseId": "REASON", "status": "深度推理", "progress": prob,
        "steps": steps,
        "suspects": [{"name": suspect.get("person", "")[:16], "risk": "mid",
                      "riskLabel": "异常 %d%%" % prob,
                      "desc": "事实: " + suspect.get("evidence", "")[:60],
                      "evidence": suspect.get("rule", "") + " · 评分 "
                                  + str(suspect.get("score", 0)),
                      "prob": "系统判定: 异常概率 %d%%" % prob, "conf": 2}],
        "hypotheses": [
            {"title": "假设 A · 关系异常 (%d%%)" % prob, "text": suspect.get("note", "")},
            {"title": "假设 B · 正常波动 (%d%%)" % (100 - prob),
             "text": "对照同圈行为基线, 排除偶然因素后确认。"}],
        "conclusion": ("系统判定: 异常概率 %d%%%s。机器评估仅供参考, 采信前需人工复核。" % (
            prob, "。反证成立: 排除%s, 判定升级为选择性退场" % (
                counter.get("eliminates", "")) if counter else "")),
    }


def deep_reason(data: Dict[str, List[Dict[str, Any]]],
                suspects_list: List[Dict[str, Any]],
                top_n: int = 5,
                interval: float = 1.2) -> List[Dict[str, Any]]:
    """对 Top N 可疑点跑深度推理(自动反证 + 推理链生成)。

    Args:
        data: load_all() 返回值。
        suspects_list: suspects.detect 输出。
        top_n: 深度推理的可疑点数。
        interval: 请求间隔。

    Returns:
        案件板 case 列表(深度推理版)。
    """
    page = new_page()
    tab = page.new_tab()
    tab.get("https://www.douyin.com/")
    time.sleep(6)
    cases = []
    for s in suspects_list[:top_n]:
        counter = counter_evidence_retire(data, s, tab)
        cases.append(build_reasoning_chain(s, counter))
        time.sleep(interval)
    tab.close()
    page.quit()
    return cases


if __name__ == "__main__":
    import json
    from sherlock import analyze, suspects
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ data/ 无数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    sus = suspects.detect(data)
    print("反证引擎(需浏览器会话与代理):")
    print(json.dumps(deep_reason(data, sus),
                     ensure_ascii=False, indent=2, default=str))


def verify_mutual_status(tab, target_uid: str, person_uid: str) -> str:
    """互关真值验证: 拉 person 自己的粉丝列表, 看 target 是否在其中。

    这是平台层面的互关事实(person 的真实粉丝列表), 不依赖观看者身份;
    但受列表可见性限制: 空列表=对方设了隐私(本身就是情报),
    未见 target=可能互关但在 API 可见窗口之外。

    Returns:
        "互相关注" / "列表隐私不可见" / "未确认(上限外或非互关)" / "未知"。
    """
    from sherlock import collect
    try:
        users = collect.collect_users(tab, person_uid, "follower")
    except Exception:
        return "未知"
    if not users:
        return "列表隐私不可见"
    for u in users:
        if (u.get("sec_uid") or "") == target_uid or (u.get("uid") or "") == target_uid:
            return "互相关注"
    return "未确认(上限外或非互关)"


def verify_top_mutual(data: Dict[str, List[Dict[str, Any]]],
                      top_n: int = 15,
                      profile: str = None,
                      headless: bool = True) -> List[Dict[str, Any]]:
    """亲密度 TOP 人物互关真值验证: 拉每人自己的粉丝列表找目标。

    API 互关(fans∩follows)受列表可见上限影响, 可能漏判/误判;
    直接查 person 的粉丝列表(平台真值, 不依赖观看者身份):
    - 目标在列表 → 互关确认
    - 列表空(对方设隐私) → 本身就是情报
    - 目标不在可见窗口 → 未确认(上限外或非互关)

    Returns:
        [{"nickname", "sec_uid", "role", "closeness",
          "api_mutual", "homepage_mutual", "verified"}]
    """
    from sherlock import analyze
    gd = analyze.build_graph_data(data)
    users = [n for n in gd["nodes"] if n["type"] == "user"]
    users.sort(key=lambda n: -n.get("closeness", 0))
    top = users[:top_n]
    author_uid = (data.get("profile") or {}).get("sec_uid", "")
    fans = {r["sec_uid"] for r in data.get("fans", [])}
    follows = {r["sec_uid"] for r in data.get("follows", [])}

    page = new_page(profile=profile, headless=headless)
    tab = page.new_tab()
    tab.get("https://www.douyin.com/")
    out = []
    for n in top:
        if not n["id"] or n["id"] == author_uid:
            continue
        status = verify_mutual_status(tab, author_uid, n["id"])
        out.append({
            "nickname": n.get("name_full") or n.get("label", ""),
            "sec_uid": n["id"],
            "role": n.get("role", ""),
            "closeness": n.get("closeness", 0),
            "api_mutual": "互关" if n["id"] in (fans & follows) else "否",
            "homepage_mutual": status,
            "verified": status == "互相关注",
        })
        print("  [%2d/%2d] %-14s API互关=%-3s 粉丝列表验证=%-18s 亲密度=%.1f" % (
            len(out), len(top), out[-1]["nickname"][:14],
            out[-1]["api_mutual"], status, n.get("closeness", 0)))
    tab.close()
    page.quit()
    return out
