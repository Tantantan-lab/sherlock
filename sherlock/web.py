"""网页入口: 本机 HTTP 服务, 普通人三步完成侦查。

    python -m sherlock.web            # 启动并自动打开浏览器
    # 页面: ①扫码登录 ②粘贴主页链接 ③开始侦查 → 看结果

仅依赖标准库; 侦查任务在后台线程执行, 前端轮询进度。
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PORT = 8787
_state: Dict[str, Any] = {"running": False, "progress": "", "outputs": [],
                          "error": ""}
_lock = threading.Lock()

_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>🔍 Sherlock 侦查台</title>
<style>
  body{margin:0;background:radial-gradient(circle at 50% -15%,#35291f 0,#181411 48%,#0d0b09 100%);color:#e8d5b5;font-family:Georgia,'Songti SC',serif;min-height:100vh;display:grid;place-items:center}
  .card{width:min(520px,92vw);background:#17130f;border:1px solid #4b3d30;border-radius:8px;padding:36px;box-shadow:0 16px 42px rgba(8,5,3,.4)}
  h1{font-size:22px;letter-spacing:.12em;color:#d4a017;margin:0 0 6px}
  .sub{font:10px Arial;letter-spacing:.24em;color:#8f816d;margin-bottom:28px}
  .step{margin:18px 0;padding:14px;border:1px solid #342c24;border-radius:4px;background:#1b1612}
  .step b{display:block;font:11px Arial;letter-spacing:.15em;color:#c7a45e;margin-bottom:8px}
  input{width:100%;box-sizing:border-box;background:#0f0c09;border:1px solid #4b3d30;color:#e8d5b5;padding:10px 12px;border-radius:3px;font:14px Georgia}
  button{width:100%;margin-top:10px;border:1px solid #97763e;background:linear-gradient(#3f3020,#2b2118);color:#e8ce95;padding:11px;border-radius:3px;font-size:13px;letter-spacing:.1em;cursor:pointer}
  button:hover{background:#4b3925}
  button:disabled{opacity:.4;cursor:wait}
  #status{margin-top:16px;font:12px Arial;color:#9a8c79;line-height:1.7}
  a{color:#d4a017;text-decoration:none;border-bottom:1px dashed #6b5739}
  .err{color:#d96a5f}
</style></head><body>
<div class="card">
  <h1>🔍 Sherlock 侦查台</h1>
  <div class="sub">SHERLOCK · 抖音社交关系侦查</div>
  <div class="step"><b>① 登录抖音</b><button onclick="act('login')">弹出浏览器扫码登录</button></div>
  <div class="step"><b>② 目标主页链接</b>
    <input id="url" placeholder="粘贴抖音个人主页链接, 如 https://www.douyin.com/user/MS4w...">
  </div>
  <div class="step"><b>③ 开始侦查</b><button id="go" onclick="act('run')">一键采集+分析+生成报告</button></div>
  <div id="status">就绪。</div>
</div>
<script>
async function act(kind){
  const st=document.getElementById('status');
  if(kind==='login'){
    st.textContent='浏览器已弹出, 请扫码登录(完成后本页无需操作)…';
    const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'}});
    const d=await r.json(); st.textContent=d.msg;
    return;
  }
  const url=document.getElementById('url').value.trim();
  if(!url){st.textContent='请先粘贴主页链接';st.className='err';return;}
  document.getElementById('go').disabled=true;
  st.textContent='侦查进行中…';st.className='';
  const r=await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({url})});
  const d=await r.json(); if(d.error){st.textContent=d.error;st.className='err';document.getElementById('go').disabled=false;return;}
  poll();
}
async function poll(){
  const st=document.getElementById('status');
  for(let i=0;i<300;i++){
    await new Promise(r=>setTimeout(r,2000));
    const r=await fetch('/status'); const d=await r.json();
    if(d.running){st.textContent=d.progress||'侦查进行中…';continue;}
    document.getElementById('go').disabled=false;
    if(d.error){st.textContent=d.error;st.className='err';return;}
    st.innerHTML=d.outputs.map(o=>'<a href="/files/'+o+'">'+o+'</a>').join('<br>')||'无产出';
    if(d.outputs.length){d.outputs.forEach(o=>{if(o.endsWith('.html'))window.open('/files/'+o);});}
    return;
  }
  document.getElementById('go').disabled=false; st.textContent='超时, 请查看终端日志。';
}
</script></body></html>"""


def _run_pipeline(url: str) -> None:
    """后台执行完整管线, 进度写入 _state。"""
    from sherlock import analyze, board, collect, graph, report, suspects

    def note(msg: str) -> None:
        with _lock:
            _state["progress"] = msg

    try:
        sec_uid = url.split("/user/")[-1].split("?")[0] if "/user/" in url else url
        note("正在采集线索(作品/评论/对话/粉丝)…")
        collect.main(sec_uid)
        note("正在交叉分析…")
        data = analyze.load_all()
        md = report.build_report(data)
        rp = report.save_report(md)
        sus = suspects.detect(data)
        gd = analyze.build_graph_data(data)
        gp = graph.render_sherlock(gd)
        from sherlock.reason import build_reasoning_chain
        order = {"高": 0, "中": 1}
        top = sorted(sus, key=lambda x: (order.get(x["severity"], 2),
                                         -x.get("score", 0)))[:6]
        cases = []
        for i, s in enumerate(top, 1):
            chain = build_reasoning_chain(s)
            chain["id"] = "case-%d" % i
            chain["caseId"] = "AUTO-%02d" % i
            chain["status"] = "自动分析·待人工复核"
            cases.append(chain)
        bp = board.render_cases(cases, graph_link="福尔摩斯线索墙.html")
        with _lock:
            _state["outputs"] = [os.path.basename(p) for p in (rp, gp, bp)]
            _state["progress"] = "完成"
    except Exception as e:  # 顶层兜底, 错误呈现给用户
        with _lock:
            _state["error"] = str(e)[:200]
    finally:
        with _lock:
            _state["running"] = False


class Handler(BaseHTTPRequestHandler):
    """极简路由: 页面 / 登录 / 运行 / 状态 / 产物下载。"""

    def _json(self, obj: Dict[str, Any]) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        # 防 DNS rebinding: Host 必须是本机回环
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._json({"error": "拒绝访问"})
            return
        path = urlparse(self.path).path
        if path == "/":
            body = _PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/status":
            with _lock:
                self._json(dict(_state))
            return
        if path.startswith("/files/"):
            name = os.path.basename(path)
            fp = os.path.join(_BASE, "analysis_output", name)
            if os.path.isfile(fp):
                body = open(fp, "rb").read()
                ctype = {"csv": "text/csv; charset=utf-8",
                         "json": "application/json; charset=utf-8",
                         "md": "text/plain; charset=utf-8",
                         "js": "text/javascript"}.get(
                    name.rsplit(".", 1)[-1].lower(), "text/html; charset=utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("X-Content-Type-Options", "nosniff")
                # 原始数据(csv/json/md)强制下载, 不在浏览器渲染(防内容嗅探)
                if not ctype.startswith("text/html"):
                    self.send_header("Content-Disposition",
                                     'attachment; filename="%s"' % name)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._json({"error": "文件不存在"})
            return
        self._json({"error": "not found"})

    def do_POST(self) -> None:
        # 防 CSRF: 仅接受本页面 JSON 请求, 拒绝跨站(form 型请求会被拦下)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self._json({"error": "仅接受 JSON 请求"})
            return
        origin = self.headers.get("Origin") or ""
        if origin and origin not in ("http://127.0.0.1:%d" % _PORT,
                                     "http://localhost:%d" % _PORT):
            self._json({"error": "跨站请求已拒绝"})
            return
        path = urlparse(self.path).path
        if path == "/login":
            threading.Thread(target=self._login, daemon=True).start()
            self._json({"msg": "已弹出浏览器, 请扫码登录"})
            return
        if path == "/run":
            n = int(self.headers.get("Content-Length") or 0)
            url = json.loads(self.rfile.read(n)).get("url", "")
            with _lock:
                if _state["running"]:
                    self._json({"error": "已有侦查任务进行中"})
                    return
                _state.update(running=True, progress="启动中", outputs=[],
                              error="")
            threading.Thread(target=_run_pipeline, args=(url,),
                             daemon=True).start()
            self._json({"ok": True})
            return
        self._json({"error": "not found"})

    @staticmethod
    def _login() -> None:
        from sherlock.headless import new_page
        page = new_page(port=9345, headless=False)
        page.get("https://www.douyin.com/")

    def log_message(self, *args) -> None:
        pass


def main(port: int = _PORT) -> None:
    """启动服务并打开浏览器。"""
    import webbrowser
    print("🔍 Sherlock 侦查台: http://127.0.0.1:%d" % port)
    webbrowser.open("http://127.0.0.1:%d" % port)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
