"""
HTML 대시보드 생성기
output/dashboard.html 로 저장
"""
import base64
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SOURCE_COLORS = {
    "naver_webtoon": "#059669",
    "ridi":          "#2563eb",
    "kakaopage":     "#d97706",
    "zeta":          "#7c3aed",
    "crack":         "#dc2626",
    "sample":        "#6b7280",
}

SOURCE_LABELS = {
    "naver_webtoon": "네이버 웹툰",
    "ridi":          "리디북스",
    "kakaopage":     "카카오페이지",
    "zeta":          "Zeta AI",
    "crack":         "Crack AI",
    "sample":        "샘플",
}


def make_avatar_svg(name: str) -> str:
    initial = name[0].upper() if name else "?"
    colors = ["#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626", "#0891b2"]
    color = colors[hash(name) % len(colors)]
    bg2 = color + "88"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{color}"/>
      <stop offset="100%" style="stop-color:{bg2}"/>
    </linearGradient>
  </defs>
  <rect width="200" height="200" fill="url(#g)" rx="12"/>
  <text x="100" y="130" text-anchor="middle" font-size="80" font-family="sans-serif" fill="white" font-weight="bold">{initial}</text>
</svg>'''
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _score_bar(label: str, score: int, color: str) -> str:
    pct = max(0, min(100, score * 10))
    return f'''
        <div class="score-row">
          <span class="score-label">{label}</span>
          <div class="score-bar-bg">
            <div class="score-bar-fill" style="width:{pct}%; background:{color};"></div>
          </div>
          <span class="score-val">{score}</span>
        </div>'''


def _card_html(rank: int, sc, show_rank: bool = True) -> str:
    char = sc.character
    source_color = SOURCE_COLORS.get(char.source, "#6b7280")
    source_label = SOURCE_LABELS.get(char.source, char.source)

    if char.image_url:
        img_tag = f'<img src="{char.image_url}" alt="{char.name}" loading="lazy" onerror="this.src=\'\'"/>'
    else:
        avatar = make_avatar_svg(char.name)
        img_tag = f'<img src="{avatar}" alt="{char.name}"/>'

    rank_badge = f'<div class="rank-badge">#{rank}</div>' if show_rank else ""
    source_badge = f'<div class="source-badge" style="background:{source_color};">{source_label}</div>'

    bars = (
        _score_bar("G3 익숙함", sc.g3, "#60a5fa") +
        _score_bar("G4 신선함", sc.g4, "#a78bfa") +
        _score_bar("G5 트랙", sc.g5, "#34d399")
    )

    reason_html = ""
    if sc.reason:
        reason_html = f'''
        <details class="reason-details">
          <summary>분석 이유</summary>
          <p class="reason-text">{sc.reason}</p>
        </details>'''

    unx_html = ""
    if sc.unx_fit:
        unx_html = f'<div class="unx-fit">✦ {sc.unx_fit}</div>'

    char_url = char.url or ""
    name_html = f'<a href="{char_url}" target="_blank" class="char-name">{char.name}</a>' if char_url else f'<span class="char-name">{char.name}</span>'

    total_html = f'<div class="total-score">총점 <strong>{sc.total}</strong></div>'

    return f'''
    <div class="card">
      <div class="card-image">
        {img_tag}
        {rank_badge}
        {source_badge}
      </div>
      <div class="card-body">
        {name_html}
        {total_html}
        <div class="scores">{bars}
        </div>
        {reason_html}
        {unx_html}
      </div>
    </div>'''


def _all_chars_rows(all_chars) -> str:
    rows = []
    for i, char in enumerate(all_chars, 1):
        source_color = SOURCE_COLORS.get(char.source, "#6b7280")
        source_label = SOURCE_LABELS.get(char.source, char.source)
        url_cell = f'<a href="{char.url}" target="_blank">링크</a>' if char.url else "-"
        rows.append(f'''
          <tr>
            <td class="col-num">{i}</td>
            <td><span class="tag" style="background:{source_color};">{source_label}</span></td>
            <td class="col-name">{char.name}</td>
            <td class="col-desc">{char.description[:80]}{"..." if len(char.description) > 80 else ""}</td>
            <td class="col-tags">{", ".join(str(t) for t in char.tags[:4])}</td>
            <td>{url_cell}</td>
          </tr>''')
    return "\n".join(rows)


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', 'Noto Sans KR', sans-serif;
  background: #0f0f1a;
  color: #e2e8f0;
  min-height: 100vh;
}
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Header */
.header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-bottom: 1px solid #2d3748;
  padding: 24px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.header h1 {
  font-size: 1.6rem;
  font-weight: 700;
  background: linear-gradient(90deg, #a78bfa, #60a5fa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.header-meta { font-size: 0.82rem; color: #94a3b8; text-align: right; line-height: 1.6; }
.source-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.source-tag { font-size: 0.72rem; padding: 2px 8px; border-radius: 12px; font-weight: 600; }

/* Section */
.section { padding: 32px; max-width: 1400px; margin: 0 auto; }
.section-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: #a78bfa;
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid #2d3748;
  letter-spacing: 0.05em;
}

/* Card grid */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

/* Card */
.card {
  background: #1a1a2e;
  border: 1px solid #2d3748;
  border-radius: 14px;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}
.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(167, 139, 250, 0.15);
}
.card-image {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  background: #0f0f1a;
  overflow: hidden;
}
.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.rank-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  background: rgba(0,0,0,0.75);
  color: #fbbf24;
  font-size: 0.9rem;
  font-weight: 800;
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid #fbbf24;
  backdrop-filter: blur(4px);
}
.source-badge {
  position: absolute;
  bottom: 10px;
  right: 10px;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 10px;
  color: #fff;
  backdrop-filter: blur(4px);
}
.card-body { padding: 14px 16px 16px; }
.char-name {
  display: block;
  font-size: 1rem;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.total-score { font-size: 0.8rem; color: #94a3b8; margin-bottom: 10px; }
.total-score strong { color: #fbbf24; font-size: 1rem; }

/* Score bars */
.scores { margin-bottom: 10px; }
.score-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
}
.score-label { font-size: 0.68rem; color: #94a3b8; width: 56px; flex-shrink: 0; }
.score-bar-bg {
  flex: 1;
  height: 6px;
  background: #2d3748;
  border-radius: 3px;
  overflow: hidden;
}
.score-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.score-val { font-size: 0.72rem; color: #cbd5e1; width: 16px; text-align: right; flex-shrink: 0; }

/* Reason details */
.reason-details {
  margin-top: 8px;
  font-size: 0.78rem;
}
.reason-details summary {
  color: #94a3b8;
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}
.reason-details summary:hover { color: #e2e8f0; }
.reason-text {
  color: #cbd5e1;
  line-height: 1.6;
  margin-top: 6px;
  padding: 8px;
  background: #0f0f1a;
  border-radius: 6px;
  border-left: 2px solid #a78bfa;
}

/* UNX fit */
.unx-fit {
  margin-top: 8px;
  font-size: 0.78rem;
  color: #34d399;
  background: rgba(52, 211, 153, 0.08);
  border: 1px solid rgba(52, 211, 153, 0.2);
  border-radius: 6px;
  padding: 6px 10px;
  line-height: 1.5;
}

/* All chars table */
.table-wrap {
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid #2d3748;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
th {
  background: #1a1a2e;
  color: #94a3b8;
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #2d3748;
  white-space: nowrap;
}
td {
  padding: 8px 12px;
  border-bottom: 1px solid #1e293b;
  vertical-align: top;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #1a1a2e; }
.col-num { color: #64748b; width: 36px; }
.col-name { font-weight: 600; color: #e2e8f0; }
.col-desc { color: #94a3b8; max-width: 260px; }
.col-tags { color: #7dd3fc; max-width: 160px; }
.tag {
  display: inline-block;
  font-size: 0.68rem;
  padding: 2px 7px;
  border-radius: 10px;
  color: #fff;
  font-weight: 600;
}

/* Footer */
footer {
  text-align: center;
  padding: 20px;
  font-size: 0.78rem;
  color: #475569;
  border-top: 1px solid #1e293b;
  margin-top: 16px;
}

/* All chars details */
.all-chars-details summary {
  font-size: 1.1rem;
  font-weight: 700;
  color: #a78bfa;
  cursor: pointer;
  padding-bottom: 8px;
  border-bottom: 1px solid #2d3748;
  letter-spacing: 0.05em;
  user-select: none;
}
.all-chars-details summary:hover { color: #c4b5fd; }
.all-chars-details[open] .table-wrap { margin-top: 16px; }

@media (max-width: 600px) {
  .section { padding: 16px; }
  .card-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
  .header { padding: 16px; }
}
@media (max-width: 400px) {
  .card-grid { grid-template-columns: 1fr; }
}
"""


def generate_html(top_k: list, all_chars: list, cfg, run_meta: dict) -> str:
    """
    top_k: list[ScoredCharacter]
    all_chars: list[Character]
    cfg: TrackerConfig
    run_meta: dict (generated_at, sources, etc.)
    """
    generated_at = run_meta.get("generated_at", datetime.now().isoformat())
    sources_used = run_meta.get("sources_used", [])

    # Source tags in header
    source_tags_html = ""
    for src in sources_used:
        color = SOURCE_COLORS.get(src, "#6b7280")
        label = SOURCE_LABELS.get(src, src)
        source_tags_html += f'<span class="source-tag" style="background:{color};">{label}</span>'

    # Top cards
    cards_html = ""
    for rank, sc in enumerate(top_k, 1):
        cards_html += _card_html(rank, sc, show_rank=True)

    # All chars table
    all_rows_html = _all_chars_rows(all_chars)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>UNX Character Tracker Dashboard</title>
  <style>
{CSS}
  </style>
</head>
<body>

<header class="header">
  <div>
    <h1>UNX Character Tracker</h1>
    <div class="source-tags">{source_tags_html}</div>
  </div>
  <div class="header-meta">
    <div>수집 캐릭터 <strong>{len(all_chars)}</strong>개 &nbsp;|&nbsp; Top-{len(top_k)} 선정</div>
    <div>생성: {generated_at[:19].replace("T", " ")}</div>
  </div>
</header>

<main>
  <section class="section">
    <div class="section-title">TOP {len(top_k)} 추천 캐릭터</div>
    <div class="card-grid">
      {cards_html}
    </div>
  </section>

  <section class="section">
    <details class="all-chars-details">
      <summary>전체 수집 캐릭터 목록 ({len(all_chars)}개)</summary>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>소스</th>
              <th>이름</th>
              <th>설명</th>
              <th>태그</th>
              <th>링크</th>
            </tr>
          </thead>
          <tbody>
            {all_rows_html}
          </tbody>
        </table>
      </div>
    </details>
  </section>
</main>

<footer>
  UNX Character Tracker &nbsp;·&nbsp; 생성: {generated_at[:19].replace("T", " ")}
</footer>

</body>
</html>"""

    # Save to file
    output_path = Path(cfg.output_dir) / "dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"[Reporter] Dashboard saved: {output_path} ({output_path.stat().st_size:,} bytes)")
    return html
