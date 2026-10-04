#!/usr/bin/env python3
"""Render docs/domain into a static site for GitHub Pages.

Source of truth is the markdown. The HTML under docs/domain/site is generated.
Uses only the Python standard library.
"""

from __future__ import annotations

import html
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "docs" / "domain"
SLIDES = ROOT / "docs" / "slides"
OUT = Path(
    __import__("os").environ.get("LW_SITE_OUT", str(DOMAIN / "site"))
)
ASSETS = DOMAIN / "assets"

PAGES = [
    ("README.md", "index.html", "Overview", "Overview"),
    ("start-here.md", "start-here.html", "Start here", "Decide"),
    ("01-concerns.md", "01-concerns.html", "Concerns", "Decide"),
    ("02-lifecycle.md", "02-lifecycle.html", "CVE lifecycle", "Decide"),
    ("03-solutions.md", "03-solutions.html", "Solutions", "Decide"),
    ("04-pipeline-only.md", "04-pipeline-only.html", "Pipeline only", "Execute"),
    ("05-pipeline-with-agents.md", "05-pipeline-with-agents.html", "Pipeline with agents", "Execute"),
    ("06-fully-agentic.md", "06-fully-agentic.html", "Fully agentic", "Execute"),
    ("07-how-to-choose.md", "07-how-to-choose.html", "How to choose", "Execute"),
    ("08-lightwell.md", "08-lightwell.html", "Lightwell", "Lightwell"),
    ("sources.md", "sources.html", "Sources", "Reference"),
    ("00-boundaries.md", "00-boundaries.html", "Boundaries", "Reference"),
    ("04-agent-map.md", "04-agent-map.html", "Agent map", "Reference"),
    ("05-skill-contract.md", "05-skill-contract.html", "Skill contract", "Reference"),
]

REFERENCE_GROUPS = {"Reference"}

CALLOUTS = {
    "in": ("In domain", "callout in"),
    "out": ("Out of domain", "callout out"),
    "now": ("Current code", "callout now"),
}


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def slugify(text: str) -> str:
    plain = re.sub(r"<[^>]+>", "", text)
    plain = html.unescape(plain)
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return slug or "section"


def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    pieces: list[str] = []
    for token in re.split(r"(`[^`]+`)", escaped):
        if len(token) >= 2 and token.startswith("`") and token.endswith("`"):
            pieces.append(f"<code>{token[1:-1]}</code>")
            continue
        rich = re.sub(
            r"\[([^\]]+)\]\(([^)\s]+)\)",
            lambda match: (
                f'<a href="{html.escape(match.group(2), quote=True)}">'
                f"{match.group(1)}</a>"
            ),
            token,
        )
        rich = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rich)
        rich = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", rich)
        pieces.append(rich)
    return "".join(pieces)


class Renderer:
    def __init__(self) -> None:
        self.headings: list[tuple[int, str, str]] = []
        self._ids: dict[str, int] = {}

    def heading_id(self, title: str, explicit: str | None = None) -> str:
        base = explicit or slugify(title)
        count = self._ids.get(base, 0) + 1
        self._ids[base] = count
        hid = base if count == 1 else f"{base}-{count}"
        return hid

    def add_heading(self, level: int, title_html: str, hid: str) -> None:
        self.headings.append((level, title_html, hid))

    def render(self, text: str) -> str:
        lines = text.splitlines()
        blocks: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                index += 1
                code: list[str] = []
                while index < len(lines) and not lines[index].strip().startswith("```"):
                    code.append(lines[index])
                    index += 1
                index += 1
                klass = f' class="language-{html.escape(lang)}"' if lang else ""
                blocks.append(
                    f"<pre><code{klass}>{html.escape(chr(10).join(code))}</code></pre>"
                )
                continue

            if stripped.startswith(":::"):
                kind = stripped[3:].strip()
                if kind == "phase":
                    phases: list[dict[str, str]] = []
                    while True:
                        index += 1
                        inner: list[str] = []
                        while index < len(lines) and lines[index].strip() != ":::":
                            inner.append(lines[index])
                            index += 1
                        if index < len(lines) and lines[index].strip() == ":::":
                            index += 1
                        phases.append(self.parse_phase_fields("\n".join(inner)))
                        while index < len(lines) and lines[index].strip() == "":
                            index += 1
                        if index < len(lines) and lines[index].strip() == ":::phase":
                            continue
                        break
                    blocks.append(self.lifecycle_stage(phases))
                    continue
                index += 1
                inner = []
                while index < len(lines) and lines[index].strip() != ":::":
                    inner.append(lines[index])
                    index += 1
                index += 1
                blocks.append(self.directive(kind, "\n".join(inner)))
                continue

            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                title = stripped[level:].strip()
                hid = self.heading_id(title)
                title_html = inline(title)
                self.add_heading(level, title_html, hid)
                blocks.append(f'<h{level} id="{hid}">{title_html}</h{level}>')
                index += 1
                continue

            if stripped.startswith("|"):
                table_lines = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index].strip())
                    index += 1
                blocks.append(self.table(table_lines))
                continue

            if re.match(r"^(- |\d+\. )", stripped):
                ordered = bool(re.match(r"^\d+\. ", stripped))
                items: list[str] = []
                while index < len(lines) and re.match(
                    r"^(- |\d+\. )", lines[index].strip()
                ):
                    item = re.sub(r"^(- |\d+\. )", "", lines[index].strip())
                    items.append(f"<li>{inline(item)}</li>")
                    index += 1
                tag = "ol" if ordered else "ul"
                blocks.append(f"<{tag}>{''.join(items)}</{tag}>")
                continue

            if stripped in {"---", "***"}:
                blocks.append("<hr>")
                index += 1
                continue

            if stripped == "":
                index += 1
                continue

            para = [stripped]
            index += 1
            while index < len(lines):
                nxt = lines[index].strip()
                if nxt == "" or self._starts_block(nxt):
                    break
                para.append(nxt)
                index += 1
            blocks.append(f"<p>{inline(' '.join(para))}</p>")
        return "\n".join(blocks)

    @staticmethod
    def _starts_block(text: str) -> bool:
        return bool(
            text.startswith("#")
            or text.startswith("|")
            or text.startswith("```")
            or text.startswith(":::")
            or text in {"---", "***"}
            or re.match(r"^(- |\d+\. )", text)
        )

    def directive(self, kind: str, body: str) -> str:
        if kind in CALLOUTS:
            label, klass = CALLOUTS[kind]
            inner_html = Renderer().render(body) if body.strip() else ""
            # Keep heading ids on the page renderer only.
            return (
                f'<aside class="{klass}"><p class="callout-label">{label}</p>'
                f"{inner_html}</aside>"
            )
        if kind == "cards":
            cards = []
            for line in body.splitlines():
                if "|" not in line:
                    continue
                label, text, href = [part.strip() for part in line.split("|", 2)]
                cards.append(
                    f'<a class="card" href="{html.escape(href, quote=True)}">'
                    f"<span>{inline(label)}</span><strong>{inline(text)}</strong></a>"
                )
            return f'<div class="card-grid">{"".join(cards)}</div>'
        if kind == "equation":
            bits = []
            for part in (piece.strip() for piece in body.split("|")):
                if not part:
                    continue
                if part in {"=", "+"}:
                    bits.append(f"<b>{html.escape(part)}</b>")
                else:
                    bits.append(f"<span>{inline(part)}</span>")
            return f'<p class="equation">{"".join(bits)}</p>'
        return f"<pre><code>{html.escape(body)}</code></pre>"

    @staticmethod
    def parse_phase_fields(body: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for line in body.splitlines():
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            fields[key.strip()] = value.strip()
        return fields

    def lifecycle_stage(self, phases: list[dict[str, str]]) -> str:
        tabs: list[str] = []
        panels: list[str] = []
        for index, fields in enumerate(phases):
            number = fields.get("number", f"{index + 1:02d}")
            title = fields.get("title", "")
            hid = self.heading_id(title, f"phase-{number}")
            title_html = inline(title)
            self.add_heading(2, f"{number} {title_html}", hid)
            selected = index == 0
            flag = (
                '<span class="station-flag">Agents act here</span>'
                if number == "09"
                else ""
            )
            tabs.append(
                f'<button type="button" role="tab" id="tab-{hid}" '
                f'aria-controls="{hid}" aria-selected="{str(selected).lower()}" '
                f'tabindex="{0 if selected else -1}">'
                f'<span class="station-num">{html.escape(number)}</span>'
                f'<span class="station-name">{title_html}</span>{flag}</button>'
            )
            rows = "".join(
                f"<div><dt>{html.escape(label)}</dt><dd>{inline(fields.get(key, ''))}</dd></div>"
                for label, key in (
                    ("Primary actors", "actors"),
                    ("Work performed", "work"),
                    ("Output and handoff", "output"),
                    ("AI-era pressure", "ai"),
                )
            )
            hidden = "" if selected else " hidden"
            panels.append(
                f'<article class="phase-panel" id="{hid}" role="tabpanel" '
                f'aria-labelledby="tab-{hid}"{hidden}>'
                f'<p class="kicker">{inline(fields.get("owner", ""))}</p>'
                f"<h2>{title_html}</h2>"
                f'<p class="purpose">{inline(fields.get("purpose", ""))}</p>'
                f"<dl>{rows}</dl></article>"
            )
        record = (
            '<div class="record-track"><span>Formal CVE record</span><ol>'
            "<li>No ID</li><li>Reserved</li><li>Published</li>"
            "<li>Updated or Rejected</li></ol></div>"
        )
        script = (
            "<script>(function(){var id=location.hash.slice(1);if(!id)return;"
            "var panel=document.getElementById(id);"
            "if(!panel||!panel.classList.contains('phase-panel'))return;"
            "document.querySelectorAll('.phase-panel').forEach(function(item){"
            "item.hidden=item!==panel;});})();</script>"
        )
        return (
            '<section class="lifecycle-stage" aria-roledescription="lifecycle">'
            f"{record}"
            '<div class="phase-scroller">'
            '<button type="button" class="phase-shift" data-dir="-1" aria-label="Earlier phase">‹</button>'
            '<div class="phase-track" role="tablist" aria-label="Lifecycle phases">'
            f'{"".join(tabs)}</div>'
            '<button type="button" class="phase-shift" data-dir="1" aria-label="Later phase">›</button>'
            "</div>"
            '<div class="phase-progress" aria-hidden="true"><span></span></div>'
            f'<div class="phase-panels">{"".join(panels)}</div>'
            '<p class="loop-note">Exploitation evidence, incomplete fixes, incidents, and postmortems '
            "update the record and feed prevention back into research and development.</p>"
            f"{script}</section>"
        )

    @staticmethod
    def table(lines: list[str]) -> str:
        rows = []
        for line in lines:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells and all(
                re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells
            ):
                continue
            rows.append(cells)
        if not rows:
            return ""
        head = rows[0]
        body = rows[1:]
        thead = "".join(f"<th>{inline(cell)}</th>" for cell in head)
        tbody = "".join(
            "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>"
            for row in body
        )
        return f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>'


def toc_html(headings: list[tuple[int, str, str]]) -> str:
    useful = [item for item in headings if item[0] in {2, 3}]
    if len(useful) < 2:
        return ""
    items = []
    for level, title, hid in useful:
        items.append(
            f'<a class="toc-{level}" href="#{hid}">{title}</a>'
        )
    return (
        '<nav class="toc" aria-label="On this page"><p>On this page</p>'
        + "".join(items)
        + "</nav>"
    )


def page_html(
    title: str,
    summary: str,
    group: str,
    body: str,
    toc: str,
    current: str,
    is_reference: bool = False,
) -> str:
    nav_groups: list[tuple[str, list[str]]] = []
    for _src, href, label, grp in PAGES:
        if not nav_groups or nav_groups[-1][0] != grp:
            nav_groups.append((grp, []))
        current_attr = ' aria-current="page"' if href == current else ""
        nav_groups[-1][1].append(
            f'<a href="{href}"{current_attr}>{html.escape(label)}</a>'
        )
    nav = []
    for grp, links in nav_groups:
        nav.append(f'<p class="nav-label">{html.escape(grp)}</p>')
        nav.append("".join(links))
    nav.append('<p class="nav-label">Elsewhere</p>')
    nav.append('<a href="slides/index.html">Slide deck</a>')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · CVE remediation at scale</title>
<meta name="description" content="{html.escape(summary)}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%23EE0000'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:ital,wght@0,400;0,500;0,700;1,500&amp;family=Red+Hat+Mono:wght@400;500&amp;family=Red+Hat+Text:ital,wght@0,400;0,500;0,600;1,400&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<div class="shell">
  <aside class="rail">
    <div class="brand">
      <span class="mark" aria-hidden="true"></span>
      <div>
        <strong>lw-agents</strong>
        <em>CVE remediation</em>
      </div>
    </div>
    <label class="filter">
      <span class="visually-hidden">Filter pages</span>
      <input id="nav-filter" type="search" placeholder="Filter pages" autocomplete="off">
    </label>
    <nav class="nav" aria-label="CVE remediation at scale">
      {''.join(nav)}
    </nav>
    <div class="rail-foot">
      <button id="theme-toggle" type="button">Dark theme</button>
      <p>Skills are not aligned to this pack yet.</p>
    </div>
  </aside>
  <div class="main">
    <header class="topbar">
      <button id="nav-toggle" type="button" aria-expanded="false">Contents</button>
      <p class="crumb">{html.escape(group)}</p>
    </header>
    <div class="layout">
      <article id="content" class="article">
        <p class="eyebrow">{html.escape(group)}</p>
        <h1>{html.escape(title)}</h1>
        <p class="lede">{html.escape(summary)}</p>
        {'<p class="status">Reference page for skill authors. The skills in the repository still describe a Maven Central upgrade.</p>' if is_reference else ''}
        {body}
      </article>
      {toc}
    </div>
    <footer>
      <p>From advisory to production — CVE remediation at scale. The ten phases are a working model, not a CVE Program standard. Lightwell behavior follows the product docs named in Sources.</p>
    </footer>
  </div>
</div>
<script src="assets/site.js"></script>
</body>
</html>
"""


def build() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ASSETS, OUT / "assets")
    shutil.copytree(SLIDES, OUT / "slides")
    shutil.copytree(DOMAIN / "fixtures", OUT / "fixtures")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    for source_name, href, _label, group in PAGES:
        source = DOMAIN / source_name
        meta, body = parse_front_matter(source.read_text(encoding="utf-8"))
        renderer = Renderer()
        rendered = renderer.render(body)
        title = meta.get("title", href)
        summary = meta.get("summary", "")
        is_ref = group in REFERENCE_GROUPS
        page = page_html(title, summary, group, rendered, toc_html(renderer.headings), href, is_reference=is_ref)
        (OUT / href).write_text(page, encoding="utf-8")

    site = (OUT / "index.html").read_text(encoding="utf-8")
    lifecycle = (OUT / "02-lifecycle.html").read_text(encoding="utf-8")
    lightwell = (OUT / "08-lightwell.html").read_text(encoding="utf-8")
    agent_map = (OUT / "04-agent-map.html").read_text(encoding="utf-8")
    required = [
        "3.14.0.rhlw-00001",
        "Maven Central",
        "cve-triage",
    ]
    blob = site + lifecycle + lightwell + agent_map
    blob += (OUT / "05-pipeline-with-agents.html").read_text(encoding="utf-8")
    missing = [item for item in required if item not in blob]
    if missing:
        raise SystemExit(f"built site is missing: {missing}")
    forbidden = "Lightwell-demo1"
    for path in OUT.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".md", ".yml", ".yaml", ".json"}:
            if forbidden in path.read_text(encoding="utf-8", errors="ignore"):
                raise SystemExit(f"refusing to publish a demo password in {path}")
    titles = [
        "Discover",
        "Intake",
        "Validate and scope",
        "Reserve and coordinate",
        "Assess in parallel",
        "Fix and release",
        "Publish and enrich",
        "Repackage and integrate",
        "Prioritize and remediate",
        "Observe and learn",
    ]
    absent = [title for title in titles if title not in lifecycle]
    if absent:
        raise SystemExit(f"lifecycle page missing phases: {absent}")
    if "lifecycle-stage" not in lifecycle or lifecycle.count('role="tab"') != 10:
        raise SystemExit("lifecycle stage did not render ten phases")
    if not (OUT / "slides" / "index.html").exists():
        raise SystemExit("slide deck was not copied")
    decide_pages = ["index.html", "01-concerns.html", "03-solutions.html",
                     "04-pipeline-only.html", "05-pipeline-with-agents.html",
                     "06-fully-agentic.html", "07-how-to-choose.html"]
    for dp in decide_pages:
        content = (OUT / dp).read_text(encoding="utf-8")
        if "Reference page for skill authors" in content:
            raise SystemExit(f"decide page {dp} has the reference warning")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:  # noqa: BLE001 — surface build failures clearly
        print(exc, file=sys.stderr)
        raise
