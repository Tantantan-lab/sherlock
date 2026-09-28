"""情报整理: 把采集数据整理成可读档案(对话流/时间线/细节标注)。

方法论: 收集是原材料, 整理才是情报——对话按"线程"归组还原
聊天现场, 时间线以视频为锚点重建经历, 细节标注用荧光笔
划出暴露关系的称呼与情绪信号。
"""
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "analysis_output")

# 细节标注关键词组: 称呼(暴露关系) / 情绪(事件信号) / 事件(生活节点)
_HIGHLIGHTS = {
    "称呼": ("师妹", "学妹", "学姐", "学长", "宝宝", "宝贝", "老婆",
             "姐妹", "舍友", "室友", "师兄", "师弟", "紫啧"),
    "情绪": ("爱你", "想你", "眼泪", "独白", "委屈", "难过", "舍不得",
             "荒谬", "好久不见", "戒断", "回忆"),
    "事件": ("毕业", "上班", "生日", "开学", "放假", "离职", "实验室",
             "科研", "演唱会"),
}
# 时间线事件标签色
_EVENT_COLORS = {"毕业": "#b54038", "上班": "#c4aa60", "生日": "#d4a017",
                 "开学": "#476d76", "放假": "#476d76", "留校": "#476d76",
                 "离职": "#b54038"}


def _fmt_ts(ts: int) -> str:
    if not ts:
        return "?"
    return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")


def build_conversations(comments: List[Dict[str, Any]],
                        replies: List[Dict[str, Any]],
                        videos: Optional[List[Dict[str, Any]]] = None
                        ) -> List[Dict[str, Any]]:
    """评论 → 对话线程(主评论 + 缩进回复), 按时间倒序。

    Args:
        comments: 采集的主评论列表。
        replies: 采集的回复链列表。
        videos: 视频列表(可选), 提供时每条线程附带视频标题/日期/链接。

    Returns:
        线程列表, 每条: {main, replies, video_title, video_date,
        video_id}(video_* 仅在传入 videos 时存在)。
    """
    meta = {v.get("id"): v for v in (videos or [])}
    main = {r["comment_id"]: r for r in comments if r.get("comment_id")}
    threads: Dict[str, Dict[str, Any]] = {}
    for r in comments:
        cid = r.get("comment_id")
        if not cid:
            continue
        v = meta.get(r.get("video_id"))
        threads[cid] = {"main": r, "replies": [],
                        "video_title": (v or {}).get("title", "")[:48],
                        "video_date": _fmt_ts((v or {}).get("create_time") or 0)
                        if v else "",
                        "video_id": r.get("video_id", "")}
    for r in replies:
        cid = r.get("main_comment_id")
        if cid in threads:
            threads[cid]["replies"].append(r)
    for t in threads.values():
        t["replies"].sort(key=lambda r: r.get("created_at", ""))
    out = sorted(threads.values(),
                 key=lambda t: t["main"].get("created_at", ""), reverse=True)
    return out


def build_timeline(videos: List[Dict[str, Any]],
                   comments: List[Dict[str, Any]]
                   ) -> List[Dict[str, Any]]:
    """时间线: 视频为锚点 + 事件标签 + 当日评论。

    Args:
        videos: 视频列表(create_time/title)。
        comments: 主评论列表(按视频ID 归到对应锚点)。

    Returns:
        按时间正序的锚点列表。
    """
    by_video = defaultdict(list)
    for r in comments:
        if r.get("video_id"):
            by_video[r["video_id"]].append(r)
    out = []
    for v in sorted(videos, key=lambda x: int(x.get("create_time") or 0)):
        title = v.get("title", "") or ""
        tags = [{"label": k, "color": c} for k, c in _EVENT_COLORS.items()
                if k in title]
        day_coms = sorted(by_video.get(v.get("id"), []),
                          key=lambda r: r.get("created_at", ""))
        out.append({
            "date": _fmt_ts(v.get("create_time") or 0),
            "title": title,
            "video_id": v.get("id", ""),
            "tags": tags,
            "comments": day_coms[:6],
            "n_comments": len(day_coms),
        })
    return out


def build_highlights(comments: List[Dict[str, Any]]
                     ) -> Dict[str, List[Dict[str, Any]]]:
    """细节标注: 关键词组命中, 输出荧光笔片段。

    Returns:
        {组名: [{评论人, 时间, 片段(命中词已加<<>>标记), 命中词}]}
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for group, words in _HIGHLIGHTS.items():
        hits = []
        for r in comments:
            text = r.get("comment_text") or ""
            for w in words:
                if w in text:
                    marked = text.replace(w, "<<" + w + ">>")
                    hits.append({"who": r.get("nickname", ""),
                                 "time": (r.get("created_at") or "")[:10],
                                 "marked": marked[:80],
                                 "word": w})
                    break
        hits.sort(key=lambda h: h["time"])
        out[group] = hits
    return out


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>🔍 情报整理档案</title>
<style>
  body{margin:0;background:radial-gradient(circle at 50% -15%,#35291f 0,#181411 48%,#0d0b09 100%);color:#e8d5b5;font-family:Georgia,'Songti SC',serif}
  header{padding:14px 28px;border-bottom:1px solid rgba(220,195,143,.22);display:flex;align-items:center;gap:18px;background:rgba(16,14,12,.8);position:sticky;top:0;z-index:9}
  header h1{font-size:17px;letter-spacing:.14em;color:#d4a017;margin:0}
  .tabs{display:flex;gap:6px}
  .tab{border:1px solid #574534;background:#211b16;color:#9a8c79;padding:8px 16px;border-radius:3px;font-size:12px;cursor:pointer;letter-spacing:.08em}
  .tab.active{color:#f1d28f;border-color:#97763e;background:#33281c}
  main{max-width:860px;margin:0 auto;padding:24px 20px 60px}
  .panel{display:none}.panel.active{display:block}
  .filterbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}
  .chip{border:1px solid #4b3d30;background:#1b1612;color:#bfb29c;padding:6px 12px;border-radius:14px;font-size:12px;cursor:pointer}
  .chip.on{background:#493929;color:#f1d28f;border-color:#97763e}
  .thread{border:1px solid #342c24;background:#17130f;border-radius:5px;padding:14px 16px;margin-bottom:14px}
  .c-main{display:flex;gap:10px;align-items:flex-start}
  .ava{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;font-size:14px;color:#251f18;flex:none}
  .meta{font:10px Arial;color:#8f816d}
  .text{font-size:13.5px;line-height:1.6;margin-top:4px}
  .reply{margin:10px 0 0 44px;padding:9px 12px;border-left:2px solid #4b3d30;background:#14100c;border-radius:0 4px 4px 0;font-size:12.5px}
  .reply .who{color:#c7a45e;font-size:12px}
  .tl-item{border-left:2px solid #4b3d30;padding:0 0 22px 20px;position:relative}
  .tl-item:before{content:"";position:absolute;left:-7px;top:6px;width:12px;height:12px;border-radius:50%;background:#d4a017;box-shadow:0 0 0 3px rgba(212,160,23,.2)}
  .tl-date{font:11px Arial;letter-spacing:.12em;color:#8f816d}
  .tl-title{font-size:14px;margin:5px 0}
  .tag{display:inline-block;font:10px Arial;padding:2px 7px;border-radius:3px;margin-right:5px;color:#fff}
  .tl-com{font-size:11.5px;color:#9a8c79;line-height:1.7;margin-top:7px}
  .hl-group{margin-bottom:24px}
  .hl-group h2{font-size:14px;color:#c7a45e;letter-spacing:.1em;border-bottom:1px solid #3b3027;padding-bottom:8px}
  .hl-item{font-size:12.5px;line-height:1.7;padding:7px 0;border-bottom:1px dashed #2f2821}
  .hl-item mark{background:#5a3a1c;color:#ffd88a;padding:0 3px;border-radius:2px}
  .hl-item .m{font:10px Arial;color:#8f816d;margin-right:8px}
</style></head><body>
<header><h1>🔍 情报整理档案</h1><span class="navlinks">
    <a href="贝克街案件分析室_v2.html" style="color:#d4a017;text-decoration:none;margin:0 10px;font-size:12px;letter-spacing:.1em">📁 案件板</a>
    <a href="福尔摩斯线索墙.html" style="color:#d4a017;text-decoration:none;margin:0 10px;font-size:12px;letter-spacing:.1em">🕸️ 关系图</a>
    <a href="情报整理.html" style="color:#d4a017;text-decoration:none;margin:0 10px;font-size:12px;letter-spacing:.1em">📚 整理档案</a>
  </span>
  <div class="tabs">
    <button class="tab active" data-tab="chat">💬 对话流</button>
    <button class="tab" data-tab="timeline">📜 时间线</button>
    <button class="tab" data-tab="detail">🔦 细节标注</button>
  </div>
</header>
<main>
  <div class="panel active" id="chat">
    <div class="filterbar" id="personFilter"></div>
    <div id="chatList"></div>
  </div>
  <div class="panel" id="timeline"><div id="tlList"></div></div>
  <div class="panel" id="detail"><div id="hlList"></div></div>
</main>
<script>
const DATA = __DATA__;
const PALETTE = ['#a93226','#6d8fae','#7a8a5a','#b5651d','#5d6d7e','#8f6dae','#4f8a8b','#9a7b4f'];
let nameColor = {};
function colorOf(name){ if(!nameColor[name]) nameColor[name]=PALETTE[Object.keys(nameColor).length%PALETTE.length]; return nameColor[name]; }
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// 对话流
let filterNames = new Set();
function renderFilter(){
  const counts = {};
  DATA.conversations.forEach(t => {
    counts[t.main['nickname']] = (counts[t.main['nickname']]||0)+1;
    t.replies.forEach(r => counts[r['reply_nickname']] = (counts[r['reply_nickname']]||0)+1);
  });
  const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,14).map(e=>e[0]);
  filterNames.forEach(n => { if (counts[n] && !top.includes(n)) top.push(n); });
  const bar = document.getElementById('personFilter');
  bar.innerHTML = top.map(n =>
    '<span class="chip'+(filterNames.has(n)?' on':'')+'" data-n="'+esc(n)+'">'+esc(n)+' ('+counts[n]+')</span>').join('');
  bar.querySelectorAll('.chip').forEach(ch => ch.onclick = () => {
    filterNames.has(ch.dataset.n) ? filterNames.delete(ch.dataset.n) : filterNames.add(ch.dataset.n);
    renderFilter(); renderChat();
  });
}
function renderChat(){
  const box = document.getElementById('chatList');
  let html = '';
  let shown = 0;
  DATA.conversations.forEach(t => {
    const m = t.main;
    const inFilter = !filterNames.size
      || filterNames.has(m['nickname'])
      || t.replies.some(r => filterNames.has(r['reply_nickname']));
    if (!inFilter) return;
    shown++;
    html += '<div class="thread">'
      + (t.video_id ? '<div class="meta" style="margin-bottom:8px">📹 <a href="https://www.douyin.com/video/'+encodeURIComponent(t.video_id)+'" target="_blank" style="color:#d4a017">'
        + esc(t.video_title||'') + '</a> · ' + (t.video_date||'') + '</div>' : '')
      + '<div class="c-main">'
      + '<div class="ava" style="background:'+colorOf(m['nickname'])+'">'+ esc(m['nickname']||'?')[0] +'</div>'
      + '<div><div class="meta">'+ (m['created_at']||'').slice(5,16) +' · '+esc(m['ip_label']||'')
      + (m['douyin_id'] ? ' · 抖音号 '+esc(m['douyin_id']) : '')
      + ' · 赞'+(m['digg_count']||0)+'</div>'
      + '<div class="text">'+ esc(m['comment_text']||'') +'</div></div></div>';
    t.replies.forEach(r => {
      html += '<div class="reply"><span class="who">'+esc(r['reply_nickname'])+'</span> '
        + '<span class="meta">'+(r['created_at']||'').slice(5,16)+' → '+esc(r['reply_to']||'')+'</span>'
        + '<div class="text">'+esc(r['reply_text']||'')+'</div></div>';
    });
    html += '</div>';
  });
  box.innerHTML = html || '<p style="color:#8f816d">无匹配对话(点上方人物芯片过滤)</p>';
}

// 时间线
function renderTimeline(){
  const box = document.getElementById('tlList');
  box.innerHTML = DATA.timeline.map(t =>
    '<div class="tl-item"><div class="tl-date">'+t.date+'</div>'
    + '<div class="tl-title"><a href="https://www.douyin.com/video/'+encodeURIComponent(t.video_id)+'" target="_blank" style="color:#e8d5b5;text-decoration:none;border-bottom:1px dashed #6b5739">'+esc(t.title)+'</a> '
    + (t.tags||[]).map(g => '<span class="tag" style="background:'+g.color+'">'+g.label+'</span>').join('')
    + '</div><div class="tl-com">' + (t.comments||[]).slice(0,4).map(c =>
      '<div>· '+esc(c['nickname'])+': '+esc(((c['comment_text']||'')||'[表情]')).slice(0,44)+'</div>').join('')
    + (t.n_comments > 4 ? '<div>… 共 '+t.n_comments+' 条评论</div>' : '')
    + '</div></div>').join('');
}

// 细节标注
function renderHighlights(){
  const box = document.getElementById('hlList');
  box.innerHTML = Object.entries(DATA.highlights).map(([g, hits]) =>
    '<div class="hl-group"><h2>'+g+' ('+hits.length+')</h2>'
    + hits.slice(-40).map(h =>
      '<div class="hl-item"><span class="m">'+esc(h.time)+' '+esc(h.who)+'</span>'
      + esc(h.marked).replace(/&lt;&lt;(.*?)&gt;&gt;/g, '<mark>$1</mark>') +'</div>').join('')
    + '</div>').join('');
}

document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab,.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById(t.dataset.tab).classList.add('active');
});
// 从关系图节点跳转: #who=<昵称> 自动按人筛选对话
function hasName(n){
  return DATA.conversations.some(t => t.main['nickname'] === n
    || t.replies.some(r => r['reply_nickname'] === n));
}
try {
  const m = decodeURIComponent(location.hash || '').match(/#who=(.*)/);
  if (m && m[1]) {
    if (hasName(m[1])) filterNames.add(m[1]);
    else document.getElementById('chatList').innerHTML =
      '<p style="color:#8f816d">该用户暂无评论/对话记录(粉丝/关注列表用户不发言)</p>';
  }
} catch (e) {}
renderFilter(); renderChat(); renderTimeline(); renderHighlights();
</script></body></html>"""


_TL_TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>📜 时间线分析</title>
<style>
  body{margin:0;background:radial-gradient(circle at 50% -15%,#35291f 0,#181411 48%,#0d0b09 100%);color:#e8d5b5;font-family:Georgia,'Songti SC',serif}
  header{padding:12px 28px;border-bottom:1px solid rgba(220,195,143,.22);display:flex;align-items:center;gap:16px;background:rgba(16,14,12,.85);position:sticky;top:0;z-index:9}
  header h1{font-size:16px;letter-spacing:.14em;color:#d4a017;margin:0}
  header a{color:#d4a017;text-decoration:none;margin:0 8px;font-size:12px;letter-spacing:.1em}
  main{max-width:780px;margin:0 auto;padding:30px 20px 80px}
  .tl{border-left:2px solid #4b3d30;padding-left:22px}
  .item{position:relative;margin-bottom:26px}
  .item:before{content:"";position:absolute;left:-29px;top:7px;width:12px;height:12px;border-radius:50%;background:#d4a017;box-shadow:0 0 0 3px rgba(212,160,23,.2)}
  .date{font:11px Arial;letter-spacing:.12em;color:#8f816d}
  .title{font-size:14.5px;margin:5px 0;line-height:1.5}
  .title a{color:#e8d5b5;text-decoration:none;border-bottom:1px dashed #6b5739}
  .tag{display:inline-block;font:10px Arial;padding:2px 7px;border-radius:3px;margin-right:5px;color:#fff}
  .emo{display:inline-block;font:10px Arial;padding:2px 7px;border-radius:3px;margin-right:5px;background:#5a3a1c;color:#ffd88a}
  .snap{font:11px Arial;color:#9a8c79;margin-top:7px;line-height:1.8}
  .snap b{color:#c7a45e;font-weight:400}
  .note{margin-top:8px;padding:9px 12px;border-left:2px solid #a8322d;background:#16110d;font-size:12px;color:#b6a991;line-height:1.7}
  .note b{color:#d96a5f;font-weight:400}
  .quote{font-style:italic;color:#8a7d6b;font-size:11.5px;margin-top:5px}
</style></head><body>
<header><h1>📜 时间线分析</h1>
  <a href="贝克街案件分析室_v2.html">📁 案件板</a>
  <a href="福尔摩斯线索墙.html">🕸️ 关系图</a>
  <a href="情报整理.html">📚 整理档案</a>
  <a href="时间线分析.html">📜 时间线分析</a>
  <span style="color:#8f816d;font-size:11px">数据快照 · 首现/淡出 · 情绪标注 · 侦探批注</span>
</header><main><div class="tl" id="tl"></div></main>
<script>
const DATA = __TLDATA__;
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
const box = document.getElementById('tl');
box.innerHTML = DATA.map(t => {
  let s = '<div class="item"><div class="date">' + t.date + '</div>'
    + '<div class="title"><a href="https://www.douyin.com/video/' + t.video_id + '" target="_blank">' + esc(t.title) + '</a></div>';
  (t.tags || []).forEach(g => s += '<span class="tag" style="background:' + g.color + '">' + g.label + '</span>');
  (t.emotion_hit || []).forEach(w => s += '<span class="emo">情绪: ' + esc(w) + '</span>');
  s += '<div class="snap"><b>' + t.n_comments + '</b> 条评论';
  if (t.firsts && t.firsts.length) s += ' · <b>首现:</b> ' + t.firsts.map(esc).join('、');
  if (t.lasts && t.lasts.length) s += ' · <b>淡出:</b> ' + t.lasts.map(esc).join('、');
  s += '</div>';
  (t.quotes || []).forEach(q => s += '<div class="quote">「' + esc(q) + '」</div>');
  if (t.note) s += '<div class="note"><b>🔍 批注</b> · ' + esc(t.note) + '</div>';
  return s + '</div>';
}).join('');
</script></body></html>"""


def render_timeline(items: List[Dict[str, Any]],
                    out_path: str = "") -> str:
    """渲染时间线分析页。

    Args:
        items: build_timeline_analysis 返回值。
        out_path: 输出路径, 默认 analysis_output/时间线分析.html。

    Returns:
        生成的 HTML 文件绝对路径。
    """
    os.makedirs(_OUT_DIR, exist_ok=True)
    target = out_path or os.path.join(_OUT_DIR, "时间线分析.html")
    html = _TL_TEMPLATE.replace("__TLDATA__",
                                json.dumps(items, ensure_ascii=False).replace("</", "<\\/"))
    with open(target, "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.abspath(target)


def render_dossier(conversations: List[Dict[str, Any]],
                   timeline: List[Dict[str, Any]],
                   highlights: Dict[str, List[Dict[str, Any]]],
                   out_path: str = "") -> str:
    """渲染情报整理档案单页 HTML(对话流/时间线/细节标注)。

    Args:
        conversations: build_conversations 返回值。
        timeline: build_timeline 返回值。
        highlights: build_highlights 返回值。
        out_path: 输出路径, 默认 analysis_output/情报整理.html。

    Returns:
        生成的 HTML 文件绝对路径。
    """
    os.makedirs(_OUT_DIR, exist_ok=True)
    target = out_path or os.path.join(_OUT_DIR, "情报整理.html")
    data = {"conversations": conversations, "timeline": timeline,
            "highlights": highlights}
    html = _TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    with open(target, "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.abspath(target)

def build_timeline_analysis(videos: List[Dict[str, Any]],
                            comments: List[Dict[str, Any]]
                            ) -> List[Dict[str, Any]]:
    """时间线分析: 每锚点 = 数据快照 + 关键动作 + 侦探批注。

    Args:
        videos: 视频列表(锚点)。
        comments: 主评论列表。

    Returns:
        按时间正序的锚点列表, 每项含:
        date/title/video_id/tags/emotion_hit/n_comments/
        first_seen(该日首次出现的人)/quotes(名场面)/note(批注)。
    """
    first_day: Dict[str, str] = {}
    last_day: Dict[str, str] = {}
    for r in sorted(comments, key=lambda x: x.get("created_at", "")):
        u, d = r.get("sec_uid"), (r.get("created_at") or "")[:10]
        if not u or not d:
            continue
        if u not in first_day:
            first_day[u] = d
        last_day[u] = d
    name_map = {}
    for r in comments:
        if r.get("sec_uid"):
            name_map.setdefault(r["sec_uid"], r.get("nickname", ""))

    by_video = defaultdict(list)
    for r in comments:
        if r.get("video_id"):
            by_video[r["video_id"]].append(r)

    _EMOTION = ("爱你", "想你", "眼泪", "独白", "委屈", "难过", "错了",
                "舍不得", "荒谬", "温柔", "覆水", "好久不见", "回忆")
    out = []
    for v in sorted(videos, key=lambda x: int(x.get("create_time") or 0)):
        date = _fmt_ts(v.get("create_time") or 0)
        title = v.get("title", "") or ""
        day_coms = by_video.get(v.get("id"), [])
        firsts = [name_map.get(u, "?") for u, d in first_day.items()
                  if d == date][:4]
        lasts = [name_map.get(u, "?") for u, d in last_day.items()
                 if d == date][:4]
        emotion_hit = [w for w in _EMOTION if w in title]
        # 批注规则(数据驱动, 非主观结论)
        note = ""
        if firsts:
            note = "首现: " + "/".join(firsts)
        if lasts:
            note += (" · " if note else "") + "淡出: " + "/".join(lasts)
        quotes = [r.get("comment_text", "")[:30] for r in day_coms
                  if len(r.get("comment_text", "")) >= 8][:2]
        out.append({
            "date": date, "title": title, "video_id": v.get("id", ""),
            "tags": [{"label": k, "color": c} for k, c in
                     {"毕业": "#b54038", "上班": "#c4aa60", "生日": "#d4a017",
                      "开学": "#476d76", "放假": "#476d76",
                      "离职": "#b54038"}.items() if k in title],
            "emotion_hit": emotion_hit,
            "n_comments": len(day_coms),
            "firsts": firsts, "lasts": lasts,
            "quotes": quotes, "note": note,
        })
    return out


if __name__ == "__main__":
    from sherlock import analyze
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ data/ 无数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    conv = build_conversations(data["comments"], data.get("replies", []),
                               data.get("videos"))
    tl = build_timeline(data.get("videos", []), data["comments"])
    hl = build_highlights(data["comments"])
    print("✅ 情报整理档案:", render_dossier(conv, tl, hl))
    print("✅ 时间线分析:",
          render_timeline(build_timeline_analysis(data.get("videos", []),
                                                  data["comments"])))
