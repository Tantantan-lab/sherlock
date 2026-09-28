"""侦探报告汇总: 关系分析 + 人物档案 + 可疑点 + 时间线 → Markdown。

这是"福尔摩斯式整理流程"的终点: 把全部线索按证据强度
编排成一份可读的调查报告。
"""
import os
from typing import Any, Dict, List, Optional

from sherlock import analyze, suspects, timeline

_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "analysis_output")


def _h2(title: str) -> str:
    return "\n## %s\n" % title


def build_report(data: Dict[str, List[Dict[str, Any]]],
                 exclude_uids: Optional[List[str]] = None,
                 target_fans: int = 0) -> str:
    """生成完整侦探报告(Markdown 文本)。

    Args:
        data: load_all() 返回值。
        exclude_uids: 排除名单。
        target_fans: 目标账号粉丝数(大V阈值用)。

    Returns:
        Markdown 报告全文。
    """
    rel = analyze.relationship_report(data, exclude_uids)
    profiles = analyze.person_profiles(data, exclude_uids)
    sus = suspects.detect(data, exclude_uids, target_fans)
    tl = timeline.reconstruct(data.get("videos", []), data.get("comments", []))

    parts = ["# 🕵️ 社交关系侦查报告", "",
             "> 生成方式: 公开数据交叉推演 · 仅供研究参考", ""]

    parts.append(_h2("一、总体关系"))
    prof = data.get("profile") or {}
    parts.append("- 主页公开计数: 关注 %s / 粉丝 %s / 获赞 %s" % (
        prof.get("follows_count", "?"), prof.get("fans_count", "?"),
        prof.get("likes_count", "?")))
    parts.append("- 可见列表: 粉丝 %d / 关注 %d / 评论者 %d" % (
        rel["fans"], rel["follows"], rel["commenters"]))
    parts.append("- **核心互动粉(粉丝∩评论者): %d** · 互关: %d" % (
        rel["core_fans"], rel["mutual"]))
    parts.append("- 评论高峰时段: %s" % " / ".join(
        "%d时(%d)" % (h, n) for h, n in rel["top_hours"][:4]))
    parts.append("- IP 属地 TOP: %s" % " / ".join(
        "%s(%d)" % (p, n) for p, n in rel["top_ips"][:4]))
    parts.append("")

    parts.append(_h2("二、人物档案 TOP10"))
    for p in profiles[:10]:
        parts.append("- **%s** [%s]: 评论%d · 获赞%d · 覆盖%d视频 · 高峰%s · %s" % (
            p["nickname"], p["role"], p["comment_count"], p["total_digg"],
            p["videos_covered"], p["peak_hours"], p["ip_label"]))
    parts.append("")

    parts.append(_h2("三、可疑点清单(%d 条)" % len(sus)))
    if not sus:
        parts.append("未检测到可疑点。")
    for s in sus:
        parts.append("- 【%s·%s】**%s**: %s" % (
            s["severity"], s["rule"], s["person"], s["note"]))
        parts.append("  > 证据: %s" % s["evidence"])
    parts.append("")

    parts.append(_h2("四、时间线还原"))
    for e in tl["events"][:20]:
        parts.append("- [%s] %s — %s" % (e[0], e[1], e[2]))
    parts.append("")
    for name, start, basis in tl["phases"]:
        parts.append("- %s: 自 %s(%s)" % (name, start, basis))
    return "\n".join(parts)


def save_report(markdown: str, out_path: str = "") -> str:
    """报告落盘, 返回绝对路径。"""
    os.makedirs(_OUT_DIR, exist_ok=True)
    target = out_path or os.path.join(_OUT_DIR, "侦查报告.md")
    with open(target, "w", encoding="utf-8") as f:
        f.write(markdown)
    return os.path.abspath(target)
