"""贝克街案件分析室: 多案件逐步推演线索板生成器。

从案件数据(纯 JSON, 不绑定任何真实数据)渲染单文件交互 HTML:
- 左侧案件档案列表, 多案卷切换
- 中间软木板: 线索卡可拖拽, 红线随推演步骤生长
- 顶部步骤条: 逐步揭示线索
- 右侧: 分析守则(防主观) / 关键人物(置信度) / 竞争假设 / 笔记 / 推论
- 可选挂载关系图入口(由 sherlock.graph 生成)

方法论: 证据先行, 多假设竞争检验, 结论跟随证据——
见右侧"分析守则"四条。
"""
import json
import os
from typing import Any, Dict, List, Optional

_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "analysis_output")

_TEMPLATE = """<style>
    :root{--ink:#171411;--paper:#e9dfc7;--paper-2:#d9c9a6;--gold:#c7a45e;--red:#8e2d28;--red-bright:#c94b40;--green:#49664a;--blue:#355f73;--board:#765239;--board-dark:#432e20;--cream:#f2ead9;--muted:#9e927f;--shadow:0 16px 42px rgba(8,5,3,.34)}
    *{box-sizing:border-box}
    html{min-width:320px;background:#100e0c}
    body{margin:0;color:var(--cream);font-family:Georgia,'Songti SC','Noto Serif SC',serif;background:radial-gradient(circle at 50% -15%,#35291f 0,#181411 48%,#0d0b09 100%);min-height:100vh;overflow-x:hidden}
    button,input,textarea{font:inherit}
    button{cursor:pointer}
    button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid #e7c875;outline-offset:3px}
    .shell{min-height:100vh;display:grid;grid-template-rows:auto 1fr}
    header{min-height:76px;padding:14px 28px;border-bottom:1px solid rgba(220,195,143,.22);display:flex;align-items:center;justify-content:space-between;gap:20px;background:rgba(16,14,12,.8);backdrop-filter:blur(18px);position:relative;z-index:20}
    .brand{display:flex;align-items:center;gap:14px;min-width:0}.monogram{width:42px;height:42px;border:1px solid var(--gold);border-radius:50%;display:grid;place-items:center;color:var(--gold);font-size:20px;box-shadow:inset 0 0 0 4px #181410}.brand h1{font-size:18px;letter-spacing:.17em;margin:0;font-weight:500;white-space:nowrap}.brand p{margin:4px 0 0;color:#8f816d;font:10px/1.2 Arial,sans-serif;letter-spacing:.24em}
    .case-meta{display:flex;align-items:center;gap:22px;font:10px Arial,sans-serif;color:#c0b39d}.status{display:flex;align-items:center;gap:8px}.status i{width:7px;height:7px;background:#b54038;border-radius:50%;box-shadow:0 0 0 5px rgba(181,64,56,.12);animation:pulse 2.2s infinite}.case-id{border-left:1px solid #4d4034;padding-left:22px;letter-spacing:.12em}.header-btn{border:1px solid #65533f;background:#211b16;color:#d7c7aa;border-radius:3px;padding:10px 14px;font-size:12px;letter-spacing:.08em}.header-btn:hover{border-color:var(--gold);color:#f2d99e}
    .workspace{display:grid;grid-template-columns:260px minmax(520px,1fr) 290px;min-height:calc(100vh - 77px)}
    aside{background:rgba(20,17,14,.75);padding:24px 19px;position:relative;z-index:10}.left{border-right:1px solid #3b3027}.right{border-left:1px solid #3b3027}.section-label{font:10px Arial,sans-serif;letter-spacing:.22em;color:var(--gold);display:flex;align-items:center;gap:10px;margin:0 0 14px}.section-label:after{content:"";height:1px;background:#4b3d30;flex:1}.case-title{font-size:17px;line-height:1.2;font-weight:500;margin:0 0 8px}.location{color:#8d806e;font-size:12px;margin:0 0 22px}.case-desc{font-size:11px;line-height:1.7;color:#b5a995;margin-bottom:24px}.progress-head{display:flex;justify-content:space-between;font:11px Arial,sans-serif;color:#9a8c79;margin-bottom:8px}.progress{height:4px;background:#302820;overflow:hidden}.progress span{display:block;width:68%;height:100%;background:linear-gradient(90deg,#7f2925,#c15548)}
    .filter-title{margin:27px 0 11px;font:10px Arial,sans-serif;color:#7e7262;letter-spacing:.18em}.filters{display:grid;gap:8px}.filter{width:100%;display:flex;align-items:center;justify-content:space-between;border:0;background:transparent;color:#bfb29c;padding:9px 6px;text-align:left;font-size:13px;border-bottom:1px solid #2f2821}.filter.active{color:#f1d493}.filter .dot{width:8px;height:8px;border-radius:50%;margin-right:10px;display:inline-block}.filter b{font:10px Arial,sans-serif;color:#716656;font-weight:400}.legend{margin-top:28px;padding:14px;border:1px solid #342c24;background:#17130f}.legend p{margin:7px 0;font:11px Arial,sans-serif;color:#897d6c}.legend span{display:inline-block;width:24px;height:2px;margin-right:8px;vertical-align:middle}.board-wrap{position:relative;padding:26px;overflow:hidden;background:linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px);background-size:28px 28px}
    .board-toolbar{position:absolute;top:14px;left:50%;transform:translateX(-50%);z-index:9;background:rgba(20,16,13,.92);border:1px solid #574534;padding:6px;display:flex;gap:5px;box-shadow:0 6px 20px #120d09}.tool{border:0;background:transparent;color:#9f927f;width:35px;height:31px;border-radius:2px;font:15px Arial}.tool:hover,.tool.active{background:#493929;color:#f1d28f}.zoom{width:auto;padding:0 10px;font-size:11px}
    .board{height:calc(100vh - 129px);min-height:620px;max-height:880px;position:relative;overflow:hidden;border:12px solid var(--board-dark);box-shadow:inset 0 0 0 2px #967055,inset 0 0 80px rgba(34,17,7,.38),var(--shadow);background-color:var(--board);background-image:radial-gradient(rgba(244,220,173,.11) 1px,transparent 1px),radial-gradient(rgba(43,25,15,.13) 1px,transparent 1px),linear-gradient(135deg,rgba(255,255,255,.03),rgba(0,0,0,.08));background-size:7px 7px,11px 11px,100% 100%}
    #threads{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2;overflow:visible}.thread{stroke:#a8322d;stroke-width:2;filter:drop-shadow(0 1px 1px #28130f);opacity:.86}.thread.weak{stroke-dasharray:6 5;opacity:.58}.thread-dot{fill:#b13b33;stroke:#6e211d;stroke-width:2}
    .clue{position:absolute;width:178px;color:#251f18;background:var(--paper);padding:15px 15px 13px;box-shadow:0 7px 14px rgba(28,16,8,.36);z-index:4;cursor:grab;user-select:none;transform:rotate(var(--r));transition:box-shadow .18s,filter .18s,opacity .2s}.clue:active{cursor:grabbing;box-shadow:0 18px 30px rgba(20,11,5,.5)}.clue.hidden{opacity:.12;filter:grayscale(1);pointer-events:none}.clue.selected{box-shadow:0 0 0 3px #d8b357,0 14px 26px rgba(24,12,5,.45);z-index:6}.clue:before{content:"";position:absolute;left:50%;top:5px;width:9px;height:9px;background:#a63730;border-radius:50%;transform:translateX(-50%);box-shadow:0 2px 2px #5a1b18,0 0 0 2px rgba(255,255,255,.16)}.clue.photo{padding:11px;background:#ddd2ba}.clue.photo .scene{height:92px;border:5px solid #efe7d5;background:linear-gradient(145deg,#1e2422,#53605a 45%,#181d1c);display:grid;place-items:center;color:#b6b7ac;font-size:34px;filter:sepia(.35)}.clue.photo .caption{text-align:center;margin-top:9px;font:italic 12px Georgia}.tape{position:absolute;left:50%;top:-8px;width:58px;height:18px;transform:translateX(-50%) rotate(-3deg);background:rgba(220,205,161,.65);box-shadow:0 1px 2px rgba(38,30,14,.15)}.clue-tag{display:flex;justify-content:space-between;align-items:center;color:#695d4e;font:8px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;margin:3px 0 11px}.clue h3{font-size:13px;margin:0 0 7px;font-weight:600}.clue p{font-size:10px;line-height:1.48;margin:0;color:#574d40}.clue .mark{position:absolute;right:8px;bottom:6px;font:bold 22px/1 Arial;color:rgba(132,39,34,.34);transform:rotate(-10deg)}
    .clue.note{background:#d8c78f}.clue.note p{font-family:'Kaiti SC',Georgia,serif;font-size:13px}.clue.dark{background:#282723;color:#ded3b9;border:1px solid #897354}.clue.dark p{color:#bcb096}.clue.dark .clue-tag{color:#94866f}.clue.evidence:after{content:"EVIDENCE";position:absolute;right:8px;bottom:6px;border:2px solid rgba(123,35,31,.45);color:rgba(123,35,31,.55);padding:2px 4px;font:bold 8px Arial;transform:rotate(-8deg)}
    .votebar{display:flex;gap:5px;margin-top:9px;justify-content:center}
    .votebar button{border:1px solid #8a7a5a;background:#efe7d5;color:#574d40;
      font:10px Arial;padding:3px 8px;border-radius:3px;cursor:pointer}
    .votebar button:hover{border-color:#a8322d;color:#a8322d}
    .clue.voteA{box-shadow:0 0 0 3px #2e7d32,0 7px 14px rgba(28,16,8,.36)}
    .clue.voteB{box-shadow:0 0 0 3px #b54038,0 7px 14px rgba(28,16,8,.36)}
    .clue.voteQ{box-shadow:0 0 0 3px #d4a017,0 7px 14px rgba(28,16,8,.36)}
    .clue-a{left:8%;top:8%;--r:-3deg}.clue-b{left:40%;top:4%;--r:2deg}.clue-c{right:7%;top:11%;--r:-1deg}.clue-d{left:14%;top:43%;--r:2deg}.clue-e{left:45%;top:39%;--r:-2deg}.clue-f{right:7%;top:47%;--r:3deg}.clue-g{left:31%;bottom:6%;--r:1deg}.clue-h{right:24%;bottom:5%;--r:-3deg}
    .analysis-tabs{display:flex;border-bottom:1px solid #3b3027;margin:-2px 0 20px}.tab{flex:1;border:0;background:none;color:#776b5d;padding:10px 3px;font:11px Arial,sans-serif;letter-spacing:.08em;border-bottom:2px solid transparent}.tab.active{color:#e1c27b;border-color:#ad853d}.panel{display:none}.panel.active{display:block}.suspect{padding:15px 0;border-bottom:1px solid #302821}.suspect-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.suspect h3{font-size:15px;font-weight:500;margin:0}.risk{font:9px Arial,sans-serif;padding:4px 6px;border:1px solid}.risk.high{color:#d96a5f;border-color:#66342f}.risk.mid{color:#d3b66d;border-color:#5c4e31}.risk.low{color:#77977b;border-color:#354939}.suspect p{color:#8f8372;font-size:11px;line-height:1.5;margin:8px 0}.motive{font:10px Arial,sans-serif;color:#b6a991}.motive b{color:#716657;font-weight:400}.confidence{display:flex;gap:3px;margin-top:10px}.confidence i{width:18px;height:3px;background:#3b3128}.confidence i.on{background:#a83b34}
    .prob{margin-top:8px;font:10px Arial;color:#d3b66d;line-height:1.6}.hypothesis{padding:15px;border:1px solid #483a2d;background:#181410;margin-bottom:12px}.hypothesis strong{display:block;color:#d7bd82;font-size:13px;margin-bottom:7px}.hypothesis p{font-size:11px;line-height:1.6;color:#8f8371;margin:0}.notes{width:100%;height:215px;resize:vertical;background:#181410;border:1px solid #493b2e;color:#cfbea0;padding:12px;font-size:13px;line-height:1.6}.save-state{height:16px;margin:8px 0 0;color:#6e8e71;font:10px Arial,sans-serif}
    .casefilters{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px}
    .cf{border:1px solid #4b3d30;background:#1b1612;color:#bfb29c;padding:5px 10px;border-radius:12px;font-size:11px;cursor:pointer}
    .cf.on{background:#493929;color:#f1d28f;border-color:#97763e}
    .score-badge{float:right;font:10px Arial;color:#c7a45e;border:1px solid #574534;border-radius:8px;padding:1px 6px}
    .stats{font:11px Arial;color:#8f816d;margin:0 0 12px;line-height:1.8}
    .guardrails{padding:12px 13px;border:1px solid #574534;background:#16110d;margin-bottom:14px;border-radius:2px}.guardrails b{display:block;font:11px Arial;letter-spacing:.16em;color:#c7a45e;margin-bottom:7px}.guardrails p{margin:0;font:11px/1.8 Arial;color:#9a8c79}.deduce{width:100%;margin-top:20px;border:1px solid #97763e;background:linear-gradient(#3f3020,#2b2118);color:#e8ce95;padding:13px;font-size:12px;letter-spacing:.13em}.deduce:hover{background:#4b3925}.result{display:none;margin-top:12px;padding:13px;background:#211914;border-left:2px solid var(--red-bright);font-size:11px;line-height:1.6;color:#bdae97}.result.show{display:block;animation:reveal .45s ease-out}
    .mobile-panel-btn{display:none}
    @keyframes pulse{50%{box-shadow:0 0 0 8px rgba(181,64,56,0)}}@keyframes reveal{from{opacity:0;transform:translateY(6px)}}
    @media(max-width:1080px){.workspace{grid-template-columns:220px minmax(500px,1fr)}.right{position:fixed;right:0;top:77px;bottom:0;width:290px;z-index:30;transform:translateX(100%);transition:transform .25s;box-shadow:-18px 0 40px #0c0907}.right.open{transform:translateX(0)}.mobile-panel-btn{display:inline-block}.clue{width:160px}.case-meta .status{display:none}}
    @media(max-width:760px){header{padding:12px 16px}.brand h1{font-size:15px}.brand p,.case-id{display:none}.workspace{display:block}.left{display:none}.board-wrap{padding:14px}.board{height:calc(100svh - 110px);min-height:600px;border-width:8px}.board-toolbar{top:8px}.clue{width:142px;padding:13px 11px}.clue p{font-size:10px}.clue h3{font-size:14px}.clue-a{left:3%;top:8%}.clue-b{left:38%;top:4%}.clue-c{right:3%;top:29%}.clue-d{left:4%;top:38%}.clue-e{left:36%;top:39%}.clue-f{right:3%;top:56%}.clue-g{left:5%;bottom:5%}.clue-h{right:16%;bottom:4%}.right{top:67px}.header-btn{padding:9px}.monogram{width:38px;height:38px}.board-wrap{overflow:auto}.board{min-width:560px}}
  </style>
<body>
<div class="shell">
  <header>
    <div class="brand"><div class="monogram">B</div><div><h1>贝克街案件分析室</h1><p>DOUYIN RELATIONSHIP ARCHIVE</p></div></div><span class="navlinks">
    <a href="贝克街案件分析室_v2.html" style="color:#d4a017;text-decoration:none;margin:0 10px;font-size:12px;letter-spacing:.1em">📁 案件板</a>
    <a href="福尔摩斯线索墙.html" style="color:#d4a017;text-decoration:none;margin:0 10px;font-size:12px;letter-spacing:.1em">🕸️ 关系图</a>
    <a href="情报整理.html" style="color:#d4a017;text-decoration:none;margin:0 10px;font-size:12px;letter-spacing:.1em">📚 整理档案</a>
  </span>
    <div class="case-meta"><div class="status"><i></i><span id="statusText">案件调查中</span></div><div class="case-id" id="caseId">案卷编号 —</div><button class="header-btn mobile-panel-btn" id="openAnalysis">分析</button><button class="header-btn" id="openGraph" style="display:none">关系图</button>
    <button class="header-btn" id="resetBoard">重置线索板</button></div>
  </header>
  <main class="workspace">
    <aside class="left">
      <p class="section-label">案件档案</p>
      <div class="casefilters" id="sevFilters">
        <span class="cf on" data-sev="all">全部</span>
        <span class="cf" data-sev="高">高</span>
        <span class="cf" data-sev="中">中</span>
        <span class="cf" data-sev="低">低</span>
      </div>
      <div class="casefilters" id="ruleFilters"></div>
      <div class="stats" id="caseStats"></div>
      <div id="caseList"></div>
      <div class="legend"><p><span style="background:#a8322d"></span>强关联 / 可证实</p><p><span style="background:repeating-linear-gradient(90deg,#a8322d 0 5px,transparent 5px 9px)"></span>推测关联 / 待验证</p></div>
    </aside>
    <section class="board-wrap" aria-label="可拖拽线索分析板">
      <div class="board-toolbar" style="gap:8px">
        <span id="stepBar" style="font:10px Arial;color:#c0b39d;padding:0 8px;display:flex;align-items:center;gap:4px"></span>
        <button class="tool" id="playBtn" title="自动播放推理">▶播放</button>
        <button class="tool" id="prevStep" title="上一步">◀</button>
        <button class="tool" id="nextStep" title="下一步(揭示新线索)">▶</button>
        <button class="tool" id="toggleLines" title="显示或隐藏关系线">⌁</button>
        <button class="tool zoom" id="arrangeBoard">自动整理</button>
      </div>
      <div class="board" id="board">
        <svg id="threads" aria-hidden="true"></svg>
      </div>
    </section>
    <aside class="right" id="analysisPanel">
      <p class="section-label">推理分析</p>
      <div class="guardrails"><b>分析守则 · 防主观代入</b>
        <p>① 先陈述事实, 再谈推断<br>② 同时保留至少两个竞争假设<br>③ 时间相近 ≠ 因果关系<br>④ 每条结论至少一条直接证据</p></div>
      <div class="analysis-tabs"><button class="tab active" data-panel="suspects">关键人物</button><button class="tab" data-panel="hypotheses">假设</button><button class="tab" data-panel="notes">笔记</button></div>
      <div class="panel active" id="suspects"></div>
      <div class="panel" id="hypotheses"></div>
      <div class="panel" id="notes"><textarea class="notes" id="caseNotes" placeholder="记录你的推理……"></textarea><p class="save-state" id="saveState">笔记自动保存在本机</p></div>
      <div class="guardrails" id="voteSummary" style="margin-top:14px">📊 你的标注: 尚未开始</div>
      <button class="deduce" id="deduce">检验假设 · 形成推论</button><div class="result" id="result"></div>
    </aside>
  </main>
</div>
<script>
const CASES = __CASES__;
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
let cur = null, step = 0, linesVisible = true, drag = null, offsetX = 0, offsetY = 0;
const board = document.getElementById('board');
const svg = document.getElementById('threads');

function loadCase(id){
  stopAuto();
  cur = CASES.find(c => c.id === id);
  step = 0;
  document.getElementById('statusText').textContent = cur.status;
  document.getElementById('caseId').textContent = '案卷编号 ' + cur.caseId;
  renderCaseList();
  renderBoard();
  renderPanels();
}
let sevFilter = 'all', ruleFilter = 'all';
let autoTimer = null;
function stopAuto(){ if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  const b = document.getElementById('playBtn'); if (b) b.textContent = '▶播放'; }
function startAuto(){
  stopAuto();
  step = 0;
  renderBoard();
  const b = document.getElementById('playBtn');
  if (b) b.textContent = '⏸暂停';
  autoTimer = setInterval(() => {
    if (step < cur.steps.length - 1) { step++; renderBoard(); }
    else { stopAuto(); }
  }, 1600);
}
document.getElementById('playBtn').addEventListener('click', () => {
  if (autoTimer) stopAuto(); else startAuto();
});
function renderCaseList(){
  const box = document.getElementById('caseList');
  box.innerHTML = '';
  const rules = [...new Set(CASES.map(c => c.rule))];
  const rf = document.getElementById('ruleFilters');
  rf.innerHTML = '<span class="cf' + (ruleFilter === 'all' ? ' on' : '') + '" data-rule="all">全部规则</span>'
    + rules.map(r => '<span class="cf' + (ruleFilter === r ? ' on' : '') + '" data-rule="' + r + '">' + r + '</span>').join('');
  rf.querySelectorAll('.cf').forEach(el => el.onclick = () => {
    ruleFilter = el.dataset.rule; renderCaseList();
  });
  const stats = document.getElementById('caseStats');
  const bySev = {高: 0, 中: 0, 低: 0};
  CASES.forEach(c => bySev[c.severity] = (bySev[c.severity] || 0) + 1);
  const shown = CASES.filter(c =>
    (sevFilter === 'all' || c.severity === sevFilter)
    && (ruleFilter === 'all' || c.rule === ruleFilter));
  stats.innerHTML = '案卷 ' + shown.length + '/' + CASES.length
    + ' · 高 ' + (bySev['高'] || 0) + ' · 中 ' + (bySev['中'] || 0) + ' · 低 ' + (bySev['低'] || 0);
  shown.forEach(c => {
    const b = document.createElement('button');
    b.className = 'filter' + (cur && c.id === cur.id ? ' active' : '');
    b.innerHTML = '<span><i class="dot" style="background:' + c.color + '"></i>'
      + esc(c.title) + '</span><span class="score-badge">' + (c.score || 0) + '分</span>';
    b.onclick = () => { loadCase(c.id); startAuto(); };
    box.appendChild(b);
  });
}
document.getElementById('sevFilters').addEventListener('click', ev => {
  const el = ev.target.closest('.cf');
  if (!el) return;
  sevFilter = el.dataset.sev;
  document.querySelectorAll('#sevFilters .cf').forEach(x => x.classList.toggle('on', x === el));
  renderCaseList();
});
function renderBoard(){
  board.querySelectorAll('.clue').forEach(x => x.remove());
  const POSITIONS = ['clue-a', 'clue-b', 'clue-c', 'clue-d', 'clue-e', 'clue-f'];
  let gIdx = 0;   // 全案全局卡片编号: 跨步骤不重复占位
  cur.steps.forEach((s, i) => {
    if (i > step) return;
    s.clues.forEach((c, j) => {
      const el = document.createElement('article');
      el.className = 'clue ' + POSITIONS[gIdx % POSITIONS.length] + ' ' + (c.cls || '');
      // 超出 6 个位置时按轮次加偏移, 保证任何两张卡坐标不同
      const cycle = Math.floor(gIdx / POSITIONS.length);
      if (cycle > 0) {
        el.style.marginTop = (cycle * 28) + 'px';
        el.style.marginLeft = (cycle * 28) + 'px';
      }
      gIdx++;
      el.dataset.id = c.id;
      el.tabIndex = 0;
      let inner = '';
      if (c.cls && c.cls.includes('photo')) {
        // 纯文字卡(不再渲染小图, 避免遮挡)
        inner = '<div class="clue-tag"><span>' + esc(c.tag) + '</span><span>' + esc(c.tag2) + '</span></div><p>' + esc(c.caption || c.text || '') + '</p>';
      } else if (c.cls && c.cls.includes('note')) {
        inner = '<div class="clue-tag"><span>' + esc(c.tag) + '</span><span>' + esc(c.tag2) + '</span></div><p>' + esc(c.text) + '</p>';
      } else {
        inner = '<div class="clue-tag"><span>' + esc(c.tag) + '</span><span>' + esc(c.tag2) + '</span></div><h3>' + esc(c.title) + '</h3><p>' + esc(c.text) + '</p>';
        if (c.mark) inner += '<span class="mark">' + c.mark + '</span>';
      }
      el.innerHTML = inner + '<div class="votebar">'
        + '<button data-v="A">👍 A</button><button data-v="B">👎 B</button><button data-v="?">❓ 存疑</button>'
        + '</div>';
      // 恢复本卡已标注状态
      const vote = localStorage.getItem(voteKey(c.id));
      if (vote) el.classList.add(vote);
      board.appendChild(el);
    });
  });
  restore();
  renderSteps();
  updateSummary();
  draw();
}
function renderSteps(){
  const bar = document.getElementById('stepBar');
  bar.innerHTML = cur.steps.map((s, i) =>
    '<span style="padding:2px 5px;border-radius:2px;' +
    (i === step ? 'background:#493929;color:#f1d28f' : i < step ? 'color:#8f8372' : 'color:#55504a') +
    '">' + s.label + '</span>').join(' › ');
}
function renderPanels(){
  const sb = document.getElementById('suspects');
  sb.innerHTML = cur.suspects.map(p =>
    '<div class="suspect"><div class="suspect-head"><h3>' + esc(p.name) + '</h3><span class="risk ' + p.risk + '">' + esc(p.riskLabel) + '</span></div><p>' + esc(p.desc) + '</p><div class="motive"><b>证据</b> · ' + esc(p.evidence) + '</div><div class="confidence">' +
    Array.from({length: 5}, (_, i) => '<i class="' + (i < p.conf ? 'on' : '') + '"></i>').join('') +
    '</div>' + (p.prob ? '<div class="prob">' + p.prob + '</div>' : '') + '</div>').join('');
  const hb = document.getElementById('hypotheses');
  hb.innerHTML = cur.hypotheses.map(h =>
    '<div class="hypothesis"><strong>' + esc(h.title) + '</strong><p>' + esc(h.text) + '</p></div>').join('');
  document.getElementById('result').textContent = cur.conclusion;
  document.getElementById('result').classList.remove('show');
  const notes = document.getElementById('caseNotes');
  notes.value = localStorage.getItem('douyin-notes-' + cur.id) || '';
}
function center(el){
  const b = board.getBoundingClientRect(), r = el.getBoundingClientRect();
  return {x: r.left - b.left + r.width / 2, y: r.top - b.top + r.height / 2};
}
function draw(){
  svg.innerHTML = '';
  if (!linesVisible) return;
  cur.steps.slice(0, step + 1).forEach(s => s.links.forEach(([a, b, weak]) => {
    const x = board.querySelector('[data-id="' + a + '"]'), y = board.querySelector('[data-id="' + b + '"]');
    if (!x || !y) return;
    const p = center(x), q = center(y);
    svg.insertAdjacentHTML('beforeend',
      '<line class="thread ' + (weak ? 'weak' : '') + '" x1="' + p.x + '" y1="' + p.y + '" x2="' + q.x + '" y2="' + q.y + '"/>' +
      '<circle class="thread-dot" cx="' + p.x + '" cy="' + p.y + '" r="3.5"/><circle class="thread-dot" cx="' + q.x + '" cy="' + q.y + '" r="3.5"/>');
  }));
}
function posKey(){ return 'douyin-board-' + cur.id; }
function voteKey(clueId){ return 'douyin-vote-' + cur.id + '-' + clueId; }
function updateSummary(){
  const a = board.querySelectorAll('.clue.voteA').length;
  const b = board.querySelectorAll('.clue.voteB').length;
  const q = board.querySelectorAll('.clue.voteQ').length;
  const el = document.getElementById('voteSummary');
  if (!el) return;
  const prob = cur.progress || 0;
  let html = '⚖️ 系统判定: 异常概率 <b>' + prob + '%</b>'
    + (prob >= 60 ? '(倾向假设A)' : prob <= 40 ? '(倾向假设B/正常)' : '(存疑待核)');
  html += '<br>📊 你的标注: 支持A <b>' + a + '</b> · 支持B <b>' + b + '</b> · 存疑 <b>' + q + '</b>';
  if (a + b + q > 0) {
    const userA = a > b ? 'A' : (b > a ? 'B' : '平');
    const sysA = prob >= 60 ? 'A' : (prob <= 40 ? 'B' : '存疑');
    html += '<br>' + (userA === sysA
      ? '✅ 你的检验与系统判定一致'
      : (userA === '平' ? '⚖️ 你未倾向任何假设' : '⚠️ 你的检验与系统判定不一致, 建议复核证据'));
  } else {
    html += '<br>点击证据卡下方按钮开始检验';
  }
  el.innerHTML = html;
}
function save(){
  const data = {};
  board.querySelectorAll('.clue').forEach(c => data[c.dataset.id] = {left: c.style.left, top: c.style.top});
  localStorage.setItem(posKey(), JSON.stringify(data));
}
function restore(){
  try {
    const data = JSON.parse(localStorage.getItem(posKey()) || '{}');
    board.querySelectorAll('.clue').forEach(c => {
      if (data[c.dataset.id]) { c.style.left = data[c.dataset.id].left; c.style.top = data[c.dataset.id].top; c.style.right = 'auto'; c.style.bottom = 'auto'; }
    });
  } catch (e) {}
  requestAnimationFrame(draw);
}
function start(e){
  const c = e.target.closest('.clue');
  if (!c) return;
  drag = c; c.classList.add('selected');
  const r = c.getBoundingClientRect();
  offsetX = (e.clientX ?? e.touches?.[0].clientX) - r.left;
  offsetY = (e.clientY ?? e.touches?.[0].clientY) - r.top;
  c.setPointerCapture?.(e.pointerId);
}
function move(e){
  if (!drag) return;
  const b = board.getBoundingClientRect();
  let x = e.clientX - b.left - offsetX, y = e.clientY - b.top - offsetY;
  x = Math.max(0, Math.min(b.width - drag.offsetWidth, x));
  y = Math.max(0, Math.min(b.height - drag.offsetHeight, y));
  drag.style.left = x + 'px'; drag.style.top = y + 'px';
  drag.style.right = 'auto'; drag.style.bottom = 'auto';
  draw();
}
function end(){ if (!drag) return; drag.classList.remove('selected'); drag = null; save(); }
// 投票按钮区按下时阻断拖拽(指针捕获会把点击重定向到卡片, 按钮收不到事件)
board.addEventListener('pointerdown', ev => {
  if (ev.target.closest('.votebar')) ev.stopPropagation();
}, true);
board.addEventListener('click', ev => {
  const btn = ev.target.closest('.votebar button');
  if (!btn) return;
  const clue = btn.closest('.clue');
  clue.classList.remove('voteA', 'voteB', 'voteQ');
  clue.classList.add('vote' + btn.dataset.v);
  localStorage.setItem(voteKey(clue.dataset.id), 'vote' + btn.dataset.v);
  updateSummary();
});
board.addEventListener('pointerdown', start);
board.addEventListener('pointermove', move);
board.addEventListener('pointerup', end);
board.addEventListener('pointercancel', end);
document.getElementById('nextStep').addEventListener('click', () => { stopAuto(); if (step < cur.steps.length - 1) { step++; renderBoard(); } });
document.getElementById('prevStep').addEventListener('click', () => { stopAuto(); if (step > 0) { step--; renderBoard(); } });
document.getElementById('toggleLines').addEventListener('click', e => { linesVisible = !linesVisible; e.currentTarget.classList.toggle('active', linesVisible); draw(); });
document.getElementById('deduce').addEventListener('click', () => {
  const a = board.querySelectorAll('.clue.voteA').length;
  const b = board.querySelectorAll('.clue.voteB').length;
  const q = board.querySelectorAll('.clue.voteQ').length;
  const res = document.getElementById('result');
  if (a + b + q === 0) {
    res.textContent = '你还没有标注任何证据。先完成上方证据卡的 👍/👎/❓ 检验, 再来形成推论。';
  } else if (a > b) {
    res.textContent = '你的标注: 支持A ×' + a + ', 支持B ×' + b + ', 存疑 ×' + q
      + '。按你的检验, 证据更倾向假设A——但请再核对存疑项与反证后采信。';
  } else if (b > a) {
    res.textContent = '你的标注: 支持A ×' + a + ', 支持B ×' + b + ', 存疑 ×' + q
      + '。按你的检验, 证据更倾向假设B(正常波动)——倾向排除异常。';
  } else {
    res.textContent = '你的标注: 支持A ×' + a + ', 支持B ×' + b + ', 存疑 ×' + q
      + '。两边势均力敌, 建议补充证据后再下结论。';
  }
  res.classList.add('show');
});
document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
  document.querySelectorAll('.tab,.panel').forEach(x => x.classList.remove('active'));
  tab.classList.add('active');
  document.getElementById(tab.dataset.panel).classList.add('active');
}));
const notes = document.getElementById('caseNotes');
notes.addEventListener('input', () => {
  localStorage.setItem('douyin-notes-' + cur.id, notes.value);
  const s = document.getElementById('saveState');
  s.textContent = '已保存'; clearTimeout(notes.timer);
  notes.timer = setTimeout(() => s.textContent = '笔记自动保存在本机', 1200);
});
const gb = document.getElementById('openGraph');
if (gb) { gb.style.display = ''; gb.addEventListener('click', () => window.open('福尔摩斯线索墙.html')); }
document.getElementById('openAnalysis').addEventListener('click', () => document.getElementById('analysisPanel').classList.toggle('open'));
document.addEventListener('click', e => { if (innerWidth <= 1080 && !e.target.closest('#analysisPanel') && !e.target.closest('#openAnalysis')) document.getElementById('analysisPanel').classList.remove('open'); });
function arrange(){
  board.querySelectorAll('.clue').forEach(c => { c.style.left = ''; c.style.top = ''; c.style.right = ''; c.style.bottom = ''; });
  localStorage.removeItem(posKey());
  setTimeout(draw, 30);
}
document.getElementById('arrangeBoard').addEventListener('click', arrange);
document.getElementById('resetBoard').addEventListener('click', () => { arrange(); notes.value = ''; localStorage.removeItem('douyin-notes-' + cur.id); document.getElementById('result').classList.remove('show'); });
addEventListener('resize', draw);
loadCase(CASES[0].id);
</script>
"""


def render_cases(cases: List[Dict[str, Any]],
                 out_path: str = "",
                 graph_link: str = "") -> str:
    """渲染多案件推演板 HTML。

    Args:
        cases: 案件列表。结构见 demo_cases.json:
            id/title/color/caseId/status/progress/steps(每步 label+
            clues+links)/suspects/hypotheses/conclusion。
            步骤 label 建议用方法论命名: 事实收集/证据关联/
            竞争假设/检验排除/结论。
        out_path: 输出路径, 默认 analysis_output/贝克街案件分析室_v2.html。
        graph_link: 关系图 HTML 相对路径, 非空时顶部出现入口按钮。

    Returns:
        生成的 HTML 文件绝对路径。
    """
    os.makedirs(_OUT_DIR, exist_ok=True)
    target = out_path or os.path.join(_OUT_DIR, "贝克街案件分析室_v2.html")
    html = _TEMPLATE.replace("__CASES__", json.dumps(cases, ensure_ascii=False).replace("</", "<\\/"))
    if graph_link:
        html = html.replace("const gb = document.getElementById('openGraph');",
                            "const gb = document.getElementById('openGraph');", 1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.abspath(target)
