"""福尔摩斯线索墙: 关系图单文件 HTML 生成器。

设计要点(2026-09-28 定稿):
- 布局: G6 force 引擎 + preventOverlap(nodeSpacing 碰撞排斥),
  作者 fx/fy 钉在画布中心, 其余自由散布——有机且不重叠
- 球大小: 按亲密度(closeness 字段, 与 predict 同口径加权)
- 默认核心圈视图: 初始隐藏粉丝/路人, 图例点击可展开;
  例外: 有 2 条以上回复边的路人(频繁沟通者)保留可见
- 线条: 互关 4px / 回复 3px / 其余 2.2px, 高不透明度
- 交互: 悬停阅卷(身份/抖音号/IP/亲密度), 点击跳主页
  (与拖拽区分), 角色/边类型图例开关, IP 着色切换
"""
import json
import os
from typing import Any, Dict, List

_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "analysis_output")

_PALETTE = {"作者": "#d4a017", "互关": "#c0392b", "核心粉": "#b5651d",
            "粉丝": "#6d8fae", "关注": "#7a8a5a", "高频路人": "#9a7b4f",
            "路人": "#8a7f6d"}
_REGION_PALETTE = {"广东": "#a93226", "湖南": "#c49a6c", "浙江": "#6d8fae",
                   "四川": "#7a8a5a", "广西": "#9a7b4f", "福建": "#5d6d7e",
                   "江西": "#8f6dae", "重庆": "#4f8a8b", "海南": "#b5651d",
                   "未知": "#4a4037", "其他": "#8a7f6d"}
_EDGE_STYLE = {"粉丝": ("#5B8FF9", 2.2, [1, 3]),
               "关注": ("#52c41a", 2.2, [2, 2]),
               "互关": ("#e74c3c", 4, []),
               "回复": ("#fa8c16", 3, [])}

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>🔍 CASE FILE · 核心关系线索墙</title>
<script src="g6.min.js"></script>
<script>window.onerror=function(m){document.title="ERR: "+m;};</script>
<style>
  body{margin:0;background:#241c15;font-family:"Courier New",monospace;color:#e8d5b5}
  #mount{width:100vw;height:calc(100vh - 46px)}
  .board{padding:10px 20px;border-bottom:2px solid #4a3a2a;
    background:linear-gradient(180deg,#2e241a,#241c15);
    display:flex;flex-wrap:wrap;align-items:center;gap:14px;font-size:12px}
  .board h1{font-size:15px;margin:0;letter-spacing:2px;color:#d4a017}
  .stamp{border:1px dashed #7a5f3a;color:#b09a6f;padding:2px 10px;
    font-size:10px;transform:rotate(-2deg);letter-spacing:1px}
  .legend{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .lg{display:inline-flex;align-items:center;gap:5px;cursor:pointer;
    padding:2px 6px;border-radius:3px}
  .lg.off{opacity:.3;text-decoration:line-through}
  .pin{width:9px;height:9px;border-radius:50%;display:inline-block;
    box-shadow:0 0 0 2px rgba(232,213,181,.25)}
  .ln{width:18px;height:3px;display:inline-block}
  .muted{color:#9a8a6a}
</style>
</head>
<body>
<div class="board">
  <h1>🔍 CASE FILE · 核心关系</h1>
  <span class="stamp">SHERLOCK</span>
  <span class="navlinks">
    <a href="贝克街案件分析室_v2.html" style="color:#d4a017;text-decoration:none;margin:0 8px;font-size:12px;letter-spacing:.1em">📁 案件板</a>
    <a href="福尔摩斯线索墙.html" style="color:#d4a017;text-decoration:none;margin:0 8px;font-size:12px;letter-spacing:.1em">🕸️ 关系图</a>
    <a href="情报整理.html" style="color:#d4a017;text-decoration:none;margin:0 8px;font-size:12px;letter-spacing:.1em">📚 整理档案</a>
  </span>
  <div class="legend" id="legend">
    <span class="lg" data-edge="互关"><i class="ln" style="background:#e74c3c"></i>互关</span>
    <span class="lg" data-edge="粉丝"><i class="ln" style="background:#5B8FF9"></i>粉丝</span>
    <span class="lg" data-edge="关注"><i class="ln" style="background:#52c41a"></i>关注</span>
    <span class="lg" data-edge="回复"><i class="ln" style="background:#fa8c16"></i>回复</span>
    <span class="muted">|</span>
    <span class="lg" data-role="互关"><i class="pin" style="background:#c0392b"></i>互关</span>
    <span class="lg" data-role="核心粉"><i class="pin" style="background:#b5651d"></i>核心粉</span>
    <span class="lg" data-role="粉丝"><i class="pin" style="background:#6d8fae"></i>粉丝</span>
    <span class="lg" data-role="关注"><i class="pin" style="background:#7a8a5a"></i>关注</span>
    <span class="lg" data-role="高频路人"><i class="pin" style="background:#9a7b4f"></i>高频路人</span>
    <span class="lg" data-role="路人"><i class="pin" style="background:#8a7f6d"></i>路人</span>
    <span class="lg" id="ipToggle"><i class="pin" style="background:linear-gradient(135deg,#a93226,#6d8fae)"></i>IP着色模式</span>
    <span class="muted">默认核心圈 · 球大=亲密度 · 点图例展开</span>
  </div>
</div>
<div id="mount"></div>
<script>
const DATA = __DATA__;
const PALETTE = __PALETTE__;
const RPALETTE = __RPALETTE__;
const ESTYLE = __ESTYLE__;
const hiddenEdges = new Set(), hiddenRoles = new Set(['粉丝', '路人']);
let ipMode = false, tipEl = null, tipTimer = null;
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const g = new G6.Graph({
  container: 'mount', width: window.innerWidth, height: window.innerHeight - 46,
  modes: { default: ['drag-canvas', 'zoom-canvas', 'drag-node'] },
  defaultNode: {
    type: 'circle',
    labelCfg: { style: { fill: '#e8d5b5', fontSize: 11, fontFamily: 'Courier New, monospace' } },
  },
  nodeStateStyles: { hover: { lineWidth: 3, stroke: '#e8d5b5' } },
  layout: {
    type: 'force',
    preventOverlap: true,
    nodeSpacing: 34,
    nodeStrength: -300,
    linkDistance: 46,
    edgeStrength: 0.6,
    center: [window.innerWidth/2, (window.innerHeight-46)/2],
  },
});

function pinAuthor(list) {
  const cx = window.innerWidth / 2, cy = (window.innerHeight - 46) / 2;
  const author = list.find(n => n.role === '作者');
  if (author) { author.fx = cx; author.fy = cy; }
}

function render() {
  // 核心圈: 隐藏粉丝/路人, 但保留核心人物的对话对象——
  // 与核心成员(作者/互关/核心粉/高频路人)有回复边的路人一并显示,
  // 这样"频繁沟通的线"不会因为对方被隐藏而消失
  const core = DATA.nodes.filter(n => !hiddenRoles.has(n.role));
  const coreIds = new Set(core.map(n => n.id));
  const talkIds = new Set();
  DATA.edges.forEach(e => {
    if (e.type !== '回复') return;
    if (coreIds.has(e.source) && !coreIds.has(e.target)) talkIds.add(e.target);
    if (coreIds.has(e.target) && !coreIds.has(e.source)) talkIds.add(e.source);
  });
  const visible = DATA.nodes.filter(n =>
    coreIds.has(n.id) || talkIds.has(n.id));
  pinAuthor(visible);
  const nodes = visible.map(n => ({
    id: n.id,
    fx: n.fx, fy: n.fy,
    label: (n.role === '作者' || n.role === '互关' || n.comment_n >= 5) ? n.label : '',
    size: n.role === '作者' ? 56 : 10 + Math.min(Math.sqrt(n.closeness || 0) * 4, 36),
    style: {
      fill: ipMode ? (RPALETTE[n.ip_region] || '#8a7f6d') : (PALETTE[n.role] || '#8a7f6d'),
      stroke: ipMode ? (PALETTE[n.role] || '#8a7f6d') : '#e8d5b5',
      lineWidth: n.role === '作者' ? 3 : (n.role === '互关' || n.role === '核心粉' ? 2 : 0.8),
      shadowColor: n.role === '作者' ? '#d4a017' : 'transparent',
      shadowBlur: n.role === '作者' ? 30 : 0,
    },
  }));
  const edges = DATA.edges
    .filter(e => !hiddenEdges.has(e.type))
    .filter(e => nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target))
    .map(e => {
      const [c, w, dash] = ESTYLE[e.type] || ['#a93226', 2.2, []];
      return { source: e.source, target: e.target,
               style: { stroke: c, lineWidth: w, lineDash: dash,
                 opacity: e.type === '互关' ? 0.95 : 0.7,
                 endArrow: e.type === '回复'
                   ? { path: G6.Arrow.triangle(5, 6, 0), fill: '#fa8c16' }
                   : false } };
    });
  g.data({ nodes, edges });
  try { g.render(); } catch (e) { document.title = 'RENDER_ERR: ' + String(e); }
}

// 图例开关
document.getElementById('legend').addEventListener('click', ev => {
  const el = ev.target.closest('.lg');
  if (!el || el.id === 'ipToggle') return;
  el.classList.toggle('off');
  if (el.dataset.edge) {
    el.classList.contains('off') ? hiddenEdges.add(el.dataset.edge) : hiddenEdges.delete(el.dataset.edge);
  } else if (el.dataset.role) {
    el.classList.contains('off') ? hiddenRoles.add(el.dataset.role) : hiddenRoles.delete(el.dataset.role);
  }
  render();
});
document.getElementById('ipToggle').addEventListener('click', ev => {
  ipMode = !ipMode;
  ev.currentTarget.classList.toggle('off', !ipMode);
  render();
});

// 悬停阅卷 + 自动消失
function hideTip() {
  if (tipEl) { tipEl.remove(); tipEl = null; }
  if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
  document.onmousemove = null;
}
g.on('node:mouseenter', evt => {
  const n = evt.item.getModel();
  const nd = DATA.nodes.find(x => x.id === n.id);
  hideTip();
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;z-index:9;background:rgba(40,30,20,.97);color:#e8d5b5;' +
    'padding:8px 14px;border:1px dashed #7a5f3a;border-radius:2px;font-size:11px;' +
    'font-family:"Courier New",monospace;pointer-events:none;letter-spacing:1px;max-width:280px';
  t.innerHTML = '🔍 <b>' + esc(nd.name_full || nd.label) + '</b><br>└ 身份: ' + esc(nd.role)
    + (nd.douyin_id ? '<br>└ 抖音号: ' + esc(nd.douyin_id) + ' (点击节点查看TA的对话)' : '')
    + (nd.follows_count ? '<br>└ 关注: ' + esc(nd.follows_count) + ' · 粉丝: ' + esc(nd.fans_count || '-')
       + ' · 获赞: ' + esc(nd.likes_count || '-') : '')
    + (nd.closeness ? '<br>└ 亲密度: ' + esc(nd.closeness) : '')
    + (nd.comment_n ? '<br>└ 评论次数: ' + esc(nd.comment_n) : '')
    + (nd.ip ? '<br>└ IP属地: ' + esc(nd.ip) : '');
  document.body.appendChild(t);
  tipEl = t;
  document.onmousemove = e => { t.style.left = (e.clientX + 14) + 'px'; t.style.top = (e.clientY + 10) + 'px'; };
  tipTimer = setTimeout(hideTip, 4000);
});
g.on('node:mouseleave', hideTip);
g.on('canvas:dragstart', hideTip);
g.on('node:dragstart', hideTip);
g.on('wheel', hideTip);

// 拖动作者时解除钉住(之后可自由移动)
g.on('node:dragstart', evt => {
  const n = evt.item.getModel();
  if (n.id === 'AUTHOR') { n.fx = undefined; n.fy = undefined; }
});

// 节点点击: 用户/作者 → 情报整理页按人筛选对话
g.on('node:click', evt => {
  const n = evt.item.getModel();
  const nd = DATA.nodes.find(x => x.id === n.id);
  if (!nd) return;
  window.open('情报整理.html#who=' + encodeURIComponent(nd.name_full || nd.label || ''), '_blank');
});


render();
window.addEventListener('resize', () => g.changeSize(window.innerWidth, window.innerHeight - 46));
</script>
</body>
</html>"""


def build_core_data(nodes: List[Dict[str, Any]],
                    edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    """全量图 → 核心子图(工具函数, 供手动筛选用)。

    Args:
        nodes: 全量节点。
        edges: 全量边。

    Returns:
        {"nodes": [...], "edges": [...]} 核心子图。
    """
    keep = {n["id"] for n in nodes
            if n["role"] in ("作者", "互关", "核心粉", "关注", "高频路人")
            or n.get("comment_n", 0) >= 5}
    core_edges = [e for e in edges
                  if e["type"] in ("粉丝", "关注", "互关", "回复")
                  and e["source"] in keep and e["target"] in keep]
    degree: Dict[str, int] = {}
    for e in core_edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1
    core_nodes = [n for n in nodes if n["id"] in keep
                  and (n["role"] != "路人" or degree.get(n["id"], 0) > 0)]
    return {"nodes": core_nodes, "edges": core_edges}


def render_sherlock(data: Dict[str, Any],
                    out_path: str = "") -> str:
    """渲染线索墙 HTML(单文件, 数据内嵌, 离线可用)。

    Args:
        data: build_graph_data 的返回值(nodes/edges)。
        out_path: 输出路径, 默认 analysis_output/福尔摩斯线索墙.html。

    Returns:
        生成的 HTML 文件绝对路径。
    """
    os.makedirs(_OUT_DIR, exist_ok=True)
    target = out_path or os.path.join(_OUT_DIR, "福尔摩斯线索墙.html")
    html = _TEMPLATE
    html = html.replace("__PALETTE__", json.dumps(_PALETTE))
    html = html.replace("__RPALETTE__", json.dumps(_REGION_PALETTE))
    html = html.replace("__ESTYLE__", json.dumps(_EDGE_STYLE))
    # 最后替换 __DATA__(避免昵称里含占位符名把数据串进模板)
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    with open(target, "w", encoding="utf-8") as f:
        f.write(html)
    # 线索墙依赖同目录的 g6.min.js, 缺失时页面会是空白
    if not os.path.exists(os.path.join(os.path.dirname(target), "g6.min.js")):
        print("⚠️ analysis_output/ 缺 g6.min.js: 线索墙页面无法渲染, "
              "请从旧目录复制(douyin-comment/analysis_output/g6.min.js)或 "
              "从 CDN 下载 G6 4.x 到同目录")
    return os.path.abspath(target)


if __name__ == "__main__":
    from sherlock import analyze
    data = analyze.load_all()
    if not data.get("comments"):
        print("❌ data/ 无数据, 请先 python -m sherlock.collect <sec_uid>")
        raise SystemExit(1)
    gd = analyze.build_graph_data(data)
    print("✅ 线索墙:", render_sherlock(gd))
