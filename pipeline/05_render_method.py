#!/usr/bin/env python3
"""Render METHODOLOGY.md into web/method.html.

METHODOLOGY.md is the contract (CLAUDE.md). This page is its typeset copy for
readers who arrive from the map or the story rather than from the repository,
and it is generated, never hand-edited: the page carries the sha256 of the
source it was rendered from and the verifier fails when that no longer matches
the file, so the two cannot drift apart silently.

Standard library only, no markdown package. The document uses a small, stable
subset of Markdown (ATX headings to three levels, paragraphs, fenced code, pipe
tables, bullet lists, block quotes, thematic breaks, bold, italic, code spans
and bare URLs), and a dependency for that would cost more than the parser
below. Anything outside the subset renders as a plain paragraph rather than
failing, so a new construct shows up on the page as un-typeset text, which is
the visible kind of failure.

Section references in the text ("§3.4", "§5") become links to the matching
heading, and the numbered run-in limitations of §5 ("**5.1 Media vantage
bias.**") get anchors and table-of-contents entries of their own, because the
issue templates and the interface cite them by number.

Run after editing METHODOLOGY.md:

    python3 pipeline/05_render_method.py

`--check` exits non-zero when web/method.html differs from what the current
METHODOLOGY.md renders to (what the verifier runs). The refresh workflow does
not run this step: the methodology changes with the method, not with the
monthly data.
"""
from __future__ import annotations

import hashlib
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "METHODOLOGY.md"
OUT = ROOT / "web" / "method.html"
REPO = "https://github.com/Sam0urr/ribat"

HEADING_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*$")
NUMBER_RE = re.compile(r"^(\d+)(?:\.(\d+))?\.?\s+(.*)$")
RUNIN_RE = re.compile(r"^\*\*(\d+)\.(\d+)\s+(.+?)\*\*\s*(.*)$", re.S)
META_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$")
BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
SECTION_REF_RE = re.compile(r"§(\d+)(?:\.(\d+))?")


# ── block parsing ──────────────────────────────────────────────────────────

def starts_block(line: str) -> bool:
    s = line.rstrip()
    return (s.startswith("```") or HEADING_RE.match(s) is not None or s == "---"
            or s.startswith(">") or s.startswith("|") or BULLET_RE.match(s) is not None)


def parse(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.rstrip()
        if not s.strip():
            i += 1
            continue
        if s.startswith("```"):
            body = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence
            blocks.append({"t": "code", "text": "\n".join(body)})
            continue
        m = HEADING_RE.match(s)
        if m:
            blocks.append({"t": "h", "level": len(m.group(1)), "text": m.group(2)})
            i += 1
            continue
        if s == "---":
            blocks.append({"t": "hr"})
            i += 1
            continue
        if s.startswith(">"):
            body = []
            while i < n and lines[i].startswith(">"):
                body.append(lines[i][1:].strip())
                i += 1
            blocks.append({"t": "quote", "text": " ".join(body)})
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append({"t": "table", "rows": rows})
            continue
        if BULLET_RE.match(s):
            items: list[str] = []
            while i < n and lines[i].strip():
                m = BULLET_RE.match(lines[i])
                if m:
                    items.append(m.group(1).strip())
                elif items and lines[i].startswith(" "):
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            blocks.append({"t": "ul", "items": items})
            continue
        body = []
        while i < n and lines[i].strip() and not starts_block(lines[i]):
            body.append(lines[i].strip())
            i += 1
        metas = [META_RE.match(b) for b in body]
        if body and all(metas):
            blocks.append({"t": "meta", "items": [(m.group(1), m.group(2)) for m in metas]})
            continue
        para = " ".join(body)
        m = RUNIN_RE.match(para)
        if m:
            # "**5.1 Media vantage bias.** GPR is ..." - the full stop closes the
            # run-in in prose; as a heading and in the contents it is dropped.
            blocks.append({"t": "p", "runin": (f"{m.group(1)}.{m.group(2)}", m.group(3).rstrip(".")),
                           "text": m.group(4)})
        else:
            blocks.append({"t": "p", "text": para})
    return blocks


# ── anchors ────────────────────────────────────────────────────────────────

def section_id(num: str, sub: str | None) -> str:
    return f"s{num}" + (f"-{sub}" if sub else "")


def plain(md: str) -> str:
    return re.sub(r"[*`]", "", md)


def assign_ids(blocks: list[dict]) -> dict[str, str]:
    """Give every numbered heading and run-in an id; return {id: plain title}."""
    ids: dict[str, str] = {}
    for b in blocks:
        if b["t"] == "h" and b["level"] > 1:
            m = NUMBER_RE.match(b["text"])
            if m:
                b["num"] = m.group(1) + (f".{m.group(2)}" if m.group(2) else "")
                b["id"] = section_id(m.group(1), m.group(2))
                b["title"] = m.group(3)
            else:
                b["num"] = ""
                b["title"] = b["text"]
                b["id"] = re.sub(r"[^a-z0-9]+", "-", b["text"].lower()).strip("-")
            ids[b["id"]] = plain(b["title"])
        elif b["t"] == "p" and "runin" in b:
            num, title = b["runin"]
            major, minor = num.split(".")
            b["id"] = section_id(major, minor)
            ids[b["id"]] = plain(title)
    return ids


# ── inline rendering ───────────────────────────────────────────────────────

def link_urls(t: str) -> str:
    def repl(m: re.Match) -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in ".,;:)":
            tail = url[-1] + tail
            url = url[:-1]
        return f'<a href="{url}">{url}</a>{tail}'
    return URL_RE.sub(repl, t)


def link_sections(t: str, ids: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        target = section_id(m.group(1), m.group(2))
        return f'<a href="#{target}">{m.group(0)}</a>' if target in ids else m.group(0)
    return SECTION_REF_RE.sub(repl, t)


def prose(t: str, ids: dict[str, str]) -> str:
    t = html.escape(t, quote=False)
    t = link_urls(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    return link_sections(t, ids)


def inline(md: str, ids: dict[str, str]) -> str:
    # Code spans are stashed before any other inline rule runs, so a bold span
    # that wraps a code span ("**Why `covered_choke` is always empty.**") still
    # closes, and nothing inside backticks is ever emphasised or linked.
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, md)
    s = prose(s, ids)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


# ── page assembly ──────────────────────────────────────────────────────────

def render_blocks(blocks: list[dict], ids: dict[str, str]) -> str:
    out: list[str] = []
    for b in blocks:
        t = b["t"]
        if t == "h":
            if b["level"] == 1:
                continue  # the title is rendered in the hero
            tag = f"h{b['level']}"
            num = f'<span class="n">{b["num"]}</span>' if b["num"] else ""
            out.append(f'<{tag} id="{b["id"]}">{num}{inline(b["title"], ids)}</{tag}>')
        elif t == "meta":
            continue  # rendered in the hero
        elif t == "hr":
            out.append('<hr class="rule">')
        elif t == "code":
            out.append(f"<pre><code>{html.escape(b['text'], quote=False)}</code></pre>")
        elif t == "quote":
            out.append(f"<blockquote>{inline(b['text'], ids)}</blockquote>")
        elif t == "table":
            head, *body = b["rows"]
            th = "".join(f'<th scope="col">{inline(c, ids)}</th>' for c in head)
            tr = "".join("<tr>" + "".join(f"<td>{inline(c, ids)}</td>" for c in r) + "</tr>"
                         for r in body)
            out.append(f'<div class="tbl"><table><thead><tr>{th}</tr></thead>'
                       f"<tbody>{tr}</tbody></table></div>")
        elif t == "ul":
            out.append("<ul>" + "".join(f"<li>{inline(it, ids)}</li>" for it in b["items"]) + "</ul>")
        elif t == "p":
            if "runin" in b:
                num, title = b["runin"]
                out.append(f'<h3 class="runin" id="{b["id"]}"><span class="n">{num}</span>'
                           f"{inline(title, ids)}</h3>")
                out.append(f"<p>{inline(b['text'], ids)}</p>")
            else:
                out.append(f"<p>{inline(b['text'], ids)}</p>")
    return "\n".join(out)


def render_toc(blocks: list[dict]) -> str:
    entries: list[tuple[dict, list[dict]]] = []
    for b in blocks:
        if b["t"] == "h" and b["level"] == 2:
            entries.append((b, []))
        elif entries and ((b["t"] == "h" and b["level"] == 3) or (b["t"] == "p" and "runin" in b)):
            entries[-1][1].append(b)
    items = []
    for h, kids in entries:
        sub = ""
        if kids:
            li = []
            for k in kids:
                if k["t"] == "h":
                    num, title = k["num"], k["title"]
                else:
                    num, title = k["runin"]
                li.append(f'<li><a href="#{k["id"]}"><span class="n">{num}</span>'
                          f"<span>{html.escape(plain(title))}</span></a></li>")
            sub = "<ol>" + "".join(li) + "</ol>"
        num = f'<span class="n">{h["num"]}</span>' if h["num"] else ""
        items.append(f'<li><a href="#{h["id"]}">{num}<span>{html.escape(plain(h["title"]))}</span></a>{sub}</li>')
    return "<ol>" + "".join(items) + "</ol>"


CSS = """
:root{
  --ink:#070b12; --ink-2:#0c131f;
  --bone:#ece4d4; --bone-2:#b9b3a6; --muted:#767f8f;
  --blue:#6da7ec; --blue-mid:#3987e5; --blue-deep:#1c5cab;
  --amber:#d9a441;
  --line:rgba(236,228,212,.13); --line-2:rgba(236,228,212,.07);
  --display:'Fraunces',Georgia,'Times New Roman',serif;
  --sans:'IBM Plex Sans',ui-sans-serif,system-ui,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
  --gutter:clamp(20px,5vw,64px);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--ink);color:var(--bone-2);
  font-family:var(--sans);font-weight:300;line-height:1.68;font-size:16.5px;
  -webkit-font-smoothing:antialiased;overflow-x:hidden;
}
body::before{
  content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(120% 80% at 78% -10%, rgba(41,106,191,.16), transparent 60%),
    radial-gradient(90% 60% at 8% 105%, rgba(217,164,65,.07), transparent 62%),
    repeating-linear-gradient(0deg,var(--line-2) 0 1px,transparent 1px 88px),
    repeating-linear-gradient(90deg,var(--line-2) 0 1px,transparent 1px 88px);
}
main,header,footer{position:relative;z-index:2}

h1,h2,h3{font-family:var(--display);font-weight:400;color:var(--bone);
  letter-spacing:-.02em;font-variation-settings:'opsz' 96,'SOFT' 0,'WONK' 1}
a{color:var(--blue);text-underline-offset:3px;text-decoration-thickness:1px;
  overflow-wrap:anywhere}
a:hover{color:var(--bone)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--muted)}
.rule{height:1px;background:var(--line);border:0;margin:56px 0 0}

header{position:sticky;top:0;z-index:40;
  background:linear-gradient(180deg,rgba(7,11,18,.94),rgba(7,11,18,.72) 70%,transparent);
  backdrop-filter:blur(10px)}
nav{display:flex;align-items:center;gap:26px;padding:16px var(--gutter);
  border-bottom:1px solid var(--line-2)}
nav .mark{font-family:var(--display);font-size:19px;color:var(--bone);
  letter-spacing:.01em;font-variation-settings:'opsz' 40,'WONK' 1;text-decoration:none}
nav .mark span{color:var(--amber)}
nav .sp{flex:1}
nav a{font-family:var(--mono);font-size:11.5px;letter-spacing:.1em;
  text-transform:uppercase;text-decoration:none;color:var(--muted)}
nav a:hover,nav a[aria-current]{color:var(--bone)}

.hero{padding:clamp(56px,10vh,120px) var(--gutter) clamp(36px,6vh,64px);max-width:1220px}
.hero .eyebrow{display:block;margin-bottom:22px}
.hero h1{font-size:clamp(34px,5.6vw,76px);line-height:1;margin:0 0 26px;max-width:18ch;
  letter-spacing:-.035em;font-weight:300}
.hero h1 em{font-style:italic;color:var(--amber);font-weight:400}
.hero .lede{font-size:clamp(16px,1.8vw,19px);max-width:60ch;color:var(--bone-2);
  font-weight:300;line-height:1.6;margin:0}
.hero .lede strong{color:var(--bone);font-weight:500}
.meta{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;color:var(--muted);
  display:flex;flex-wrap:wrap;gap:8px 28px;margin-top:26px}
.meta b{color:var(--bone-2);font-weight:400}

.wrap{display:grid;grid-template-columns:250px minmax(0,1fr);gap:clamp(28px,5vw,80px);
  align-items:start;padding:0 var(--gutter) clamp(60px,10vh,120px);max-width:1220px}
.toc{position:sticky;top:84px;font-family:var(--mono);font-size:11.5px;
  letter-spacing:.03em;line-height:1.55;border-top:1px solid var(--line);padding-top:18px}
.toc .eyebrow{display:block;margin-bottom:14px}
.toc ol{list-style:none;margin:0;padding:0}
.toc li{margin:0 0 8px}
.toc ol ol{margin:8px 0 12px 0;padding-left:0}
.toc ol ol li{margin:0 0 5px}
.toc a{color:var(--muted);text-decoration:none;display:flex;gap:10px}
.toc a:hover{color:var(--bone)}
.toc .n{color:var(--amber);flex:0 0 2.6em}
.toc ol ol .n{color:var(--muted)}

article{max-width:70ch;min-width:0}
article h2{font-size:clamp(26px,3.6vw,42px);line-height:1.06;margin:28px 0 22px;
  letter-spacing:-.03em;font-weight:300;scroll-margin-top:92px}
article h3{font-size:clamp(20px,2.3vw,25px);line-height:1.2;margin:46px 0 14px;
  letter-spacing:-.015em;scroll-margin-top:92px}
article h3.runin{font-size:clamp(19px,2.1vw,23px);margin-top:40px}
article .n{font-family:var(--mono);font-size:.5em;color:var(--amber);letter-spacing:.12em;
  vertical-align:middle;margin-right:14px;font-variation-settings:normal}
article h3 .n{font-size:.62em}
article p{margin:0 0 18px}
article strong{color:var(--bone);font-weight:500}
article em{color:var(--bone)}
article ul{padding-left:20px;margin:0 0 18px}
article li{margin:0 0 10px;padding-left:4px}
article blockquote{border-left:2px solid var(--amber);margin:0 0 18px;padding:4px 0 4px 18px;
  color:var(--bone-2)}
code{font-family:var(--mono);font-size:.86em;color:var(--bone);
  background:rgba(236,228,212,.06);padding:.08em .35em;border-radius:2px}
pre{font-family:var(--mono);font-size:13px;line-height:1.65;color:var(--bone);
  background:linear-gradient(180deg,var(--ink-2),rgba(12,19,31,.4));
  border:1px solid var(--line);border-radius:3px;padding:16px 18px;overflow-x:auto;
  margin:6px 0 22px}
pre code{background:none;padding:0;font-size:inherit;color:inherit}
.tbl{overflow-x:auto;margin:6px 0 24px}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;vertical-align:top;padding:9px 14px 9px 0;
  border-bottom:1px solid var(--line-2)}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:400;border-bottom:1px solid var(--line)}
td:first-child{white-space:nowrap}

.cta{display:inline-flex;align-items:center;gap:14px;margin-top:30px;
  font-family:var(--mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  text-decoration:none;color:var(--ink);background:var(--bone);
  padding:15px 26px;border-radius:2px;transition:transform .3s,background .3s}
.cta:hover{background:var(--amber);color:var(--ink);transform:translateX(5px)}
footer{border-top:1px solid var(--line);padding:36px var(--gutter) 72px;
  font-size:12.5px;color:var(--muted);line-height:1.75}
footer p{max-width:76ch;margin:0 0 10px}
footer a{color:var(--bone-2)}

@media (max-width:900px){
  .wrap{grid-template-columns:1fr;gap:0}
  .toc{position:static;border:1px solid var(--line);padding:16px 18px;margin-bottom:28px}
  .hero h1{max-width:none}
  td:first-child{white-space:normal}
}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{
  body{background:#fff;color:#222;font-size:11pt}
  body::before{display:none}
  header,.toc,.cta{display:none}
  .wrap{display:block;padding:0}
  h1,h2,h3,article strong,article em,code,pre{color:#000}
  .hero h1 em,article .n,.toc .n{color:#000}
  pre{background:#f4f2ec;border-color:#bbb}
  code{background:#f4f2ec}
  a{color:#000}
  th,td{border-color:#ccc}
  th{color:#444}
  footer{color:#444}
}
"""


def build(md: str) -> str:
    blocks = parse(md)
    ids = assign_ids(blocks)
    title = next((b["text"] for b in blocks if b["t"] == "h" and b["level"] == 1), "Methodology")
    meta = next((b["items"] for b in blocks if b["t"] == "meta"), [])
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()

    # "Methodology — Ribat Intensity Index": the part after the dash is the
    # subject and takes the italic; the document's own title is the h1.
    if " — " in title:
        head, sub = title.split(" — ", 1)
        h1 = f"{html.escape(head)} <em>{html.escape(sub)}</em>"
    else:
        h1 = html.escape(title)
    meta_html = "".join(f"<span><b>{html.escape(k)}</b> {inline(v, ids)}</span>" for k, v in meta)
    status = next((v for k, v in meta if k.lower() == "status"), "")
    description = ("How the Ribat Intensity index is built: the definition, the four "
                   "dependency channels, the normalisation choice, the known limitations "
                   "and the export contract. Rendered from the repository's METHODOLOGY.md.")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ribat · method</title>
<meta name="description" content="{html.escape(description)}">
<meta property="og:title" content="Ribat · method">
<meta property="og:description" content="{html.escape(description)}">
<meta name="ribat-source" content="METHODOLOGY.md">
<meta name="ribat-source-sha256" content="{sha}">
<link href="./vendor/fonts.css" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>

<header>
  <nav>
    <a class="mark" href="./index.html">Ribat<span>.</span></a>
    <span class="sp"></span>
    <a href="./index.html">The map</a>
    <a href="./story.html">The story</a>
    <a href="./method.html" aria-current="page">Method</a>
    <a href="{REPO}">Source</a>
    <a href="{REPO}/issues/new/choose">Ask</a>
  </nav>
</header>

<main>

  <section class="hero">
    <span class="eyebrow">Ribāṭ · the contract the pipeline is held to</span>
    <h1>{h1}</h1>
    <p class="lede">This page is the typeset copy of
      <a href="{REPO}/blob/main/METHODOLOGY.md"><code>METHODOLOGY.md</code></a>,
      the document every pipeline stage and every panel of the map is checked
      against. It is <strong>rendered from that file, not written separately</strong>;
      the repository's verifier fails if the two diverge. Section references (§)
      link to their targets. A question about a particular section can be raised
      through the <a href="{REPO}/issues/new?template=methodology-question.yml">methodology
      issue form</a>.</p>
    <div class="meta">{meta_html}</div>
  </section>

  <div class="wrap">
    <aside class="toc" aria-label="Contents">
      <span class="eyebrow">Contents</span>
      {render_toc(blocks)}
    </aside>
    <article>
{render_blocks(blocks, ids)}
      <a class="cta" href="./index.html">Open the map →</a>
    </article>
  </div>

</main>

<footer>
  <p><strong style="color:var(--bone-2)">Risk data</strong>: Caldara, D. &amp;
    Iacoviello, M. (2022), “Measuring Geopolitical Risk”, <em>American Economic
    Review</em> 112(4), 1194–1225. CC BY.
    <strong style="color:var(--bone-2)">Dependency weights</strong>: UN Comtrade
    via World Bank WITS; OECD TiVA.
    <strong style="color:var(--bone-2)">Boundaries</strong>: Natural Earth,
    public domain.</p>
  <p>Generated by <code>pipeline/05_render_method.py</code> from
    <code>METHODOLOGY.md</code> ({html.escape(status) if status else "current revision"};
    source sha256 <code>{sha[:12]}</code>). The text is licensed CC BY 4.0; the code is MIT.
    Bug reports, data requests and methodology questions:
    <a href="{REPO}/issues/new/choose">open an issue</a>.
    <a href="{REPO}">Source, methodology and replication files</a>.</p>
</footer>
</body>
</html>
"""


def main() -> int:
    md = SRC.read_text(encoding="utf-8")
    page = build(md)
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != page:
            print(f"{OUT.relative_to(ROOT)} is stale: re-run {Path(__file__).name}")
            return 1
        print(f"{OUT.relative_to(ROOT)} is current")
        return 0
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page):,} chars) from {SRC.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
