#!/usr/bin/env python3
"""Sherlock 向导入口: 普通人只需扫码登录 + 粘贴主页链接。

用法:
    python sherlock.py            # 交互菜单
    python sherlock.py auto <sec_uid>   # 一条命令全自动(登录→采集→报告)
"""
import os
import sys

from typing import Any, Dict, List

from sherlock import analyze, collect, report, suspects, timeline


def _banner() -> None:
    print("=" * 46)
    print("  🔍 Sherlock · 抖音社交关系侦查")
    print("  登录 → 采集 → 分析 → 可疑点汇总")
    print("=" * 46)


def _menu() -> None:
    print("[1] 登录抖音(扫码一次, 之后免登录)")
    print("[2] 采集线索(粘贴主页链接, 自动全部采集)")
    print("[3] 生成侦查报告(关系+人物+可疑点+时间线)")
    print("[4] 打开线索板 / 关系图")
    print("[5] 网页入口(扫码+粘贴链接+一键侦查)")
    print("[6] 切换案件(data/cases/ 之间搬移)")
    print("[7] 互关验证(亲密度TOP逐人查首页, 需登录会话)")
    print("[q] 退出")


def step_login() -> None:
    """弹出浏览器扫码登录一次, 会话持久化。"""
    from sherlock.headless import new_page
    page = new_page(headless=False)
    tab = page.new_tab()
    tab.get("https://www.douyin.com/")
    input("请在弹出的浏览器中扫码登录, 完成后回车...")
    tab.close()
    page.quit()
    print("✅ 登录会话已保存")


def step_collect() -> None:
    url = input("粘贴目标主页链接: ").strip()
    sec_uid = url.split("/user/")[-1].split("?")[0] if "/user/" in url else url
    if not sec_uid:
        print("❌ 链接无效")
        return
    collect.main(sec_uid)


def _load_config() -> Dict[str, Any]:
    """读 config.json(可选): target_sec_uid / exclude_uids。"""
    import json
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _exclude() -> List[str]:
    exf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "排除名单.txt")
    if os.path.exists(exf):
        with open(exf, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    return [str(u).strip() for u in _load_config().get("exclude_uids", [])]


def _auto_cases(data, sus) -> List[Dict[str, Any]]:
    """可疑点 → 案件板案件: 五步自动推理链(事实→关联→反证/假设→判定)。

    复用 reason.build_reasoning_chain: 概率由可疑点评分导出,
    含签名反证等自动分析, 与旧版侦探分析的案卷深度对齐。
    """
    from sherlock.reason import build_reasoning_chain
    cases = []
    order = {"高": 0, "中": 1}
    top = sorted(sus, key=lambda s: (order.get(s["severity"], 2),
                                     -s.get("score", 0)))[:6]
    for i, s in enumerate(top, 1):
        chain = build_reasoning_chain(s)
        chain["id"] = "case-%d" % i
        chain["caseId"] = "AUTO-%02d" % i
        chain["status"] = "自动分析·待人工复核"
        cases.append(chain)
    return cases


def _save_extras(data, exclude: List[str]):
    """人物档案全表 CSV + 评论内容分析(主题/情感) MD。"""
    import csv as _csv
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "analysis_output")
    os.makedirs(out, exist_ok=True)
    profs = analyze.person_profiles(data, exclude_uids=exclude)
    pp = os.path.join(out, "人物档案表.csv")
    if profs:
        with open(pp, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=list(profs[0].keys()))
            w.writeheader()
            w.writerows(profs)
    topics = analyze.content_topics(data.get("comments", []),
                                    exclude_uids=exclude)
    sent = topics.get("sentiment", {})
    lines = ["# 📝 评论内容分析", "",
             "## 情感分布",
             "- 正面 %d%% · 中性 %d%% · 负面 %d%%" % (
                 sent.get("positive", 0), sent.get("neutral", 0),
                 sent.get("negative", 0)), ""]
    if topics.get("topics"):
        lines += ["## 主题聚类"] + [
            "- 主题%d: %s" % (i + 1, " / ".join(t))
            for i, t in enumerate(topics["topics"])]
    else:
        lines += ["## 主题聚类", "评论量不足(<10 条), 跳过 LDA 聚类。"]
    if topics.get("positive_samples"):
        lines += ["", "正面样例: %s" % " / ".join(
            "「%s」(%.2f)" % (t, s) for s, t in topics["positive_samples"])]
    if topics.get("negative_samples"):
        lines += ["负面样例: %s" % " / ".join(
            "「%s」(%.2f)" % (t, s) for s, t in topics["negative_samples"])]
    cp = os.path.join(out, "评论内容分析.md")
    with open(cp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return pp, cp


def step_report() -> None:
    from sherlock import board, graph
    import webbrowser
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ 没有数据, 请先执行 [2] 采集线索")
        return
    exclude = _exclude()
    md = report.build_report(data, exclude_uids=exclude)
    rp = report.save_report(md)
    sus = suspects.detect(data, exclude_uids=exclude)
    gd = analyze.build_graph_data(data, exclude_uids=exclude)
    gp = graph.render_sherlock(gd)
    cases = _auto_cases(data, sus)
    bp = board.render_cases(cases, graph_link="福尔摩斯线索墙.html")
    pp, cp = _save_extras(data, exclude)
    from sherlock import organize as org
    conv = org.build_conversations(data["comments"],
                                   data.get("replies", []),
                                   data.get("videos", []))
    tl = org.build_timeline(data.get("videos", []), data["comments"])
    hl = org.build_highlights(data["comments"])
    dp = org.render_dossier(conv, tl, hl)
    tp = org.render_timeline(org.build_timeline_analysis(
        data.get("videos", []), data["comments"]))
    # JSON 产物(沿用旧项目约定: graph_all.json 全维度图数据, cases.json 案卷)
    import json as _json
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "analysis_output")
    jg = os.path.join(out, "graph_all.json")
    with open(jg, "w", encoding="utf-8") as f:
        _json.dump(gd, f, ensure_ascii=False, indent=1)
    jc = os.path.join(out, "cases.json")
    with open(jc, "w", encoding="utf-8") as f:
        _json.dump(cases, f, ensure_ascii=False, indent=1)
    # 每个用户一份独立目录: 全部产物 + g6.min.js + 数据副本
    import shutil
    case = analyze.case_name(data) or "case"
    cdir = os.path.join(out, "cases", case)
    os.makedirs(cdir, exist_ok=True)
    for f in (rp, gp, bp, pp, cp, dp, tp, jg, jc):
        if os.path.exists(f):
            shutil.copy(f, os.path.join(cdir, os.path.basename(f)))
    g6 = os.path.join(out, "g6.min.js")
    if os.path.exists(g6):
        shutil.copy(g6, cdir)
    # 用户目录里的数据以 JSON 落盘(原始 CSV 仍以 data/cases 为准)
    with open(os.path.join(cdir, "data.json"), "w", encoding="utf-8") as f:
        _json.dump({"videos": data.get("videos", []),
                    "comments": data.get("comments", []),
                    "replies": data.get("replies", []),
                    "fans": data.get("fans", []),
                    "follows": data.get("follows", []),
                    "profile": data.get("profile", {})},
                   f, ensure_ascii=False, indent=1)
    print("✅ 侦查报告:", rp)
    print("✅ 线索墙:  ", gp)
    print("✅ 案件板:  ", bp)
    print("✅ 人物档案:", pp)
    print("✅ 内容分析:", cp)
    print("✅ 情报整理:", dp)
    print("✅ 时间线分析:", tp)
    print("✅ 图数据:  ", jg)
    print("✅ 案卷JSON:", jc)
    print("✅ 用户目录:", cdir)
    print("   可疑点 %d 条(高%d 中%d 低%d), 已自动生成 %d 个案卷" % (
        len(sus),
        sum(1 for s in sus if s["severity"] == "高"),
        sum(1 for s in sus if s["severity"] == "中"),
        sum(1 for s in sus if s["severity"] == "低"),
        len(cases)))
    webbrowser.open("file://" + bp)


def _data_dirs() -> tuple:
    """(data 目录, cases 目录)。"""
    base = os.path.dirname(os.path.abspath(__file__))
    return (os.path.join(base, "data"),
            os.path.join(base, "data", "cases"))


def _move_batch(src: str, dst: str) -> None:
    """案件数据文件(data.json)在两目录间搬移, 兼容遗留 CSV。"""
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if f == "data.json" or f.endswith(".csv"):
            os.rename(os.path.join(src, f), os.path.join(dst, f))


def step_case() -> None:
    """切换活跃案件: data/ 与 data/cases/<name>/ 之间搬移 CSV 批次。"""
    data_dir, cases_dir = _data_dirs()
    if not os.path.isdir(cases_dir):
        print("❌ data/cases/ 不存在")
        return
    marker = os.path.join(data_dir, ".active_case")
    cur = open(marker).read().strip() if os.path.exists(marker) else ""
    names = sorted(n for n in os.listdir(cases_dir)
                   if os.path.isdir(os.path.join(cases_dir, n)))
    print("当前案件:", cur or "(无标记)")
    print("可选案件: " + " / ".join(names))
    name = input("切换到哪个案件(输入名字或留空取消): ").strip()
    if not name:
        return
    if name not in names:
        print("❌ 案件不存在(可用: %s)" % " / ".join(names))
        return
    if name == cur:
        print("已经是该案件")
        return
    src = os.path.join(cases_dir, name)
    if not os.path.isdir(src):
        print("❌ 案件目录不存在:", name)
        return
    if cur:
        _move_batch(data_dir, os.path.join(cases_dir, cur))
    _move_batch(src, data_dir)
    with open(marker, "w") as f:
        f.write(name)
    print("✅ 已切换到:", name, "→ 跑菜单 [3] 生成全部产物")


def step_verify() -> None:
    """亲密度 TOP 人物逐人访问主页, 用首页按钮验证互关并落盘。"""
    from sherlock import analyze
    from sherlock.reason import verify_top_mutual
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ 没有数据, 请先执行 [2] 采集线索")
        return
    rows = verify_top_mutual(data, top_n=15)
    if not rows:
        print("❌ 无可验证人物")
        return
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "analysis_output", "互关验证.csv")
    import csv as _csv
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    diffs = [r for r in rows if r["api_mutual"] != ("互关" if r["verified"] else "否")]
    print("✅ 互关验证:", out, "| API 与首页结论不一致 %d 人" % len(diffs))
    for r in diffs:
        print("  ⚠️ %s: API=%s 首页=%s" % (r["nickname"], r["api_mutual"],
                                           r["homepage_mutual"]))


def step_open() -> None:
    from sherlock import board, graph
    import webbrowser
    demo = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "demo_cases.json")
    if os.path.exists(demo):
        import json
        cases = json.load(open(demo, encoding="utf-8"))
        p = board.render_cases(cases)
        webbrowser.open("file://" + p)
        print("✅ 线索板已打开:", p)
    else:
        print("⚠️ 未找到 demo_cases.json")


def auto(sec_uid: str) -> None:
    """一条命令全自动。"""
    collect.main(sec_uid)
    step_report()


def demo() -> None:
    """演示模式: 用内置虚构数据集(demo_data.json)跑完整流程, 无需登录/采集。"""
    import shutil
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "demo_data.json")
    if not os.path.exists(src):
        print("❌ 缺少 demo_data.json")
        return
    data_dir, _ = _data_dirs()
    os.makedirs(data_dir, exist_ok=True)
    shutil.copy(src, os.path.join(data_dir, "data.json"))
    print("✅ 已载入演示数据(虚构账号「林小满」), 开始生成...")
    step_report()


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "auto":
        auto(sys.argv[2])
        return
    if len(sys.argv) == 2 and sys.argv[1] == "auto":
        sec = _load_config().get("target_sec_uid", "").strip()
        if sec:
            auto(sec)
            return
        print("❌ 未提供 sec_uid, 且 config.json 中没有 target_sec_uid")
        return
    if len(sys.argv) == 2 and sys.argv[1] == "demo":
        demo()
        return
    while True:
        _banner()
        _menu()
        choice = input("选择: ").strip().lower()
        if choice == "1":
            step_login()
        elif choice == "2":
            step_collect()
        elif choice == "3":
            step_report()
        elif choice == "4":
            step_open()
        elif choice == "5":
            from sherlock import web
            web.main()
        elif choice == "6":
            step_case()
        elif choice == "7":
            step_verify()
        elif choice in ("q", "quit", "exit", ""):
            print("再见。")
            break
        else:
            print("❌ 无效选择")


if __name__ == "__main__":
    main()
