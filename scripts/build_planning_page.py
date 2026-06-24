from __future__ import annotations

import html
import re
import shutil
import struct
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOCX = Path("/Users/dmm/Desktop/数智化产品规划0623.docx")
ASSET_DIR = ROOT / "assets" / "planning"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def w_attr(name: str) -> str:
    return f"{{{NS['w']}}}{name}"


def r_attr(name: str) -> str:
    return f"{{{NS['r']}}}{name}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def clean_text(value: str) -> str:
    # Normalize invisible Word control whitespace, but keep the original words,
    # punctuation, Chinese text, numbers, and explicit line breaks.
    return value.replace("\u00a0", " ").strip()


def text_to_html(value: str) -> str:
    return esc(value).replace("\n", "<br />")


def para_text(p: ET.Element) -> str:
    parts: list[str] = []
    for node in p.iter():
        tag = local_name(node.tag)
        if tag == "t":
            parts.append(node.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag == "br":
            parts.append("\n")
    return "".join(parts)


def para_style(p: ET.Element, style_names: dict[str, str]) -> str | None:
    pstyle = p.find("w:pPr/w:pStyle", NS)
    if pstyle is None:
        return None
    style_id = pstyle.get(w_attr("val"))
    if not style_id:
        return None
    return style_names.get(style_id, style_id)


def para_num_level(p: ET.Element) -> int | None:
    ilvl = p.find("w:pPr/w:numPr/w:ilvl", NS)
    if ilvl is None:
        return None
    try:
        return int(ilvl.get(w_attr("val")) or "0")
    except ValueError:
        return None


def load_style_names(zip_file: ZipFile) -> dict[str, str]:
    root = ET.fromstring(zip_file.read("word/styles.xml"))
    style_names: dict[str, str] = {}
    for style in root.findall("w:style", NS):
        style_id = style.get(w_attr("styleId"))
        name = style.find("w:name", NS)
        if style_id and name is not None:
            style_names[style_id] = name.get(w_attr("val")) or style_id
    return style_names


def load_rels(zip_file: ZipFile) -> dict[str, str]:
    root = ET.fromstring(zip_file.read("word/_rels/document.xml.rels"))
    return {rel.get("Id"): rel.get("Target") for rel in root if rel.get("Id") and rel.get("Target")}


def image_targets(p: ET.Element, rels: dict[str, str]) -> list[str]:
    targets: list[str] = []
    for blip in p.findall(".//a:blip", NS):
        rel_id = blip.get(r_attr("embed")) or blip.get(r_attr("link"))
        target = rels.get(rel_id or "")
        if target:
            targets.append(target)
    return targets


def cell_text(tc: ET.Element) -> str:
    values = [clean_text(para_text(p)) for p in tc.findall("w:p", NS)]
    return "\n".join(value for value in values if value)


def table_rows(tbl: ET.Element) -> list[list[dict[str, object]]]:
    rows: list[list[dict[str, object]]] = []
    for tr in tbl.findall("w:tr", NS):
        row: list[dict[str, object]] = []
        for tc in tr.findall("w:tc", NS):
            grid_span = tc.find("w:tcPr/w:gridSpan", NS)
            colspan = 1
            if grid_span is not None:
                try:
                    colspan = int(grid_span.get(w_attr("val")) or "1")
                except ValueError:
                    colspan = 1
            row.append({"text": cell_text(tc), "colspan": colspan})
        rows.append(row)
    return rows


def extract_blocks() -> list[dict[str, object]]:
    with ZipFile(SOURCE_DOCX) as zip_file:
        style_names = load_style_names(zip_file)
        rels = load_rels(zip_file)
        root = ET.fromstring(zip_file.read("word/document.xml"))

    blocks: list[dict[str, object]] = []
    for child in root.find("w:body", NS):
        name = local_name(child.tag)
        if name == "p":
            text = clean_text(para_text(child))
            images = image_targets(child, rels)
            if text or images:
                blocks.append(
                    {
                        "type": "paragraph",
                        "style": para_style(child, style_names),
                        "text": text,
                        "num_level": para_num_level(child),
                        "images": images,
                    }
                )
        elif name == "tbl":
            blocks.append({"type": "table", "rows": table_rows(child)})
    return blocks


def copy_assets() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(SOURCE_DOCX) as zip_file:
        for member in zip_file.namelist():
            if member.startswith("word/media/"):
                target = ASSET_DIR / Path(member).name
                with zip_file.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def heading_level(style: str | None) -> int | None:
    if not style:
        return None
    normalized = style.lower().strip()
    if normalized == "maintitle":
        return 0
    match = re.fullmatch(r"heading\s+([1-4])", normalized)
    if match:
        return int(match.group(1))
    return None


def image_path(target: str) -> str:
    return f"assets/planning/{Path(target).name}"


def png_size(target: str) -> tuple[int, int] | None:
    path = ASSET_DIR / Path(target).name
    if not path.exists():
        return None
    with path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def split_layer_label(text: str) -> str:
    cleaned = text.replace("📌", "").strip()
    match = re.match(r"([^：:（(]+)", cleaned)
    return match.group(1).strip() if match else cleaned


def make_ids(blocks: Iterable[dict[str, object]]) -> tuple[dict[int, str], list[dict[str, object]]]:
    heading_counts: defaultdict[int, int] = defaultdict(int)
    layer = chapter = topic = subtopic = 0
    block_ids: dict[int, str] = {}
    nav: list[dict[str, object]] = []
    current_layer: dict[str, object] | None = None

    for idx, block in enumerate(blocks):
        if block.get("type") != "paragraph":
            continue
        level = heading_level(block.get("style"))
        text = str(block.get("text") or "")
        if level == 0:
            block_ids[idx] = "top"
        elif level == 1:
            layer += 1
            chapter = topic = subtopic = 0
            block_id = f"layer-{layer}"
            block_ids[idx] = block_id
            current_layer = {
                "id": block_id,
                "label": split_layer_label(text),
                "title": text,
                "children": [],
            }
            nav.append(current_layer)
        elif level == 2:
            chapter += 1
            topic = subtopic = 0
            block_id = f"layer-{layer}-chapter-{chapter}"
            block_ids[idx] = block_id
            if current_layer is not None:
                current_layer["children"].append({"id": block_id, "label": text})
        elif level == 3:
            topic += 1
            subtopic = 0
            block_ids[idx] = f"layer-{layer}-chapter-{chapter}-topic-{topic}"
        elif level == 4:
            subtopic += 1
            block_ids[idx] = f"layer-{layer}-chapter-{chapter}-topic-{topic}-sub-{subtopic}"
        elif text:
            heading_counts[level or 9] += 1
    return block_ids, nav


def collect_title(blocks: list[dict[str, object]]) -> str:
    for block in blocks:
        if block.get("type") == "paragraph" and heading_level(block.get("style")) == 0:
            return str(block.get("text") or "数智化产品规划")
    return "数智化产品规划"


def table_dimensions(rows: list[list[dict[str, object]]]) -> tuple[int, int]:
    width = 0
    for row in rows:
        width = max(width, sum(int(cell.get("colspan") or 1) for cell in row))
    return len(rows), width


def table_summary_text(rows: list[list[dict[str, object]]]) -> str:
    if not rows:
        return "表格"
    cells = [clean_text(str(cell.get("text") or "")) for cell in rows[0]]
    label = " · ".join(cell for cell in cells if cell)
    return label or "表格"


def is_feature_list_context(heading_text: str) -> bool:
    return "功能清单" in clean_text(heading_text)


def render_table(rows: list[list[dict[str, object]]], table_index: int, *, force_open: bool = False) -> str:
    row_count, col_count = table_dimensions(rows)
    open_attr = " open" if force_open or row_count <= 12 else ""
    size_class = " table-large" if row_count > 12 else ""
    wide_class = " table-wide" if col_count >= 6 else ""
    summary_text = table_summary_text(rows)
    html_parts = [
        f'<details class="doc-table{size_class}{wide_class} searchable-block" data-table{open_attr}>',
        f"<summary>{esc(summary_text)}</summary>",
        '<div class="table-tools">',
        '<label class="table-filter-label">表内搜索</label>',
        '<input class="table-filter" type="search" autocomplete="off" />',
        "</div>",
        '<div class="table-scroll">',
        "<table>",
    ]
    for row_index, row in enumerate(rows):
        section_row = row_index > 0 and len(row) == 1 and int(row[0].get("colspan") or 1) >= max(2, col_count)
        if row_index == 0:
            html_parts.append("<thead><tr>")
        elif row_index == 1:
            html_parts.append("<tbody><tr>")
        else:
            row_class = ' class="table-section-row"' if section_row else ""
            html_parts.append(f"<tr{row_class}>")
        cell_tag = "th" if row_index == 0 or section_row else "td"
        for cell in row:
            colspan = int(cell.get("colspan") or 1)
            colspan_attr = f' colspan="{colspan}"' if colspan > 1 else ""
            text = text_to_html(str(cell.get("text") or ""))
            html_parts.append(f"<{cell_tag}{colspan_attr}>{text}</{cell_tag}>")
        if row_index == 0:
            html_parts.append("</tr></thead>")
        else:
            html_parts.append("</tr>")
    if rows:
        html_parts.append("</tbody>")
    html_parts.extend(["</table>", "</div>", "</details>"])
    return "\n".join(html_parts)


def render_image(target: str, image_index: int) -> str:
    path = image_path(target)
    size = png_size(target)
    dimension_attrs = f' width="{size[0]}" height="{size[1]}"' if size else ""
    return (
        f'<figure class="doc-figure searchable-block">'
        f'<button type="button" class="figure-open" data-full-image="{esc(path)}" aria-label="放大图片 {image_index}">'
        f'<img src="{esc(path)}" alt="文档图片 {image_index}" loading="lazy"{dimension_attrs} />'
        "</button>"
        "</figure>"
    )


def render_paragraph(text: str, num_level: int | None) -> str:
    if num_level is None:
        return f'<p class="doc-paragraph searchable-block">{text_to_html(text)}</p>'
    safe_level = max(0, min(num_level, 3))
    return (
        f'<p class="doc-list-line list-level-{safe_level} searchable-block">'
        f'<span class="list-marker" aria-hidden="true"></span>'
        f'<span>{text_to_html(text)}</span>'
        "</p>"
    )


def render_nav(nav: list[dict[str, object]]) -> str:
    groups: list[str] = []
    for group in nav:
        children = "".join(
            f'<a href="#{esc(str(child["id"]))}" class="toc-child">{esc(str(child["label"]))}</a>'
            for child in group["children"]
        )
        groups.append(
            f'<section class="toc-group" data-layer-link="{esc(str(group["id"]))}">'
            f'<a href="#{esc(str(group["id"]))}" class="toc-layer">{esc(str(group["title"]))}</a>'
            f'<div class="toc-children">{children}</div>'
            "</section>"
        )
    return "\n".join(groups)


def render_layer_tabs(nav: list[dict[str, object]]) -> str:
    return "\n".join(
        f'<a href="#{esc(str(group["id"]))}" class="layer-tab" data-layer="{esc(str(group["id"]))}">{esc(str(group["label"]))}</a>'
        for group in nav
    )


def render_quick_map(nav: list[dict[str, object]]) -> str:
    cards: list[str] = []
    for index, group in enumerate(nav, start=1):
        cards.append(
            f'<a class="quick-card quick-card--layer-{index}" href="#{esc(str(group["id"]))}">'
            f'<span class="quick-number">{index:02d}</span>'
            f'<span class="quick-title">{esc(str(group["title"]))}</span>'
            f'<span class="quick-meta">{len(group["children"])} 个章节</span>'
            "</a>"
        )
    return "\n".join(cards)


def render_layer_journey(nav: list[dict[str, object]]) -> str:
    steps: list[str] = []
    for index, group in enumerate(nav, start=1):
        steps.append(
            f'<a class="journey-step" href="#{esc(str(group["id"]))}">'
            f'<span class="journey-num">{index:02d}</span>'
            f'<span class="journey-label">{esc(str(group["label"]))}</span>'
            f'<span class="journey-meta">{len(group["children"])} 章</span>'
            "</a>"
        )
    return "\n".join(steps)


def render_document(blocks: list[dict[str, object]], block_ids: dict[int, str]) -> str:
    parts: list[str] = []
    layer_open = False
    chapter_open = False
    layer_intro_open = False
    chapters_flow_open = False
    layer_index = 0
    chapter_in_layer = 0
    table_index = 0
    image_index = 0
    last_heading_text = ""

    def close_layer_intro() -> None:
        nonlocal layer_intro_open
        if layer_intro_open:
            parts.append("</div>")
            layer_intro_open = False

    def open_chapters_flow() -> None:
        nonlocal chapters_flow_open
        if layer_open and not chapters_flow_open:
            parts.append('<div class="chapters-flow">')
            chapters_flow_open = True

    def close_chapters_flow() -> None:
        nonlocal chapters_flow_open
        if chapters_flow_open:
            parts.append("</div>")
            chapters_flow_open = False

    def close_chapter() -> None:
        nonlocal chapter_open
        if chapter_open:
            parts.append("</div></article>")
            chapter_open = False

    def close_layer() -> None:
        nonlocal layer_open, chapter_in_layer
        close_chapter()
        close_layer_intro()
        close_chapters_flow()
        if layer_open:
            parts.append("</div></div></section>")
            layer_open = False
            chapter_in_layer = 0

    for idx, block in enumerate(blocks):
        block_type = block.get("type")
        if block_type == "paragraph":
            text = str(block.get("text") or "")
            style = block.get("style")
            level = heading_level(style)
            if level == 0:
                continue
            if level == 1:
                close_layer()
                block_id = block_ids[idx]
                layer_index += 1
                chapter_in_layer = 0
                parts.append(
                    f'<section class="layer-section layer-section--{layer_index} search-scope" id="{esc(block_id)}" data-layer-section="{esc(block_id)}">'
                    '<div class="layer-shell">'
                    f'<aside class="layer-rail" aria-hidden="true"><span class="layer-rail-num">{layer_index:02d}</span></aside>'
                    '<div class="layer-inner">'
                    '<header class="layer-header">'
                    f'<span class="layer-kicker">{esc(split_layer_label(text))}</span>'
                    f"<h2>{esc(text)}</h2>"
                    "</header>"
                    '<div class="layer-intro">'
                )
                layer_open = True
                layer_intro_open = True
            elif level == 2:
                if not layer_open:
                    parts.append(
                        '<section class="layer-section layer-section--0 search-scope" id="document">'
                        '<div class="layer-shell">'
                        '<aside class="layer-rail" aria-hidden="true"><span class="layer-rail-num">00</span></aside>'
                        '<div class="layer-inner">'
                    )
                    layer_open = True
                close_chapter()
                close_layer_intro()
                open_chapters_flow()
                chapter_in_layer += 1
                block_id = block_ids[idx]
                parts.append(
                    f'<article class="chapter-panel search-scope" id="{esc(block_id)}" data-chapter-index="{chapter_in_layer}">'
                    '<header class="chapter-header">'
                    f'<span class="chapter-index" aria-hidden="true">{chapter_in_layer:02d}</span>'
                    f"<h3>{esc(text)}</h3>"
                    "</header>"
                    '<div class="chapter-body">'
                )
                chapter_open = True
            elif level == 3:
                close_layer_intro()
                last_heading_text = text
                block_id = block_ids[idx]
                parts.append(f'<h4 class="topic-heading searchable-block" id="{esc(block_id)}">{esc(text)}</h4>')
            elif level == 4:
                close_layer_intro()
                last_heading_text = text
                block_id = block_ids[idx]
                parts.append(f'<h5 class="subtopic-heading searchable-block" id="{esc(block_id)}">{esc(text)}</h5>')
            else:
                if text:
                    parts.append(render_paragraph(text, block.get("num_level")))
            for target in block.get("images") or []:
                image_index += 1
                parts.append(render_image(str(target), image_index))
        elif block_type == "table":
            table_index += 1
            close_layer_intro()
            force_open = is_feature_list_context(last_heading_text)
            parts.append(render_table(block.get("rows") or [], table_index, force_open=force_open))
    close_layer()
    return "\n".join(parts)


def render_html(blocks: list[dict[str, object]]) -> str:
    block_ids, nav = make_ids(blocks)
    title = collect_title(blocks)
    table_total = sum(1 for block in blocks if block.get("type") == "table")
    image_total = sum(len(block.get("images") or []) for block in blocks if block.get("type") == "paragraph")
    heading_total = sum(1 for block in blocks if block.get("type") == "paragraph" and heading_level(block.get("style")) in {1, 2, 3, 4})
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>合一 · {esc(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="planning.css?v=enterprise-v10" />
  <link rel="stylesheet" href="planning-premium.css?v=20260623-premium8" />
  <script>
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    window.scrollTo(0, 0);
  </script>
</head>
<body class="planning-page">
  <div class="read-progress" id="readProgress" aria-hidden="true"></div>

  <header class="topbar" id="topbar">
    <a href="index.html" class="brand-link">
      <span class="brand-mark">合</span>
      <span class="brand-text">{esc(title)}</span>
    </a>
    <nav class="layer-tabs" aria-label="层级导航">
      {render_layer_tabs(nav)}
    </nav>
    <div class="section-chip" id="sectionChip" aria-live="polite">
      <span>当前章节</span>
      <strong>{esc(title)}</strong>
    </div>
    <div class="topbar-actions">
      <button type="button" class="icon-button" id="focusToggle" aria-pressed="false">专注</button>
      <button type="button" class="icon-button" id="tocToggle" aria-label="打开目录">目录</button>
    </div>
  </header>

  <aside class="toc-drawer" id="tocDrawer" aria-label="页面目录">
    <div class="toc-head">
      <span>目录</span>
      <button type="button" class="toc-close" id="tocClose" aria-label="关闭目录">×</button>
    </div>
    <nav class="toc-list" id="tocList">
      {render_nav(nav)}
    </nav>
  </aside>
  <div class="toc-overlay" id="tocOverlay"></div>

  <main>
    <section class="hero" id="top">
      <div class="hero-stage hero-stage--compact">
        <div class="hero-main">
          <span class="hero-label">产品规划</span>
          <h1>{esc(title)}</h1>
        </div>
      </div>
      <nav class="quick-map quick-map--bento" aria-label="层级快速入口">
        {render_quick_map(nav)}
      </nav>
    </section>

    <div class="content-shell">
      <aside class="desktop-toc" aria-label="桌面目录">
        <nav>{render_nav(nav)}</nav>
      </aside>
      <div class="document-flow" id="documentFlow">
        {render_document(blocks, block_ids)}
      </div>
    </div>
  </main>

  <button type="button" class="back-top" id="backTop" aria-label="回到顶部">↑</button>

  <div class="image-viewer" id="imageViewer" aria-hidden="true">
    <button type="button" class="image-viewer-close" id="imageViewerClose" aria-label="关闭图片预览">×</button>
    <img id="imageViewerImg" alt="" />
  </div>

  <script src="app.js?v=enterprise-v10"></script>
</body>
</html>
"""


CSS = r"""
:root {
  --bg: #f6f7f2;
  --surface: #ffffff;
  --surface-soft: #fdfbf5;
  --ink: #20231f;
  --muted: #667067;
  --subtle: #92998d;
  --line: #dfe3d8;
  --line-strong: #cbd2c3;
  --green: #2f6f58;
  --teal: #0f766e;
  --gold: #a86816;
  --coral: #b8543b;
  --blue: #345d82;
  --radius: 8px;
  --shadow: 0 12px 34px rgba(35, 42, 31, 0.08);
  --nav-h: 64px;
  --font-scale: 1;
  --font: "Inter", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
  scroll-padding-top: calc(var(--nav-h) + 18px);
}

body.planning-page {
  margin: 0;
  font-family: var(--font);
  color: var(--ink);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.8), rgba(255,255,255,0) 260px),
    var(--bg);
  font-size: calc(16px * var(--font-scale));
  line-height: 1.72;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

a {
  color: inherit;
}

button,
input {
  font: inherit;
}

.read-progress {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 200;
  height: 3px;
  width: 0;
  background: linear-gradient(90deg, var(--green), var(--gold), var(--coral));
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  min-height: var(--nav-h);
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px clamp(16px, 3vw, 34px);
  background: rgba(246, 247, 242, 0.92);
  border-bottom: 1px solid rgba(203, 210, 195, 0.78);
  backdrop-filter: blur(18px);
}

.topbar.is-scrolled {
  box-shadow: 0 10px 30px rgba(35, 42, 31, 0.08);
}

.brand-link {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  text-decoration: none;
  font-weight: 800;
  color: var(--ink);
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius);
  background: var(--ink);
  color: white;
  flex: 0 0 auto;
}

.brand-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layer-tabs {
  display: flex;
  justify-content: center;
  gap: 6px;
  flex: 1;
  overflow-x: auto;
  scrollbar-width: none;
}

.layer-tabs::-webkit-scrollbar {
  display: none;
}

.layer-tab {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 999px;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.86rem;
  font-weight: 700;
  white-space: nowrap;
}

.layer-tab:hover,
.layer-tab.is-active {
  background: var(--ink);
  color: white;
}

.topbar-actions {
  display: flex;
  gap: 8px;
}

.icon-button,
.tool-button,
.toc-close,
.image-viewer-close {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--ink);
  min-height: 36px;
  padding: 7px 12px;
  cursor: pointer;
  font-weight: 700;
}

.icon-button:hover,
.tool-button:hover,
.toc-close:hover {
  border-color: var(--line-strong);
  background: var(--surface-soft);
}

.hero {
  padding: 48px clamp(18px, 4vw, 56px) 26px;
}

.hero-inner {
  max-width: 1240px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 24px;
  align-items: end;
}

.hero-copy {
  min-width: 0;
}

.hero-label,
.layer-kicker {
  display: inline-flex;
  color: var(--green);
  font-size: 0.82rem;
  font-weight: 900;
  letter-spacing: 0;
  margin-bottom: 10px;
}

.hero h1 {
  margin: 0;
  max-width: 780px;
  font-size: clamp(2.2rem, 6vw, 5.4rem);
  line-height: 1.05;
  letter-spacing: 0;
}

.hero-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

.hero-stats span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 5px 11px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  color: var(--muted);
  font-size: 0.9rem;
}

.hero-stats strong {
  color: var(--ink);
}

.reader-tools {
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px;
  box-shadow: var(--shadow);
}

.search-panel {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
}

.search-panel label,
.table-filter-label {
  color: var(--muted);
  font-size: 0.88rem;
  font-weight: 800;
}

.search-panel input,
.table-filter {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 7px 10px;
  background: var(--surface);
  color: var(--ink);
  outline: none;
}

.search-panel input:focus,
.table-filter:focus {
  border-color: var(--green);
  box-shadow: 0 0 0 3px rgba(47, 111, 88, 0.13);
}

#searchCount {
  color: var(--subtle);
  font-size: 0.84rem;
  white-space: nowrap;
}

.tool-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.tool-button {
  min-height: 34px;
  padding: 6px 10px;
  color: var(--muted);
  font-size: 0.86rem;
}

.quick-map {
  max-width: 1240px;
  margin: 28px auto 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.quick-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  min-height: 96px;
  padding: 15px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  text-decoration: none;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.quick-card:hover {
  transform: translateY(-2px);
  border-color: var(--line-strong);
  box-shadow: var(--shadow);
}

.quick-number {
  grid-row: span 2;
  color: var(--gold);
  font-weight: 900;
}

.quick-title {
  font-weight: 850;
  line-height: 1.35;
}

.quick-meta {
  color: var(--subtle);
  font-size: 0.84rem;
}

.content-shell {
  max-width: 1460px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 286px minmax(0, 1fr);
  gap: 28px;
  padding: 18px clamp(18px, 4vw, 56px) 80px;
}

.desktop-toc {
  position: sticky;
  top: calc(var(--nav-h) + 18px);
  height: calc(100vh - var(--nav-h) - 36px);
  overflow: auto;
  align-self: start;
  padding-right: 6px;
}

.toc-list,
.desktop-toc nav {
  display: grid;
  gap: 10px;
}

.toc-group {
  border-left: 3px solid transparent;
  padding-left: 10px;
}

.toc-group.is-active {
  border-left-color: var(--green);
}

.toc-layer {
  display: block;
  text-decoration: none;
  font-weight: 900;
  line-height: 1.35;
  margin-bottom: 8px;
}

.toc-child {
  display: block;
  text-decoration: none;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.35;
  padding: 6px 0;
}

.toc-child:hover,
.toc-child.is-active {
  color: var(--ink);
  font-weight: 800;
}

.document-flow {
  min-width: 0;
}

.layer-section {
  margin-bottom: 42px;
  border-top: 1px solid var(--line-strong);
}

.layer-inner {
  padding-top: 34px;
}

.layer-header {
  margin-bottom: 22px;
}

.layer-header h2 {
  margin: 0;
  max-width: 960px;
  font-size: clamp(1.8rem, 4vw, 3rem);
  line-height: 1.15;
  letter-spacing: 0;
}

.layer-intro {
  max-width: 860px;
  margin-bottom: 18px;
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
}

.chapter-panel {
  margin: 18px 0 24px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: 0 8px 24px rgba(35, 42, 31, 0.05);
  overflow: clip;
}

.chapter-header {
  padding: 18px 22px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(90deg, rgba(47,111,88,0.08), rgba(168,104,22,0.06));
}

.chapter-header h3 {
  margin: 0;
  font-size: clamp(1.25rem, 2.2vw, 1.85rem);
  line-height: 1.32;
  letter-spacing: 0;
}

.chapter-body {
  padding: 20px 22px 24px;
}

.doc-paragraph,
.doc-list-line {
  max-width: 980px;
  margin: 0 0 12px;
  color: #30342f;
}

.doc-list-line {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.list-marker {
  width: 7px;
  height: 7px;
  margin-top: 0.72em;
  border-radius: 50%;
  background: var(--green);
}

.list-level-0 {
  margin-top: 16px;
  font-weight: 850;
}

.list-level-0 .list-marker {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: var(--gold);
}

.list-level-1 {
  padding-left: 18px;
}

.list-level-1 .list-marker {
  background: var(--teal);
}

.list-level-2,
.list-level-3 {
  padding-left: 42px;
  color: var(--muted);
}

.list-level-2 .list-marker,
.list-level-3 .list-marker {
  background: transparent;
  border: 2px solid var(--coral);
}

.topic-heading {
  max-width: 980px;
  margin: 28px 0 10px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--blue);
  font-size: clamp(1.08rem, 1.7vw, 1.32rem);
  line-height: 1.36;
  letter-spacing: 0;
}

.subtopic-heading {
  max-width: 980px;
  margin: 22px 0 10px;
  color: var(--green);
  font-size: 1rem;
  line-height: 1.4;
}

.doc-figure {
  margin: 22px 0 26px;
}

.figure-open {
  display: block;
  width: 100%;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: white;
  overflow: hidden;
  cursor: zoom-in;
  box-shadow: 0 8px 28px rgba(35, 42, 31, 0.08);
}

.figure-open img {
  display: block;
  width: 100%;
  height: auto;
}

.doc-table {
  margin: 18px 0 26px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: clip;
}

.doc-table summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 16px;
  cursor: pointer;
  color: var(--ink);
  font-weight: 900;
  list-style: none;
  background: var(--surface-soft);
}

.doc-table summary::-webkit-details-marker {
  display: none;
}

.table-summary-meta {
  color: var(--subtle);
  font-size: 0.85rem;
  font-weight: 700;
}

.table-tools {
  display: grid;
  grid-template-columns: auto minmax(160px, 320px);
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
  background: #fff;
}

.table-scroll {
  max-width: 100%;
  overflow: auto;
  border-top: 1px solid var(--line);
}

table {
  width: 100%;
  min-width: 900px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.9rem;
  line-height: 1.56;
}

.table-wide table {
  min-width: 1280px;
}

th,
td {
  vertical-align: top;
  text-align: left;
  padding: 12px 13px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  min-width: 120px;
}

th:last-child,
td:last-child {
  border-right: 0;
}

thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #eef3eb;
  color: var(--ink);
  font-weight: 900;
}

tbody tr:nth-child(even) td {
  background: #fbfcf8;
}

.table-section-row th,
.table-section-row td {
  background: #f3ead8;
  color: #5f4117;
  font-weight: 900;
}

tr.is-filtered-out {
  display: none;
}

.search-hidden {
  display: none !important;
}

.search-scope.search-dim {
  opacity: 0.4;
}

.back-top {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 80;
  width: 42px;
  height: 42px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--ink);
  color: white;
  cursor: pointer;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.back-top.is-visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.toc-drawer {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 160;
  width: min(88vw, 360px);
  height: 100vh;
  padding: 18px;
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: -20px 0 50px rgba(35, 42, 31, 0.18);
  transform: translateX(105%);
  transition: transform 0.22s ease;
  overflow: auto;
}

.toc-drawer.is-open {
  transform: translateX(0);
}

.toc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 18px;
  font-weight: 900;
}

.toc-close {
  width: 36px;
  padding: 0;
  font-size: 1.3rem;
}

.toc-overlay {
  position: fixed;
  inset: 0;
  z-index: 150;
  background: rgba(32, 35, 31, 0.28);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.toc-overlay.is-open {
  opacity: 1;
  pointer-events: auto;
}

.image-viewer {
  position: fixed;
  inset: 0;
  z-index: 220;
  display: grid;
  place-items: center;
  padding: 64px 24px 24px;
  background: rgba(20, 22, 19, 0.86);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.18s ease;
}

.image-viewer.is-open {
  opacity: 1;
  pointer-events: auto;
}

.image-viewer img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: var(--radius);
  background: white;
}

.image-viewer-close {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 42px;
  height: 42px;
  padding: 0;
  font-size: 1.5rem;
}

body.viewer-open,
body.toc-open {
  overflow: hidden;
}

@media (max-width: 1080px) {
  .brand-link {
    min-width: 0;
  }

  .brand-text {
    max-width: 180px;
  }

  .hero-inner,
  .content-shell {
    grid-template-columns: 1fr;
  }

  .desktop-toc {
    display: none;
  }

  .quick-map {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .topbar {
    gap: 10px;
  }

  .layer-tabs {
    display: none;
  }

  .brand-text {
    max-width: 46vw;
  }

  .hero {
    padding-top: 34px;
  }

  .hero-inner {
    gap: 16px;
  }

  .hero h1 {
    font-size: clamp(2.2rem, 15vw, 4.2rem);
  }

  .reader-tools,
  .chapter-body,
  .chapter-header,
  .layer-intro {
    padding: 14px;
  }

  .search-panel {
    grid-template-columns: 1fr;
  }

  .quick-map {
    grid-template-columns: 1fr;
  }

  .content-shell {
    padding-left: 14px;
    padding-right: 14px;
  }

  table {
    min-width: 760px;
  }

  .table-wide table {
    min-width: 1180px;
  }
}

/* ===== Design refresh: product planning workspace ===== */
:root {
  --bg: #f4f6f8;
  --surface: #ffffff;
  --surface-soft: #f8fafc;
  --ink: #16202a;
  --muted: #536171;
  --subtle: #8a95a3;
  --line: #d9e0e8;
  --line-strong: #b9c4d0;
  --green: #0f8f74;
  --teal: #0e7490;
  --gold: #b7791f;
  --coral: #c24b2a;
  --blue: #2563eb;
  --radius: 8px;
  --shadow: 0 14px 38px rgba(22, 32, 42, 0.08);
  --nav-h: 58px;
}

body.planning-page {
  background:
    linear-gradient(180deg, #ffffff 0, #f8fafc 170px, var(--bg) 420px),
    var(--bg);
  color: var(--ink);
  font-size: calc(15.5px * var(--font-scale));
}

.read-progress {
  height: 4px;
  background: linear-gradient(90deg, var(--blue), var(--green), var(--gold), var(--coral));
}

.topbar {
  min-height: var(--nav-h);
  padding: 9px clamp(14px, 3vw, 32px);
  gap: 14px;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid var(--line);
}

.topbar.is-scrolled {
  box-shadow: 0 8px 24px rgba(22, 32, 42, 0.08);
}

.brand-link {
  min-width: 210px;
  font-size: 0.94rem;
}

.brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 7px;
  background: #111827;
}

.layer-tabs {
  flex: 0 1 auto;
  margin: 0 auto;
  padding: 3px;
  gap: 2px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #eef2f7;
}

.layer-tab {
  min-height: 30px;
  padding: 5px 11px;
  border-radius: 6px;
  color: #475569;
  font-size: 0.82rem;
}

.layer-tab:hover,
.layer-tab.is-active {
  background: #172033;
  color: #ffffff;
}

.topbar-actions {
  gap: 7px;
}

.icon-button,
.tool-button,
.toc-close,
.image-viewer-close {
  min-height: 34px;
  border-color: var(--line);
  border-radius: 7px;
  background: #ffffff;
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(22, 32, 42, 0.05);
}

.icon-button:hover,
.tool-button:hover,
.toc-close:hover {
  background: #f1f5f9;
  border-color: var(--line-strong);
}

.hero {
  padding: 28px clamp(18px, 4vw, 56px) 18px;
  border-bottom: 1px solid var(--line);
  background:
    linear-gradient(90deg, rgba(37, 99, 235, 0.055), rgba(15, 143, 116, 0.035) 38%, rgba(183, 121, 31, 0.05) 100%),
    #ffffff;
}

.hero-inner {
  max-width: 1440px;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: 22px;
  align-items: start;
}

.hero-label,
.layer-kicker {
  color: var(--blue);
  font-size: 0.76rem;
  text-transform: uppercase;
}

.hero h1 {
  max-width: 720px;
  font-size: clamp(2rem, 4.8vw, 4.2rem);
  line-height: 1.08;
}

.hero-stats {
  gap: 8px;
  margin-top: 18px;
}

.hero-stats span {
  min-height: 32px;
  border-radius: 7px;
  background: #ffffff;
  border-color: var(--line);
  color: var(--muted);
}

.reader-tools {
  align-self: stretch;
  border-color: var(--line);
  background: #ffffff;
  box-shadow: var(--shadow);
}

.search-panel input,
.table-filter {
  min-height: 36px;
  border-radius: 7px;
  background: #ffffff;
}

.search-panel input:focus,
.table-filter:focus {
  border-color: var(--blue);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
}

.tool-row {
  gap: 7px;
}

.tool-button {
  color: #344054;
  font-size: 0.82rem;
}

.quick-map {
  max-width: 1440px;
  margin-top: 18px;
  gap: 10px;
}

.quick-card {
  min-height: 88px;
  padding: 14px;
  border-color: var(--line);
  background: #ffffff;
  box-shadow: 0 1px 0 rgba(22, 32, 42, 0.03);
}

.quick-card:hover {
  transform: translateY(-1px);
  border-color: var(--line-strong);
  box-shadow: var(--shadow);
}

.quick-number {
  color: var(--gold);
  font-size: 0.92rem;
}

.quick-title {
  color: #1f2937;
  font-size: 0.96rem;
}

.quick-meta {
  color: var(--subtle);
}

.content-shell {
  max-width: 1480px;
  grid-template-columns: 292px minmax(0, 1fr);
  gap: 30px;
  padding-top: 22px;
}

.desktop-toc {
  padding-right: 18px;
  border-right: 1px solid var(--line);
}

.toc-list,
.desktop-toc nav {
  gap: 12px;
}

.toc-group {
  padding: 7px 0 7px 12px;
  border-left: 2px solid transparent;
}

.toc-group.is-active {
  border-left-color: var(--blue);
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.07), rgba(255,255,255,0));
}

.toc-layer {
  margin-bottom: 6px;
  color: #111827;
  font-size: 0.94rem;
}

.toc-child {
  padding: 4px 0;
  color: #667085;
  font-size: 0.86rem;
}

.toc-child:hover,
.toc-child.is-active {
  color: var(--blue);
  font-weight: 800;
}

.layer-section {
  margin-bottom: 44px;
  border-top: 0;
}

.layer-inner {
  padding-top: 10px;
}

.layer-header {
  margin: 0 0 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.layer-header h2 {
  max-width: 980px;
  font-size: clamp(1.65rem, 3.4vw, 3rem);
  line-height: 1.14;
}

.layer-intro {
  max-width: 980px;
  margin: 14px 0 18px;
  padding: 16px 18px;
  border: 1px solid #c7d7fe;
  border-left: 5px solid var(--blue);
  border-radius: var(--radius);
  background: #eff6ff;
}

.chapter-panel {
  margin: 18px 0 30px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: visible;
}

.chapter-header {
  margin-bottom: 10px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-left: 5px solid var(--green);
  border-radius: var(--radius);
  background: #ffffff;
  box-shadow: 0 2px 10px rgba(22, 32, 42, 0.04);
}

.chapter-header h3 {
  font-size: clamp(1.18rem, 1.8vw, 1.65rem);
  line-height: 1.3;
}

.chapter-body {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #ffffff;
}

.doc-paragraph,
.doc-list-line {
  max-width: 1020px;
  margin-bottom: 11px;
  color: #25313d;
}

.doc-list-line {
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 9px;
}

.list-marker {
  width: 6px;
  height: 6px;
  margin-top: 0.75em;
  background: var(--teal);
}

.list-level-0 {
  margin-top: 15px;
  color: #111827;
  font-weight: 850;
}

.list-level-0 .list-marker {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: var(--gold);
}

.list-level-1 {
  padding-left: 16px;
}

.list-level-2,
.list-level-3 {
  padding-left: 38px;
  color: #475569;
}

.topic-heading {
  max-width: 1020px;
  margin: 26px 0 12px;
  padding: 14px 0 0;
  border-top: 1px solid var(--line);
  color: #1d4ed8;
  font-size: clamp(1.04rem, 1.4vw, 1.24rem);
}

.subtopic-heading {
  color: var(--green);
}

.doc-figure {
  margin: 18px 0 24px;
}

.figure-open {
  border-color: var(--line);
  border-radius: var(--radius);
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(22, 32, 42, 0.08);
}

.figure-open:hover {
  border-color: var(--blue);
}

.doc-table {
  margin: 16px 0 24px;
  border-color: var(--line);
  border-radius: var(--radius);
  background: #ffffff;
  box-shadow: 0 6px 20px rgba(22, 32, 42, 0.05);
}

.doc-table summary {
  padding: 12px 15px;
  background: #172033;
  color: #ffffff;
}

.table-summary-meta {
  color: #cbd5e1;
}

.table-tools {
  padding: 10px 15px;
  background: #f8fafc;
}

table {
  font-size: 0.88rem;
}

thead th {
  background: #e8eef6;
  color: #111827;
}

th,
td {
  border-color: var(--line);
}

tbody tr:nth-child(even) td {
  background: #fafcff;
}

.table-section-row th,
.table-section-row td {
  background: #fff4df;
  color: #7a4b11;
}

.back-top {
  right: 22px;
  bottom: 22px;
  border-radius: 7px;
  background: #172033;
}

.toc-drawer {
  background: #ffffff;
}

.image-viewer {
  background: rgba(15, 23, 42, 0.88);
}

@media (max-width: 1080px) {
  .hero-inner,
  .content-shell {
    grid-template-columns: 1fr;
  }

  .desktop-toc {
    display: none;
  }

  .quick-map {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .topbar {
    min-height: 58px;
    padding: 8px 12px;
  }

  .brand-link {
    min-width: 0;
  }

  .brand-text {
    max-width: 44vw;
  }

  .hero {
    padding: 22px 18px 18px;
  }

  .hero h1 {
    font-size: clamp(2rem, 13vw, 3.8rem);
  }

  .reader-tools,
  .chapter-body,
  .chapter-header,
  .layer-intro {
    padding: 14px;
  }

  .quick-map {
    grid-template-columns: 1fr;
  }

  .content-shell {
    padding: 18px 14px 70px;
  }

  .layer-header h2 {
    font-size: clamp(1.65rem, 8vw, 2.5rem);
  }

  .doc-list-line {
    grid-template-columns: 14px minmax(0, 1fr);
  }
}

/* ===== Premium interaction refresh v4 ===== */
:root {
  --bg: #eef2f5;
  --surface: #ffffff;
  --surface-soft: #f7f9fc;
  --ink: #101722;
  --muted: #526171;
  --subtle: #8b98a8;
  --line: #d7dee8;
  --line-strong: #aebaca;
  --green: #0f9f7a;
  --teal: #0e7f8f;
  --gold: #b98218;
  --coral: #c75332;
  --blue: #2b6fe8;
  --nav-h: 64px;
  --shadow: 0 18px 45px rgba(16, 23, 34, 0.1);
}

body.planning-page {
  background:
    linear-gradient(180deg, #f9fbfd 0, #eef2f5 360px),
    var(--bg);
  color: var(--ink);
}

.topbar {
  min-height: var(--nav-h);
  padding: 10px clamp(18px, 3vw, 42px);
  background: rgba(255, 255, 255, 0.86);
  border-bottom: 1px solid rgba(174, 186, 202, 0.55);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.9) inset;
}

.topbar.is-scrolled {
  box-shadow: 0 14px 40px rgba(16, 23, 34, 0.12);
}

.brand-link {
  min-width: 230px;
  font-size: 0.95rem;
  letter-spacing: 0;
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #101722, #123f3a);
  box-shadow: 0 10px 22px rgba(16, 23, 34, 0.22);
}

.layer-tabs {
  max-width: 370px;
  padding: 4px;
  background: rgba(238, 242, 245, 0.82);
  border: 1px solid rgba(174, 186, 202, 0.65);
  box-shadow: 0 8px 24px rgba(16, 23, 34, 0.05) inset;
}

.layer-tab {
  min-height: 32px;
  padding: 5px 13px;
  color: #4b5b6a;
}

.layer-tab:hover,
.layer-tab.is-active {
  background: #101722;
  color: #ffffff;
  box-shadow: 0 8px 18px rgba(16, 23, 34, 0.2);
}

.section-chip {
  display: grid;
  min-width: 220px;
  max-width: 330px;
  padding: 5px 12px;
  border-left: 1px solid var(--line);
}

.section-chip span {
  color: var(--subtle);
  font-size: 0.72rem;
  line-height: 1.2;
}

.section-chip strong {
  overflow: hidden;
  color: #1f2a37;
  font-size: 0.88rem;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-actions {
  gap: 8px;
}

.icon-button,
.tool-button,
.toc-close,
.image-viewer-close {
  border: 1px solid rgba(174, 186, 202, 0.7);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 20px rgba(16, 23, 34, 0.06);
}

.icon-button:hover,
.tool-button:hover,
.toc-close:hover {
  background: #101722;
  border-color: #101722;
  color: #ffffff;
}

#focusToggle[aria-pressed="true"] {
  background: #101722;
  color: #ffffff;
}

.hero {
  padding: 34px clamp(18px, 4vw, 56px) 24px;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.76), rgba(255,255,255,0.3)),
    linear-gradient(90deg, rgba(43,111,232,0.08), rgba(15,159,122,0.06), rgba(185,130,24,0.07));
  border-bottom: 1px solid rgba(174, 186, 202, 0.5);
}

.hero-inner {
  max-width: 1500px;
  grid-template-columns: minmax(0, 1fr) minmax(380px, 460px);
  align-items: stretch;
}

.hero-label {
  color: var(--teal);
}

.hero h1 {
  font-size: clamp(2.2rem, 5vw, 4.8rem);
  line-height: 1.03;
}

.hero-stats span {
  border-color: rgba(174, 186, 202, 0.7);
  background: rgba(255,255,255,0.78);
  box-shadow: 0 8px 24px rgba(16, 23, 34, 0.05);
}

.reader-tools {
  display: grid;
  align-content: center;
  border: 1px solid rgba(174, 186, 202, 0.65);
  background: rgba(255,255,255,0.82);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow);
}

.search-panel {
  grid-template-columns: auto minmax(0, 1fr) auto;
}

.search-panel input,
.table-filter {
  border-color: rgba(174, 186, 202, 0.75);
  background: #ffffff;
}

.quick-map {
  max-width: 1500px;
  gap: 14px;
}

.quick-card {
  position: relative;
  min-height: 106px;
  padding: 17px;
  border: 1px solid rgba(174, 186, 202, 0.65);
  background: rgba(255,255,255,0.86);
  box-shadow: 0 12px 28px rgba(16, 23, 34, 0.07);
  overflow: hidden;
}

.quick-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: linear-gradient(180deg, var(--blue), var(--green), var(--gold));
}

.quick-card:hover {
  transform: translateY(-3px);
  border-color: rgba(43,111,232,0.45);
  box-shadow: 0 18px 38px rgba(16, 23, 34, 0.12);
}

.quick-number {
  color: var(--blue);
}

.quick-title {
  font-size: 1rem;
}

.content-shell {
  max-width: 1540px;
  grid-template-columns: minmax(260px, 318px) minmax(0, 1fr);
  gap: 34px;
  padding-top: 30px;
}

.desktop-toc {
  height: calc(100vh - var(--nav-h) - 44px);
  padding: 16px 18px 16px 0;
  border-right: 1px solid rgba(174, 186, 202, 0.62);
}

.toc-group {
  margin-bottom: 4px;
  padding: 9px 10px 9px 14px;
  border-left: 2px solid transparent;
  border-radius: 0 8px 8px 0;
}

.toc-group.is-active {
  border-left-color: var(--blue);
  background: rgba(255,255,255,0.78);
  box-shadow: 0 12px 28px rgba(16, 23, 34, 0.07);
}

.toc-layer {
  color: #18212f;
  font-size: 0.94rem;
}

.toc-child {
  color: #66758a;
}

.toc-child:hover,
.toc-child.is-active {
  color: var(--blue);
}

.layer-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  padding: 0 0 18px;
  border-bottom: 1px solid rgba(174, 186, 202, 0.62);
}

.layer-kicker {
  color: var(--green);
}

.layer-header h2 {
  max-width: 1080px;
  font-size: clamp(2rem, 4vw, 3.6rem);
  line-height: 1.08;
}

.layer-intro {
  max-width: 1080px;
  padding: 18px 20px;
  border: 1px solid rgba(43,111,232,0.25);
  border-left: 5px solid var(--blue);
  background: rgba(255,255,255,0.82);
  box-shadow: 0 14px 34px rgba(16, 23, 34, 0.06);
}

.chapter-panel {
  margin: 24px 0 34px;
}

.chapter-header {
  position: relative;
  margin-bottom: 0;
  padding: 17px 20px;
  border: 1px solid rgba(174, 186, 202, 0.7);
  border-left: 0;
  border-radius: 8px 8px 0 0;
  background: #ffffff;
  box-shadow: 0 14px 32px rgba(16, 23, 34, 0.08);
}

.chapter-header::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  border-radius: 8px 0 0 0;
  background: linear-gradient(180deg, var(--green), var(--blue));
}

.chapter-header h3 {
  padding-left: 2px;
  color: #121a26;
  font-size: clamp(1.2rem, 1.9vw, 1.75rem);
}

.chapter-body {
  padding: 24px;
  border: 1px solid rgba(174, 186, 202, 0.7);
  border-top: 0;
  border-radius: 0 0 8px 8px;
  background: rgba(255,255,255,0.92);
  box-shadow: 0 18px 44px rgba(16, 23, 34, 0.09);
}

.doc-paragraph,
.doc-list-line {
  max-width: 1080px;
  color: #273241;
}

.list-level-0 {
  color: #141d2a;
}

.list-marker {
  background: var(--teal);
}

.list-level-0 .list-marker {
  background: var(--gold);
  box-shadow: 0 0 0 4px rgba(185,130,24,0.12);
}

.topic-heading {
  max-width: 1080px;
  margin-top: 30px;
  color: #1f5fd6;
}

.topic-heading::before {
  content: "";
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 9px;
  border-radius: 50%;
  background: var(--green);
}

.figure-open {
  border-color: rgba(174, 186, 202, 0.7);
  background: #ffffff;
  box-shadow: 0 18px 45px rgba(16, 23, 34, 0.12);
}

.doc-table {
  border: 1px solid rgba(174, 186, 202, 0.7);
  box-shadow: 0 18px 42px rgba(16, 23, 34, 0.09);
}

.doc-table summary {
  background: linear-gradient(90deg, #101722, #163238);
  color: #ffffff;
}

.table-tools {
  background: #f7f9fc;
}

thead th {
  background: #edf2f8;
}

.back-top {
  background: #101722;
  box-shadow: 0 14px 26px rgba(16, 23, 34, 0.28);
}

body.focus-mode .content-shell {
  grid-template-columns: minmax(0, 1120px);
  justify-content: center;
}

body.focus-mode .desktop-toc {
  display: none;
}

body.focus-mode .section-chip {
  max-width: 460px;
}

body.focus-mode .document-flow {
  width: 100%;
}

@media (max-width: 1180px) {
  .section-chip {
    display: none;
  }
}

@media (max-width: 720px) {
  .topbar {
    padding: 8px 12px;
  }

  .brand-link {
    min-width: 0;
  }

  .hero {
    padding: 24px 16px 18px;
  }

  .hero-inner {
    grid-template-columns: 1fr;
  }

  .hero h1 {
    font-size: clamp(2.25rem, 13vw, 4rem);
  }

  .quick-card {
    min-height: 94px;
  }

  .content-shell {
    padding: 20px 12px 72px;
  }

  .chapter-body {
    padding: 18px 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
"""


JS = r"""
if ('scrollRestoration' in history) {
  history.scrollRestoration = 'manual';
}

function getScrollOffset() {
  const value = Number.parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
  return Number.isFinite(value) ? value : 0;
}

function settleInitialScroll() {
  const target = window.location.hash ? document.querySelector(window.location.hash) : null;
  if (target) {
    const offset = getScrollOffset();
    const top = Math.max(0, window.scrollY + target.getBoundingClientRect().top - offset);
    window.scrollTo(0, top);
  } else {
    window.scrollTo(0, 0);
  }
}

function scheduleInitialScroll() {
  requestAnimationFrame(() => {
    settleInitialScroll();
    setTimeout(settleInitialScroll, 350);
    setTimeout(settleInitialScroll, 1100);
  });
}

if (document.readyState === 'loading') {
  window.addEventListener('load', scheduleInitialScroll, { once: true });
} else {
  scheduleInitialScroll();
}

const topbar = document.getElementById('topbar');
const readProgress = document.getElementById('readProgress');
const backTop = document.getElementById('backTop');
const tocToggle = document.getElementById('tocToggle');
const tocDrawer = document.getElementById('tocDrawer');
const tocClose = document.getElementById('tocClose');
const tocOverlay = document.getElementById('tocOverlay');
const searchToggle = document.getElementById('searchToggle');
const focusToggle = document.getElementById('focusToggle');
const sectionChip = document.getElementById('sectionChip');
const searchPanel = document.getElementById('searchPanel');
const globalSearch = document.getElementById('globalSearch');
const searchCount = document.getElementById('searchCount');
const expandTables = document.getElementById('expandTables');
const collapseTables = document.getElementById('collapseTables');
const fontDecrease = document.getElementById('fontDecrease');
const fontIncrease = document.getElementById('fontIncrease');
const imageViewer = document.getElementById('imageViewer');
const imageViewerImg = document.getElementById('imageViewerImg');
const imageViewerClose = document.getElementById('imageViewerClose');

const layerSections = [...document.querySelectorAll('[data-layer-section]')];
const layerTabs = [...document.querySelectorAll('.layer-tab')];
const tocGroups = [...document.querySelectorAll('.toc-group')];
const tocChildren = [...document.querySelectorAll('.toc-child')];
const chapters = [...document.querySelectorAll('.chapter-panel')];
let currentChapterId = chapters[0]?.id || '';

function setProgress() {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  readProgress.style.width = `${max > 0 ? (window.scrollY / max) * 100 : 0}%`;
}

function onScroll() {
  topbar.classList.toggle('is-scrolled', window.scrollY > 6);
  backTop.classList.toggle('is-visible', window.scrollY > 520);
  setProgress();
}

function openToc() {
  tocDrawer.classList.add('is-open');
  tocOverlay.classList.add('is-open');
  document.body.classList.add('toc-open');
}

function closeToc() {
  tocDrawer.classList.remove('is-open');
  tocOverlay.classList.remove('is-open');
  document.body.classList.remove('toc-open');
}

function activeLayer(id) {
  layerTabs.forEach((tab) => tab.classList.toggle('is-active', tab.dataset.layer === id));
  tocGroups.forEach((group) => group.classList.toggle('is-active', group.dataset.layerLink === id));
}

function activeTocLink(id) {
  currentChapterId = id;
  tocChildren.forEach((link) => link.classList.toggle('is-active', link.getAttribute('href') === `#${id}`));
  const target = document.getElementById(id);
  const label = target?.querySelector('.chapter-header h3')?.textContent || target?.querySelector('h2')?.textContent;
  if (label && sectionChip) sectionChip.querySelector('strong').textContent = label;
}

function setFocusMode(enabled) {
  document.body.classList.toggle('focus-mode', enabled);
  focusToggle?.setAttribute('aria-pressed', String(enabled));
  if (focusToggle) focusToggle.textContent = enabled ? '退出专注' : '专注';
}

function findViewportChapterId() {
  const offset = getScrollOffset();
  let best = chapters[0]?.id || '';
  let bestDistance = Number.POSITIVE_INFINITY;
  chapters.forEach((chapter) => {
    const distance = Math.abs(chapter.getBoundingClientRect().top - offset);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = chapter.id;
    }
  });
  return best;
}

const layerObserver = new IntersectionObserver((entries) => {
  const visible = entries
    .filter((entry) => entry.isIntersecting)
    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (visible) activeLayer(visible.target.dataset.layerSection);
}, { rootMargin: '-24% 0px -64% 0px', threshold: [0.01, 0.1, 0.25] });

layerSections.forEach((section) => layerObserver.observe(section));

const chapterObserver = new IntersectionObserver((entries) => {
  const visible = entries
    .filter((entry) => entry.isIntersecting)
    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (visible) activeTocLink(visible.target.id);
}, { rootMargin: '-20% 0px -70% 0px', threshold: [0.01, 0.1] });

chapters.forEach((chapter) => chapterObserver.observe(chapter));

function normalize(value) {
  return value.trim().toLowerCase();
}

function runGlobalSearch() {
  if (!globalSearch) return;
  const query = normalize(globalSearch.value);
  let matches = 0;

  chapters.forEach((chapter) => {
    const hit = !query || chapter.textContent.toLowerCase().includes(query);
    chapter.classList.toggle('search-hidden', !hit);
    if (query && hit) matches += 1;
  });

  document.querySelectorAll('.layer-section').forEach((layer) => {
    const hasVisibleChapter = [...layer.querySelectorAll('.chapter-panel')].some((chapter) => !chapter.classList.contains('search-hidden'));
    const layerIntroHit = !query || layer.querySelector('.layer-intro')?.textContent.toLowerCase().includes(query);
    layer.classList.toggle('search-hidden', query && !hasVisibleChapter && !layerIntroHit);
  });

  searchCount.textContent = query ? `${matches} 个章节` : '未搜索';
}

function filterTable(input) {
  const query = normalize(input.value);
  const table = input.closest('.doc-table')?.querySelector('table');
  if (!table) return;
  table.querySelectorAll('tbody tr').forEach((row) => {
    row.classList.toggle('is-filtered-out', query && !row.textContent.toLowerCase().includes(query));
  });
}

function setFontScale(delta) {
  const current = Number.parseFloat(localStorage.getItem('planningFontScale') || '1');
  const next = Math.min(1.18, Math.max(0.9, current + delta));
  localStorage.setItem('planningFontScale', String(next));
  document.documentElement.style.setProperty('--font-scale', next);
}

function initFontScale() {
  const stored = Number.parseFloat(localStorage.getItem('planningFontScale') || '1');
  if (Number.isFinite(stored)) {
    document.documentElement.style.setProperty('--font-scale', stored);
  }
}

function openImage(src) {
  imageViewerImg.src = src;
  imageViewer.classList.add('is-open');
  imageViewer.setAttribute('aria-hidden', 'false');
  document.body.classList.add('viewer-open');
}

function closeImage() {
  imageViewer.classList.remove('is-open');
  imageViewer.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('viewer-open');
  imageViewerImg.src = '';
}

window.addEventListener('scroll', onScroll, { passive: true });
window.addEventListener('resize', setProgress);
tocToggle?.addEventListener('click', openToc);
tocClose?.addEventListener('click', closeToc);
tocOverlay?.addEventListener('click', closeToc);
backTop?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

document.addEventListener('click', (event) => {
  const anchor = event.target.closest('a[href^="#"]');
  if (anchor && document.querySelector(anchor.getAttribute('href'))) closeToc();

  const imageButton = event.target.closest('[data-full-image]');
  if (imageButton) openImage(imageButton.dataset.fullImage);
});

searchToggle?.addEventListener('click', () => {
  globalSearch?.focus();
  searchPanel?.scrollIntoView({ block: 'center', behavior: 'smooth' });
});

globalSearch?.addEventListener('input', runGlobalSearch);

document.querySelectorAll('.table-filter').forEach((input) => {
  input.addEventListener('input', () => filterTable(input));
});

expandTables?.addEventListener('click', () => {
  document.querySelectorAll('.doc-table').forEach((table) => table.open = true);
});

collapseTables?.addEventListener('click', () => {
  document.querySelectorAll('.doc-table').forEach((table) => table.open = false);
});

fontDecrease?.addEventListener('click', () => setFontScale(-0.04));
fontIncrease?.addEventListener('click', () => setFontScale(0.04));
focusToggle?.addEventListener('click', () => {
  const keepId = findViewportChapterId() || currentChapterId;
  setFocusMode(!document.body.classList.contains('focus-mode'));
  requestAnimationFrame(() => {
    const target = keepId ? document.getElementById(keepId) : null;
    if (!target) return;
    const top = Math.max(0, window.scrollY + target.getBoundingClientRect().top - getScrollOffset());
    window.scrollTo(0, top);
  });
});
imageViewerClose?.addEventListener('click', closeImage);
imageViewer?.addEventListener('click', (event) => {
  if (event.target === imageViewer) closeImage();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeToc();
    closeImage();
  }
});

initFontScale();
setFocusMode(false);
onScroll();
runGlobalSearch();
"""


def main() -> None:
    if not SOURCE_DOCX.exists():
        raise FileNotFoundError(SOURCE_DOCX)
    copy_assets()
    blocks = extract_blocks()
    (ROOT / "planning.html").write_text(render_html(blocks), encoding="utf-8")
    # Styles live in planning.css; interaction logic lives in app.js — edit those files directly.
    print(f"Built planning.html from {SOURCE_DOCX}")
    print(f"Assets: {ASSET_DIR}")


if __name__ == "__main__":
    main()
