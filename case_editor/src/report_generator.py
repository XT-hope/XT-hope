# generate_report_full.py
# 功能：
# - 交互式 Plotly 报告（饼图 + 2x2 统计 + 目录搜索联想 + 每个用例：可折叠 + 上方曲线图 + 中间测试点表格 + AI分析报告 + 下方表格）
# - 仅保留 Plotly 内置图例，放在图底部（横向），避免与表格重叠
# - 去掉"耗时"列；修正工具栏溢出
# - 优先内联 plotly.js（可离线单文件）；失败则使用 CDN
# - 在每个case的折线图和表格之间添加测试点表格和AI分析报告区域

from __future__ import annotations
from typing import Dict, Any, List, Optional
from pathlib import Path
import json

# 可选：内联 plotly.js（成功则生成单文件可离线使用；失败走 CDN）
_PLOTLY_INLINE_JS: Optional[str] = None
try:
    from plotly.offline import get_plotlyjs  # type: ignore
    _PLOTLY_INLINE_JS = get_plotlyjs()
except Exception:
    _PLOTLY_INLINE_JS = None

import plotly.graph_objects as go
import plotly.io as pio


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _plotly_loader(inline_js: Optional[str]) -> str:
    if inline_js:
        return "<script>" + inline_js + "</script>"
    return '<script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>'


def _make_pie_div(total: int, passed: int, failed: int, errored: int) -> str:
    fig = go.Figure(
        go.Pie(
            labels=["PASS", "FAIL", "ERROR"],
            values=[passed, failed, errored],
            hole=0.25,
            marker=dict(colors=["#22c55e", "#ef4444", "#f59e0b"]),
            textinfo="label+value+percent",
            hoverinfo="label+value+percent",
        )
    )
    fig.update_layout(
        height=260, #260
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(font=dict(color="#cbd5e1")),
    )
    return pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        config=dict(responsive=True, displaylogo=False),
    )


def build_report_html(report: Dict[str, Any], inline_plotly_js: Optional[str] = _PLOTLY_INLINE_JS) -> str:
    cases: List[Dict[str, Any]] = list(report.get("cases", []))
    passed = sum(1 for c in cases if str(c.get("status", "")).upper() == "PASS")
    failed = sum(1 for c in cases if str(c.get("status", "")).upper() == "FAIL")
    errored = sum(1 for c in cases if str(c.get("status", "")).upper() not in ("PASS", "FAIL"))
    total = len(cases)

    title = _html_escape(str(report.get("reportTitle", "测试执行报告")))
    plotly_loader = _plotly_loader(inline_plotly_js)

    css = """<style>
:root{
  --bg:#0f172a;--card:#111827;--muted:#94a3b8;--text:#e5e7eb;--border:#1f2937;
  --chip:#1f2937;--chip-hover:#374151;--ok:#22c55e;--fail:#ef4444;--err:#f59e0b;--hl:#38bdf8
}
*{box-sizing:border-box} html,body{height:100%}
body{
  margin:0;background:linear-gradient(180deg,#0b1220,#0f172a 40%);color:var(--text);
  font:14px/1.6 system-ui,-apple-system,Segoe UI,Roboto,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale
}
a{color:#93c5fd;text-decoration:none} a:hover{text-decoration:underline}
.container{max-width:1200px;margin:0 auto;padding:24px 16px}
header{
  padding:24px;border:1px solid var(--border);background:var(--card);
  border-radius:16px;box-shadow:0 10px 30px rgba(2,6,23,.6),inset 0 1px 0 rgba(255,255,255,.03);
  margin-bottom:20px
}
header h1{margin:0 0 8px;font-size:28px;font-weight:700;letter-spacing:.3px}
header .meta{color:var(--muted);display:flex;flex-wrap:wrap;gap:12px}
.grid{display:grid;gap:16px} @media(min-width:900px){.grid.cols-2{grid-template-columns:1fr 1fr}}
.card{
  background:linear-gradient(180deg,rgba(255,255,255,.03),transparent),var(--card);
  border:1px solid var(--border);border-radius:14px;padding:18px;box-shadow:0 8px 24px rgba(0,0,0,.35)
}
.card h2{margin:0 0 12px;font-size:18px;letter-spacing:.2px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.stat{background:var(--chip);border:1px solid var(--border);border-radius:12px;padding:14px}
.stat .label{color:var(--muted);font-size:12px}
.stat .value{font-size:20px;font-weight:700;margin-top:6px}
.stat.accent .value{color:var(--ok)} .stat.fail .value{color:var(--fail)} .stat.err .value{color:var(--err)}
.dir-wrap{display:flex;flex-direction:column;gap:10px}
.search{display:flex;gap:8px;position:relative}
.search input{
  flex:1;padding:10px 12px;border-radius:10px;border:1px solid var(--border);
  background:#0b1020;color:var(--text);outline:none
}
.search button{
  padding:10px 14px;border-radius:10px;border:1px solid var(--border);
  background:#0b1020;color:var(--text);cursor:pointer
}
.search button:hover{background:#0d1325}
.suggest{
  position:absolute;top:44px;left:0;right:0;background:#0b1020;border:1px solid var(--border);
  border-radius:10px;max-height:220px;overflow:auto;z-index:20;display:none
}
.suggest-item{padding:8px 10px;cursor:pointer}
.suggest-item:hover,.suggest-item.active{background:var(--chip-hover)}
.case-list{
  border:1px solid var(--border);border-radius:12px;background:#0c1224;max-height:260px;overflow:auto;padding:8px
}
.case-item{display:block;padding:8px 10px;border-radius:8px;color:var(--text)}
.case-item:hover{background:var(--chip-hover)}

/* Case 折叠块 */
.case-card{border:1px solid var(--border);border-radius:12px;background:var(--card);margin-bottom:14px;overflow:hidden}
.case-card[open]{box-shadow:0 8px 24px rgba(0,0,0,.25)}
.case-card summary{list-style:none;cursor:pointer;padding:12px 14px;display:flex;align-items:center;gap:10px;background:linear-gradient(180deg, rgba(255,255,255,.03), transparent)}
.case-card summary::-webkit-details-marker{display:none}
.case-title-text{font-weight:700}
.case-meta{color:var(--muted);font-size:12px;margin-left:auto}
.chev{transition:transform .2s ease}
.case-card[open] .chev{transform:rotate(90deg)}

/* 图与表：表在图下方；工具栏不溢出 */
.plot{width:100%;height:300px;border:1px solid var(--border);border-radius:10px;background:#0b1020;margin:10px 14px 10px;overflow:hidden;position:relative}
.plot .modebar{right:8px!important;top:8px!important;left:auto!important}
.plot .modebar-container{right:8px!important;top:8px!important;left:auto!important}
.table-wrap{padding:0 14px 14px}
.ai-report-wrap{padding:0 14px 14px}
table{width:100%;border-collapse:separate;border-spacing:0;overflow:hidden;border-radius:12px;border:1px solid var(--border);background:#0b1020}
th,td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--muted);font-weight:600;text-align:left;background:#0f152b}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700}
.ok{background:rgba(34,197,94,.15);color:#86efac;border:1px solid rgba(34,197,94,.25)}
.fail{background:rgba(239,68,68,.15);color:#fca5a5;border:1px solid rgba(239,68,68,.25)}
.err{background:rgba(245,158,11,.15);color:#fcd34d;border:1px solid rgba(245,158,11,.25)}
.pie{width:100%;height:260px}

/* AI报告样式 - 背景色与表格一致 */
.ai-report {
  background: #0b1020; /* 与表格背景色一致 */
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-top: 10px;
  white-space: pre-wrap;
  font-family: monospace;
  color: var(--text); /* 与表格文字颜色一致 */
  overflow-x: auto;
}
</style>"""

    header = (
        '<header>\n'
        f'  <h1 id="report-title">{title}</h1>\n'
        f'  <div class="meta">生成日期：<span id="meta-date">{_html_escape(str(report.get("generatedAt","-")))}</span> ｜ '
        f'作者：<span id="meta-author">{_html_escape(str(report.get("author","-")))}</span> ｜ '
        f'用例总数：<span id="meta-total">{total}</span></div>\n'
        "</header>\n"
    )

    pie_div = _make_pie_div(total, passed, failed, errored)
    left_html = (
        '<section class="card"><h2>Results Distribution</h2>'
        '<div class="pie">' + pie_div + "</div></section>\n"
    )
    pass_rate = f"{(passed/total*100):.1f}%" if total else "-"
    stats_html = (
        '<section class="card">\n'
        "  <h2>Run Info</h2>\n"
        '  <div class="stats">\n'
        f'    <div class="stat"><div class="label">Test Cases</div><div class="value">{total}</div></div>\n'
        f'    <div class="stat accent"><div class="label">Pass Rate</div><div class="value">{pass_rate}</div></div>\n'
        f'    <div class="stat fail"><div class="label">Failures</div><div class="value">{failed}</div></div>\n'
        f'    <div class="stat err"><div class="label">Errors</div><div class="value">{errored}</div></div>\n'
        "  </div>\n"
        "</section>\n"
    )

    # 目录（锚点 + 搜索 + 联想下拉）
    case_list_items = []
    for c in cases:
        cid = str(c.get("id", ""))
        anchor = "case-" + "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in cid)
        case_list_items.append(f'<a class="case-item" href="#{anchor}">{_html_escape(cid)}</a>')
    directory = (
        '<section class="card" style="grid-column:1/-1">\n'
        "  <h2>Test Case Directory</h2>\n"
        '  <div class="dir-wrap">\n'
        '    <div class="search">\n'
        '      <input id="searchInput" placeholder="搜索 Case ID，例如：CASE-001"/>\n'
        '      <button id="searchBtn">搜索</button>\n'
        '      <div id="searchSuggest" class="suggest"></div>\n'
        "    </div>\n"
        f'    <div class="case-list" id="caseList" role="listbox" aria-label="Case List">{"".join(case_list_items)}</div>\n'
        "  </div>\n"
        "</section>\n"
    )

    # 每个用例为一个可折叠块（details/summary），内部：上方曲线图 + 测试点表格 + AI分析报告 + 下方表格（3列：步骤/状态/信息）
    cases_container = ['<section class="card" style="grid-column:1/-1"><div id="casesContainer">']
    case_signals: Dict[str, Dict[str, List[List[float]]]] = {}

    for c in cases:
        cid = str(c.get("id", ""))
        anchor = "case-" + "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in cid)
        status = str(c.get("status", "")).upper()
        badge_class = "ok" if status == "PASS" else ("fail" if status == "FAIL" else "err")
        badge = f'<span class="badge {badge_class}">{status or "-"}</span>'
        dur_ms = c.get("duration_ms", None)
        dur_text = f"{dur_ms} ms" if isinstance(dur_ms, (int, float)) else "-"

        sigs = c.get("signals")
        if not sigs:
            series_one = c.get("series") or []
            sigs = {"Signal": series_one}
        case_signals[anchor] = sigs

        # 获取测试点信息（直接从case对象获取）
        test_point = c.get("test_point", "")
        
        # 创建测试点表格HTML
        test_point_table_html = (
            '<table>'
            '<thead><tr>'
            '<th style="width:20%">属性</th>'
            '<th>内容</th>'
            '</tr></thead>'
            '<tbody>'
            f'<tr><td>测试点</td><td>{_html_escape(str(test_point))}</td></tr>'
            '</tbody>'
            '</table>'
        )

        # 获取AI分析报告（直接从case对象获取）
        ai_report = c.get("ai_report", "")
        
        # 创建AI分析报告HTML区域
        ai_report_html = ""
        if ai_report:
            ai_report_html = (
                '<div class="ai-report-wrap">'
                '<h3>AI分析报告</h3>'
                '<div class="ai-report">' + _html_escape(str(ai_report)) + '</div>'
                '</div>'
            )

        # 行（去掉耗时）
        rows_html = []
        steps = c.get("steps") or []
        if steps:
            for s in steps:
                name = _html_escape(str(s.get("name", "-")))
                st = _html_escape(str(s.get("status", "")))
                st_cls = "ok" if st.upper() == "PASS" else ("fail" if st.upper() == "FAIL" else "err")
                st_badge = f'<span class="badge {st_cls}">{st or "-"}</span>'
                msg = _html_escape(str(s.get("message", "")))
                rows_html.append(f"<tr><td>{name}</td><td>{st_badge}</td><td>{msg}</td></tr>")
        else:
            rows_html.append('<tr><td colspan="3" style="color:var(--muted)">无步骤明细</td></tr>')

        table_html = (
            '<table>'
            '<thead><tr>'
            '<th style="width:30%">步骤</th>'
            '<th style="width:12%">状态</th>'
            '<th>信息</th>'
            '</tr></thead>'
            '<tbody>' + "".join(rows_html) + '</tbody>'
            '</table>'
        )

        cases_container.append(
            '<details class="case-card" id="' + anchor + '" open>'
            '  <summary>'
            '    <span class="chev">▶</span>'
            '    <span class="case-title-text">' + _html_escape(cid) + '</span>'
            '    &nbsp; ' + badge +
            '    <span class="case-meta">总时长：' + _html_escape(dur_text) + '</span>'
            '  </summary>'
            '  <div class="plot" id="plot-' + anchor + '"></div>'
            '  <div class="table-wrap">' + test_point_table_html + '</div>'  # 测试点表格
            '  <div class="table-wrap">' + table_html + '</div>'
            '  ' + ai_report_html + ''  # AI分析报告区域
            '</details>'
        )

    cases_container.append("</div></section>")
    cases_html = "".join(cases_container)

    # 搜索 + 联想下拉脚本（跳转时自动展开对应 case）
    search_js = """
<script>
(function(){
  var input = document.getElementById('searchInput');
  var btn = document.getElementById('searchBtn');
  var sugg = document.getElementById('searchSuggest');
  var ids = Array.prototype.map.call(document.querySelectorAll('#caseList .case-item'), function(a){ return a.textContent || ''; });
  var active = -1;
  function openAndGoto(anchor){
    var el = document.getElementById(anchor);
    if(el && typeof el.open !== 'undefined'){ el.open = true; }
    if(el){ el.scrollIntoView({behavior:'smooth', block:'start'}); }
  }
  function hide(){ sugg.style.display='none'; sugg.innerHTML=''; active=-1; }
  function show(matches){
    if(!matches.length){ hide(); return; }
    var html = '';
    for(var i=0;i<matches.length;i++){
      html += '<div class="suggest-item" data-id="'+ matches[i].replace(/"/g,'&quot;') +'">'+ matches[i] +'</div>';
    }
    sugg.innerHTML = html; sugg.style.display = 'block'; active = -1;
  }
  function gotoCaseById(id){
    var anchor = 'case-' + String(id).replace(/[^a-zA-Z0-9_-]+/g,'-');
    openAndGoto(anchor); hide();
  }
  function onInput(){
    var q = (input.value||'').trim().toLowerCase();
    if(!q){ hide(); return; }
    var m = ids.filter(function(id){ return String(id).toLowerCase().indexOf(q) !== -1; }).slice(0,20);
    show(m);
  }
  function onClick(e){
    var t = e.target;
    if(t && t.classList.contains('suggest-item')){
      gotoCaseById(t.getAttribute('data-id')||'');
    }
  }
  function onKey(e){
    var items = sugg.querySelectorAll('.suggest-item');
    if(!items.length) return;
    if(e.key === 'ArrowDown'){ active = (active+1) % items.length; }
    else if(e.key === 'ArrowUp'){ active = (active-1+items.length) % items.length; }
    else if(e.key === 'Enter'){
      if(active>=0 && active<items.length){
        gotoCaseById(items[active].getAttribute('data-id')||''); e.preventDefault();
      }else{ doSearch(); }
      return;
    }else{return;}
    for(var i=0;i<items.length;i++) items[i].classList.toggle('active', i===active);
    e.preventDefault();
  }
  function doSearch(){
    var q = (input.value||'').trim().toLowerCase();
    if(!q) return;
    for(var i=0;i<ids.length;i++){
      if(String(ids[i]).toLowerCase().indexOf(q)!==-1){ gotoCaseById(ids[i]); return; }
    }
    alert('未找到匹配的 Case ID');
  }
  if(btn) btn.addEventListener('click', doSearch);
  if(input) input.addEventListener('input', onInput);
  if(input) input.addEventListener('keydown', onKey);
  if(sugg) sugg.addEventListener('mousedown', function(e){ e.preventDefault(); });
  if(sugg) sugg.addEventListener('click', onClick);
  document.addEventListener('click', function(e){
    if(!sugg.contains(e.target) && e.target!==input) hide();
  });
})();
</script>
"""

    # 多信号绘图脚本（图例放到底部，避免与表重叠；无表下方选择）
    multi_signal_js_tpl = r"""
<script>
(function(){
  const CASE_SIGNALS = __CASE_SIGNALS__;
  const SIG_COLORS = ['#38bdf8','#f59e0b','#22c55e','#ef4444','#a78bfa','#f472b6','#34d399','#f87171'];

  function pairsToTrace(name, pairs, color){
    var x=[], y=[];
    for (var i=0;i<pairs.length;i++){ x.push(+pairs[i][0]); y.push(+pairs[i][1]); }
    return {name:name,x:x,y:y,type:'scatter',mode:'lines',line:{color:color,width:2},
      hovertemplate:'t=%{x:.6f}s<br>v=%{y}<extra>'+name+'</extra>'};
  }

  var baseLayout = {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    margin:{l:60, r:20, t:30, b:90},  // 底部留空间给图例
    dragmode:'zoom', hovermode:'x unified',
    showlegend:true,
    legend:{
      orientation:'h',
      x:0, xanchor:'left',
      y:-0.2, yanchor:'top',   // 放在底部（图外侧下方）
      bgcolor:'rgba(15,23,42,0.6)',
      bordercolor:'rgba(148,163,184,0.25)', borderwidth:1,
      font:{color:'#cbd5e1'}
    },
    xaxis:{ title:{text:'时间 (s)'}, tickformat:'.3f',
      gridcolor:'rgba(148,163,184,0.12)', zerolinecolor:'rgba(148,163,184,0.25)',
      showspikes:true, spikemode:'across', spikesnap:'cursor', spikecolor:'#38bdf8', spikethickness:1 },
    yaxis:{ title:{text:'信号值'},
      gridcolor:'rgba(148,163,184,0.08)', zerolinecolor:'rgba(148,163,184,0.25)',
      showspikes:true, spikemode:'toaxis', spikesnap:'cursor', spikecolor:'#38bdf8', spikethickness:1 }
  };
  var baseConfig = { responsive:true, displaylogo:false, scrollZoom:true, doubleClick:'reset' };

  function setupCase(anchor, signals){
    var plotDiv = document.getElementById('plot-'+anchor);
    if(!plotDiv) return;
    var traces = [], keys = Object.keys(signals||{});
    for (var i=0;i<keys.length;i++){
      var name = keys[i];
      traces.push(pairsToTrace(name, signals[name]||[], SIG_COLORS[i % SIG_COLORS.length]));
    }
    Plotly.newPlot(plotDiv, traces, baseLayout, baseConfig);
  }

  for (var anchor in CASE_SIGNALS){
    if(Object.prototype.hasOwnProperty.call(CASE_SIGNALS, anchor)){
      setupCase(anchor, CASE_SIGNALS[anchor]);
    }
  }
})();
</script>
"""
    case_signals_json = json.dumps(case_signals, ensure_ascii=False).replace("</", "<\\/")
    multi_signal_js = multi_signal_js_tpl.replace("__CASE_SIGNALS__", case_signals_json)

    html = (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n"
        '<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>\n'
        "<title>" + title + "</title>\n"
        + css + "\n" + plotly_loader + "\n"
        "</head>\n<body>\n"
        '<div class="container">\n'
        + header +
        '<main class="grid cols-2">\n'
        + left_html + stats_html + directory + "".join(cases_container) +
        "</main>\n"
        "</div>\n"
        + search_js + "\n" + multi_signal_js + "\n"
        "</body>\n</html>"
    )
    return html


if __name__ == "__main__":
    # 示例：两组信号（用于图例点选）+ 一个旧字段兼容（series）
    series_ref = [
        (0.0, 0.0), (0.10582, 1.0), (0.200021, 2.0), (0.300032, 3.0), (0.400066, 4.0),
        (0.500077, 4.0), (0.600416, 6.0), (0.698695, 8.0), (0.800094, 9.0), (0.900099, 10.0),
        (1.000112, 11.0), (1.105843, 12.0), (1.199948, 13.0), (1.298902, 14.0), (1.399928, 15.0),
        (1.498692, 16.0), (1.598911, 18.0), (1.698628, 19.0), (1.798609, 20.0), (1.898629, 21.0),
        (1.998682, 22.0), (2.104259, 23.0), (2.198777, 24.0), (2.298668, 25.0), (2.400036, 26.0),
        (2.500159, 27.0), (2.600417, 27.0), (2.700033, 30.0), (2.80007, 31.0), (2.90008, 32.0),
        (3.000148, 33.0), (3.105618, 34.0), (3.200112, 34.0), (3.300081, 35.0), (3.400179, 37.0),
        (3.499902, 37.0), (3.600265, 40.0), (3.69855, 41.0), (3.798576, 42.0)
    ]
    series_b = [(t, v * 0.8 + (5.0 if (i % 5 == 0) else 0.0)) for i, (t, v) in enumerate(series_ref)]

    report = {
        "reportTitle": "融合版报告（图例底部、工具栏不溢出、无耗时列）",
        "generatedAt": "2025-09-30 10:00:00",
        "author": "Tester",
        "cases": [
            {
                "id": "CASE-TEST-A", "status": "PASS", "duration_ms": 1234,"test_point":"弯道抑制",
                "signals": {"Signal_A": series_ref, "Signal_B": series_b},
                "steps": [
                    {"name":"初始化","status":"PASS","message":"OK","duration_ms":120},
                    {"name":"登录","status":"PASS","message":"OK","duration_ms":210}
                ],
               "ai_report":"[测试意图与步骤总结]\n1.  **测试目标**: 验证弯道超速报警 (CSW) 功能中的弯中超速报警 (DCSW) 负响应场景。具体测试在半径为1000米的弯道中，当车速低于功能激活阈值（148 km/h）时，CSW功能不应被触发。\n2.  **测试场景**: 车辆在晴天、干燥、能见度良好的1000米半径弯道（车道线为虚线）上行驶，初始速度为30 km/h，保持车速低于148 km/h，无其他车辆干扰。\n3.  **测试步骤**:\n    *   **准备**: 设置场景，并开启CSW功能开关 (`CSW_Enable_S = 1`)。\n    *   **初始化**: 加载指定的弯道场景文件。\n    *   **执行条件**: 挂入D档 (`Rnk_hw = 4`)，使车辆进入可行驶状态。\n    *   **核心检查**: 在5秒的检查窗口内，持续监控CSW状态信号 (`CSW_Stats_S`)，其值应保持为2（代表“弯中超速报警未触发”或“功能未激活”状态）。这是验证负响应的关键检查点。"
            },
            {
                "id": "CASE-TEST-B", "status": "FAIL", "duration_ms": 980,"test_point":"弯道激活",
                "series": [(0,0),(0.2,0.5),(0.4,0.2),(0.6,0.8),(0.8,0.1),(1.0,0.9)],
                "steps": [{"name":"流程X","status":"FAIL","message":"断言失败","duration_ms":860}],
              "ai_report":"[测试意图与步骤总结]\n1.  **测试目标**: 验证弯道超速报警 (CSW) 功能中的弯中超速报警 (DCSW) 负响应场景。具体测试在半径为1000米的弯道中，当车速低于功能激活阈值（148 km/h）时，CSW功能不应被触发。\n2.  **测试场景**: 车辆在晴天、干燥、能见度良好的1000米半径弯道（车道线为虚线）上行驶，初始速度为30 km/h，保持车速低于148 km/h，无其他车辆干扰。\n3.  **测试步骤**:\n    *   **准备**: 设置场景，并开启CSW功能开关 (`CSW_Enable_S = 1`)。\n    *   **初始化**: 加载指定的弯道场景文件。\n    *   **执行条件**: 挂入D档 (`Rnk_hw = 4`)，使车辆进入可行驶状态。\n    *   **核心检查**: 在5秒的检查窗口内，持续监控CSW状态信号 (`CSW_Stats_S`)，其值应保持为2（代表“弯中超速报警未触发”或“功能未激活”状态）。这是验证负响应的关键检查点。"
            }
        ]
    }

    html = build_report_html(report, inline_plotly_js=_PLOTLY_INLINE_JS)
    out = Path("report_plotly_full6.html")
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out.resolve()}，直接打开即可（内联可离线；否则需联网加载 CDN）。")
