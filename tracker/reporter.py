"""
HTML 대시보드 생성기
- output/data/YYYY-MM-DD.json  날짜별 데이터 적재
- output/data/index.json       날짜 목록 인덱스
- output/dashboard.html        날짜 선택 SPA
"""
import base64
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SOURCE_COLORS = {
    "zeta":          "#7c3aed",
    "crack":         "#dc2626",
    "rofan":         "#f59e0b",
    "naver_webtoon": "#059669",
    "ridi":          "#2563eb",
    "kakaopage":     "#d97706",
    "sample":        "#6b7280",
}
SOURCE_LABELS = {
    "zeta":          "Zeta AI",
    "crack":         "Crack AI",
    "rofan":         "Rofan AI",
    "naver_webtoon": "네이버 웹툰",
    "ridi":          "리디북스",
    "kakaopage":     "카카오페이지",
    "sample":        "샘플",
}


def make_avatar_svg(name: str) -> str:
    initial = name[0].upper() if name else "?"
    colors = ["#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626", "#0891b2"]
    color = colors[hash(name) % len(colors)]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
  <defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" style="stop-color:{color}"/>
    <stop offset="100%" style="stop-color:{color}88"/>
  </linearGradient></defs>
  <rect width="200" height="200" fill="url(#g)" rx="12"/>
  <text x="100" y="130" text-anchor="middle" font-size="80" font-family="sans-serif" fill="white" font-weight="bold">{initial}</text>
</svg>'''
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ──────────────────────────────────────────────
# JSON 저장 & 인덱스 관리
# ──────────────────────────────────────────────

def _char_dict(sc) -> dict:
    c = sc.character
    return {
        "name": c.name,
        "source": c.source,
        "description": c.description,
        "tags": c.tags,
        "interaction_count": c.interaction_count,
        "url": c.url or "",
        "image_url": c.image_url or "",
        "g3": sc.g3, "g4": sc.g4, "g5": sc.g5,
        "total": sc.total,
        "reason": sc.reason or "",
        "unx_fit": sc.unx_fit or "",
    }


def _raw_char_dict(c) -> dict:
    return {
        "name": c.name,
        "source": c.source,
        "description": c.description,
        "tags": c.tags,
        "interaction_count": c.interaction_count,
        "url": c.url or "",
        "image_url": c.image_url or "",
    }


def save_date_data(top_k: list, all_chars: list, cfg, run_meta: dict) -> Path:
    """날짜별 JSON 저장 + index.json 갱신 → 경로 반환"""
    date_str = run_meta.get("date", datetime.now().strftime("%Y-%m-%d"))
    data_dir = Path(cfg.output_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 날짜 데이터
    payload = {
        "date": date_str,
        "generated_at": run_meta.get("generated_at", datetime.now().isoformat()),
        "sources": run_meta.get("sources_used", []),
        "total_collected": len(all_chars),
        "top5": [_char_dict(sc) for sc in top_k],
        "all_chars": [_raw_char_dict(c) for c in all_chars],
    }
    date_path = data_dir / f"{date_str}.json"
    date_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[Reporter] 날짜 데이터 저장: {date_path}")

    # index.json 갱신
    index_path = data_dir / "index.json"
    dates: list[str] = []
    if index_path.exists():
        try:
            dates = json.loads(index_path.read_text(encoding="utf-8")).get("dates", [])
        except Exception:
            dates = []
    if date_str not in dates:
        dates.append(date_str)
    dates = sorted(set(dates), reverse=True)
    index_path.write_text(
        json.dumps({"dates": dates, "latest": dates[0] if dates else date_str}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # web/public/data/ 에도 미러 (Vercel용)
    web_data = Path(__file__).parent.parent / "web" / "public" / "data"
    if web_data.parent.exists():
        web_data.mkdir(parents=True, exist_ok=True)
        (web_data / f"{date_str}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (web_data / "index.json").write_text(
            json.dumps({"dates": dates, "latest": dates[0]}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info(f"[Reporter] Vercel 데이터 미러: {web_data}")

    return date_path


# ──────────────────────────────────────────────
# SPA HTML 생성 (날짜 선택 + 동적 렌더)
# ──────────────────────────────────────────────

SPA_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>UNX Character Tracker</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI','Noto Sans KR',sans-serif;background:#0f0f1a;color:#e2e8f0;min-height:100vh;display:flex;flex-direction:column}
a{color:inherit;text-decoration:none}
a:hover{text-decoration:underline}

/* Layout */
.app{display:flex;flex:1;min-height:0}
.sidebar{width:200px;min-width:160px;background:#13131f;border-right:1px solid #2d3748;padding:16px 0;overflow-y:auto;flex-shrink:0}
.main{flex:1;overflow-y:auto;padding:28px 32px}

/* Header */
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);border-bottom:1px solid #2d3748;padding:18px 28px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.header h1{font-size:1.4rem;font-weight:700;background:linear-gradient(90deg,#a78bfa,#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.header-meta{font-size:0.78rem;color:#94a3b8;text-align:right;line-height:1.6}
.source-tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:3px}
.source-tag{font-size:0.68rem;padding:2px 8px;border-radius:12px;font-weight:600;color:#fff}

/* Sidebar date list */
.sidebar-title{font-size:0.7rem;font-weight:700;color:#64748b;letter-spacing:.1em;padding:0 16px 8px;text-transform:uppercase}
.date-btn{display:block;width:100%;text-align:left;padding:9px 16px;font-size:0.82rem;color:#94a3b8;background:none;border:none;cursor:pointer;transition:background .15s,color .15s}
.date-btn:hover{background:#1e1e30;color:#e2e8f0}
.date-btn.active{background:#1e1e30;color:#a78bfa;font-weight:700;border-left:3px solid #a78bfa}
.date-btn.today::after{content:'오늘';font-size:.65rem;background:#7c3aed;color:#fff;padding:1px 5px;border-radius:6px;margin-left:6px;vertical-align:middle}

/* Section title */
.section-title{font-size:1rem;font-weight:700;color:#a78bfa;margin-bottom:18px;padding-bottom:7px;border-bottom:1px solid #2d3748;letter-spacing:.05em}
.date-headline{font-size:.8rem;color:#64748b;margin-bottom:18px}

/* Card grid */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px;margin-bottom:32px}

/* Card */
.card{background:#1a1a2e;border:1px solid #2d3748;border-radius:14px;overflow:hidden;transition:transform .2s,box-shadow .2s}
.card:hover{transform:translateY(-4px);box-shadow:0 8px 30px rgba(167,139,250,.15)}
.card-image{position:relative;width:100%;aspect-ratio:1/1;background:#0f0f1a;overflow:hidden}
.card-image img{width:100%;height:100%;object-fit:cover;display:block}
.rank-badge{position:absolute;top:10px;left:10px;background:rgba(0,0,0,.75);color:#fbbf24;font-size:.85rem;font-weight:800;padding:3px 10px;border-radius:20px;border:1px solid #fbbf24;backdrop-filter:blur(4px)}
.source-badge{position:absolute;bottom:10px;right:10px;font-size:.65rem;font-weight:700;padding:3px 8px;border-radius:10px;color:#fff;backdrop-filter:blur(4px)}
.card-body{padding:13px 15px 15px}
.char-name{display:block;font-size:.95rem;font-weight:700;color:#e2e8f0;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.total-score{font-size:.75rem;color:#94a3b8;margin-bottom:9px}
.total-score strong{color:#fbbf24;font-size:.95rem}

/* Score bars */
.score-row{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.score-label{font-size:.65rem;color:#94a3b8;width:54px;flex-shrink:0}
.score-bar-bg{flex:1;height:5px;background:#2d3748;border-radius:3px;overflow:hidden}
.score-bar-fill{height:100%;border-radius:3px;transition:width .6s ease}
.score-val{font-size:.7rem;color:#cbd5e1;width:16px;text-align:right;flex-shrink:0}

/* Details */
.reason-details{margin-top:7px;font-size:.76rem}
.reason-details summary{color:#94a3b8;cursor:pointer;user-select:none;padding:2px 0}
.reason-details summary:hover{color:#e2e8f0}
.reason-text{color:#cbd5e1;line-height:1.6;margin-top:5px;padding:7px;background:#0f0f1a;border-radius:5px;border-left:2px solid #a78bfa}
.unx-fit{margin-top:7px;font-size:.76rem;color:#34d399;background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.2);border-radius:5px;padding:5px 9px;line-height:1.5}

/* All chars table */
.all-chars-details summary{font-size:.95rem;font-weight:700;color:#a78bfa;cursor:pointer;padding-bottom:7px;border-bottom:1px solid #2d3748;letter-spacing:.05em;user-select:none}
.all-chars-details summary:hover{color:#c4b5fd}
.all-chars-details[open] .table-wrap{margin-top:14px}
.table-wrap{overflow-x:auto;border-radius:9px;border:1px solid #2d3748}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{background:#1a1a2e;color:#94a3b8;font-weight:600;text-align:left;padding:9px 11px;border-bottom:1px solid #2d3748;white-space:nowrap}
td{padding:7px 11px;border-bottom:1px solid #1e293b;vertical-align:top}
tr:last-child td{border-bottom:none}
tr:hover td{background:#1a1a2e}
.col-num{color:#64748b;width:32px}
.col-name{font-weight:600;color:#e2e8f0}
.col-desc{color:#94a3b8;max-width:240px}
.tag{display:inline-block;font-size:.65rem;padding:2px 7px;border-radius:10px;color:#fff;font-weight:600}

/* Loading / Empty */
.loading{text-align:center;padding:60px;color:#64748b;font-size:.9rem}
.empty{text-align:center;padding:60px;color:#64748b}

/* Footer */
footer{text-align:center;padding:16px;font-size:.75rem;color:#475569;border-top:1px solid #1e293b}

/* Responsive */
@media(max-width:768px){
  .app{flex-direction:column}
  .sidebar{width:100%;border-right:none;border-bottom:1px solid #2d3748;display:flex;flex-wrap:wrap;padding:10px;gap:4px}
  .sidebar-title{display:none}
  .date-btn{width:auto;padding:5px 12px;border-radius:20px;border:1px solid #2d3748;font-size:.75rem}
  .date-btn.active{border-left:1px solid #a78bfa;border-color:#a78bfa}
  .main{padding:16px}
  .card-grid{grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
}
</style>
</head>
<body>

<header class="header">
  <div>
    <h1>UNX Character Tracker</h1>
    <div class="source-tags" id="sourceTags"></div>
  </div>
  <div class="header-meta" id="headerMeta">로딩 중...</div>
</header>

<div class="app">
  <nav class="sidebar" id="sidebar">
    <div class="sidebar-title">날짜 선택</div>
    <div id="dateList"><div class="loading">...</div></div>
  </nav>

  <main class="main" id="main">
    <div class="loading">데이터를 불러오는 중...</div>
  </main>
</div>

<footer id="footer">UNX Character Tracker</footer>

<script>
const SOURCE_COLORS = {
  zeta:'#7c3aed', crack:'#dc2626', rofan:'#f59e0b',
  naver_webtoon:'#059669', ridi:'#2563eb', kakaopage:'#d97706', sample:'#6b7280'
};
const SOURCE_LABELS = {
  zeta:'Zeta AI', crack:'Crack AI', rofan:'Rofan AI',
  naver_webtoon:'네이버 웹툰', ridi:'리디북스', kakaopage:'카카오페이지', sample:'샘플'
};

let allDates = [];
let todayStr = new Date().toISOString().slice(0,10);
let currentDate = null;

function srcColor(s){ return SOURCE_COLORS[s]||'#6b7280'; }
function srcLabel(s){ return SOURCE_LABELS[s]||s; }

function avatarSvg(name){
  const colors=['#7c3aed','#2563eb','#059669','#d97706','#dc2626','#0891b2'];
  const c=colors[Math.abs(name.split('').reduce((a,b)=>a+b.charCodeAt(0),0))%colors.length];
  const ch=(name[0]||'?').toUpperCase();
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:${c}"/><stop offset="100%" style="stop-color:${c}88"/></linearGradient></defs><rect width="200" height="200" fill="url(#g)" rx="12"/><text x="100" y="130" text-anchor="middle" font-size="80" font-family="sans-serif" fill="white" font-weight="bold">${ch}</text></svg>`;
  return 'data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(svg)));
}

function scoreBar(label, val, color){
  const pct=Math.max(0,Math.min(100,(val||0)*10));
  return `<div class="score-row">
    <span class="score-label">${label}</span>
    <div class="score-bar-bg"><div class="score-bar-fill" style="width:${pct}%;background:${color}"></div></div>
    <span class="score-val">${val||0}</span>
  </div>`;
}

function cardHtml(c, rank){
  const sc=srcColor(c.source), sl=srcLabel(c.source);
  const img=c.image_url
    ?`<img src="${c.image_url}" alt="${c.name}" loading="lazy" onerror="this.src='${avatarSvg(c.name)}'">`
    :`<img src="${avatarSvg(c.name)}" alt="${c.name}">`;
  const nameEl=c.url
    ?`<a href="${c.url}" target="_blank" class="char-name">${c.name}</a>`
    :`<span class="char-name">${c.name}</span>`;
  const reasonHtml=c.reason
    ?`<details class="reason-details"><summary>분석 이유</summary><p class="reason-text">${c.reason}</p></details>`:'';
  const unxHtml=c.unx_fit?`<div class="unx-fit">✦ ${c.unx_fit}</div>`:'';
  return `<div class="card">
    <div class="card-image">
      ${img}
      <div class="rank-badge">#${rank}</div>
      <div class="source-badge" style="background:${sc}">${sl}</div>
    </div>
    <div class="card-body">
      ${nameEl}
      <div class="total-score">총점 <strong>${c.total||0}</strong></div>
      <div class="scores">
        ${scoreBar('G3 익숙함',c.g3,'#60a5fa')}
        ${scoreBar('G4 신선함',c.g4,'#a78bfa')}
        ${scoreBar('G5 트랙',c.g5,'#34d399')}
      </div>
      ${reasonHtml}${unxHtml}
    </div>
  </div>`;
}

function allCharsRows(chars){
  return chars.map((c,i)=>{
    const sc=srcColor(c.source), sl=srcLabel(c.source);
    const link=c.url?`<a href="${c.url}" target="_blank">링크</a>`:'-';
    const desc=(c.description||'').slice(0,80)+(c.description&&c.description.length>80?'...':'');
    const tags=(c.tags||[]).slice(0,3).join(', ');
    return `<tr>
      <td class="col-num">${i+1}</td>
      <td><span class="tag" style="background:${sc}">${sl}</span></td>
      <td class="col-name">${c.name}</td>
      <td class="col-desc">${desc}</td>
      <td style="color:#7dd3fc;max-width:140px">${tags}</td>
      <td>${link}</td>
    </tr>`;
  }).join('');
}

function renderData(data){
  const {date,sources,total_collected,top5,all_chars,generated_at}=data;

  // Header
  document.getElementById('sourceTags').innerHTML=(sources||[])
    .map(s=>`<span class="source-tag" style="background:${srcColor(s)}">${srcLabel(s)}</span>`).join('');
  document.getElementById('headerMeta').innerHTML=
    `수집 캐릭터 <strong>${total_collected||0}</strong>개 &nbsp;|&nbsp; Top-${(top5||[]).length} 선정<br>
     생성: ${(generated_at||'').slice(0,19).replace('T',' ')}`;

  const cards=(top5||[]).map((c,i)=>cardHtml(c,i+1)).join('');
  const rows=allCharsRows(all_chars||[]);
  const dateDisp=date||'';

  document.getElementById('main').innerHTML=`
    <div class="section-title">TOP ${(top5||[]).length} 추천 캐릭터</div>
    <div class="date-headline">${dateDisp} 랭킹</div>
    <div class="card-grid">${cards||'<div class="empty">데이터 없음</div>'}</div>
    <details class="all-chars-details">
      <summary>전체 수집 캐릭터 목록 (${(all_chars||[]).length}개)</summary>
      <div class="table-wrap"><table>
        <thead><tr><th>#</th><th>소스</th><th>이름</th><th>설명</th><th>태그</th><th>링크</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </details>`;

  document.getElementById('footer').textContent=`UNX Character Tracker  ·  ${dateDisp}`;
}

async function loadDate(date){
  currentDate=date;
  // Sidebar 활성화
  document.querySelectorAll('.date-btn').forEach(b=>{
    b.classList.toggle('active', b.dataset.date===date);
  });
  document.getElementById('main').innerHTML='<div class="loading">불러오는 중...</div>';
  try{
    const res=await fetch(`./data/${date}.json`);
    if(!res.ok) throw new Error(res.status);
    const data=await res.json();
    renderData(data);
    history.replaceState(null,'',`?date=${date}`);
  }catch(e){
    document.getElementById('main').innerHTML=`<div class="empty">데이터를 불러올 수 없습니다 (${date})</div>`;
  }
}

async function init(){
  try{
    const res=await fetch('./data/index.json');
    if(!res.ok) throw new Error('index.json not found');
    const idx=await res.json();
    allDates=idx.dates||[];
    const latest=idx.latest||allDates[0];

    // Sidebar 날짜 목록
    const list=document.getElementById('dateList');
    if(allDates.length===0){
      list.innerHTML='<div class="loading">날짜 없음</div>';
    } else {
      list.innerHTML=allDates.map(d=>{
        const isToday=d===todayStr;
        return `<button class="date-btn${isToday?' today':''}" data-date="${d}" onclick="loadDate('${d}')">${d}</button>`;
      }).join('');
    }

    // URL 파라미터 우선
    const params=new URLSearchParams(location.search);
    const dateParam=params.get('date');
    const target=(dateParam&&allDates.includes(dateParam))?dateParam:latest;
    if(target) await loadDate(target);
    else document.getElementById('main').innerHTML='<div class="empty">수집된 데이터가 없습니다.<br>python3 run_pipeline.py 를 먼저 실행하세요.</div>';

  }catch(e){
    document.getElementById('dateList').innerHTML='<div class="loading">인덱스 없음</div>';
    // index.json이 없으면 최신 dashboard embedded 데이터 표시
    document.getElementById('main').innerHTML=
      '<div class="empty">data/index.json이 없습니다.<br>python3 run_pipeline.py 를 실행하세요.</div>';
  }
}

init();
</script>
</body>
</html>"""


def generate_html(top_k: list, all_chars: list, cfg, run_meta: dict) -> str:
    """SPA HTML 파일을 output/dashboard.html 에 저장"""
    output_path = Path(cfg.output_dir) / "dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(SPA_HTML, encoding="utf-8")
    logger.info(f"[Reporter] Dashboard saved: {output_path} ({output_path.stat().st_size:,} bytes)")
    return SPA_HTML
