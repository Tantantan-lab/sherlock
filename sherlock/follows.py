"""关注方向分析: 从目标的关注列表反推其兴趣方向。

方法论: 关注列表的昵称+签名是兴趣信号——按关键词分类后
统计方向分布, 即"这个人目前在看什么"。
"""
from collections import Counter
from typing import Any, Dict, List, Optional

# 方向关键词库(昵称+签名匹配)
_DIRECTIONS = (
    ("游戏/二次元", ("游戏", "电竞", "原神", "王者", "动漫", "二次元", "cos",
                     "捏脸", "番剧", "steam", "诡秘")),
    ("美妆/穿搭", ("妆", "穿搭", "搭配", "时尚", "口红", "发型", "美瞳", "护肤")),
    ("医美/整形", ("整形", "医美", "美容", "泪沟", "眼袋", "变美", "美学")),
    ("摄影/美学", ("摄影", "拍照", "写真", "头像", "壁纸", "滤镜", "plog",
                   "氛围感", "随手拍")),
    ("美食/探店", ("美食", "探店", "烘焙", "做饭", "火锅", "奶茶")),
    ("宠物/萌宠", ("宠物", "猫", "狗", "萌宠", "铲屎官", "边牧")),
    ("健身/运动", ("健身", "减脂", "瑜伽", "跑步", "滑雪", "极限运动", "户外")),
    ("情感/语录", ("情感", "语录", "治愈", "文案", "心灵", "情绪")),
    ("知识/学习", ("学习", "教育", "知识", "课程", "老师", "职场", "考研")),
    ("财经/股票", ("股票", "财经", "基金", "投资", "理财", "交易")),
    ("母婴/育儿", ("母婴", "育儿", "宝宝", "萌娃")),
    ("搞笑/娱乐", ("搞笑", "娱乐", "段子", "剧情", "短剧", "综艺")),
)


def follow_directions(data: Dict[str, List[Dict[str, Any]]],
                      top_n: int = 10) -> Dict[str, Any]:
    """关注列表 → 兴趣方向分布。

    Args:
        data: load_all() 返回值。
        top_n: 分布 TOP 数量。

    Returns:
        {"distribution": [(方向, 人数)], "unclassified": 未分类人数,
         "big_accounts": 关注里的大号 TOP5, "rows": 每关注的方向明细}
    """
    follows = data.get("follows", [])
    dist = Counter()
    rows = []
    for r in follows:
        text = "%s %s" % (r.get("nickname", "") or "", r.get("signature", "") or "")
        hit = None
        for d, kws in _DIRECTIONS:
            if any(k in text for k in kws):
                hit = d
                break
        dist[hit or "未分类"] += 1
        rows.append({"nickname": r.get("nickname", ""),
                     "signature": (r.get("signature", "") or "")[:40],
                     "follower_count": int(r.get("follower_count") or 0),
                     "direction": hit or "未分类"})
    big = sorted(rows, key=lambda x: -x["follower_count"])[:5]
    return {"distribution": dist.most_common(top_n),
            "unclassified": dist.get("未分类", 0),
            "big_accounts": big,
            "rows": rows}


if __name__ == "__main__":
    import json
    from sherlock import analyze
    data = analyze.load_all()
    if not data.get("follows"):
        print("❌ data/ 无关注数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    res = follow_directions(data)
    print("关注方向分布:")
    for d, n in res["distribution"]:
        print("  %-10s %d 人" % (d, n))
    print("未分类 %d 人; 大号 TOP:" % res["unclassified"])
    for b in res["big_accounts"]:
        print("  %s (%d 粉) %s" % (b["nickname"], b["follower_count"],
                                   b["direction"]))
