#!/usr/bin/env python3
"""Ribat pre-commit verification. Deterministic; no network. Exit 0 = pass."""
from __future__ import annotations

import csv
import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FAIL: list[str] = []
WARN: list[str] = []

KNOWN_KINDS = {"gpr_source_side", "intensity_trade", "intensity_multi", "bilateral_weights",
               "validation_summary"}
EXPECTED_GPR_SOURCES = 44
MIN_EXPOSED = 40
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ISO_RE = re.compile(r"^[A-Z]{3}$")


def check(ok: bool, msg: str) -> None:
    (FAIL, WARN)[0].append(msg) if not ok else None
    print(("  ok   " if ok else "  FAIL ") + msg)


def section(name: str) -> None:
    print(f"\n[{name}]")


def main() -> int:
    # 1 ── Python compiles ---------------------------------------------------
    section("python")
    for py in sorted((ROOT / "pipeline").glob("*.py")):
        try:
            py_compile.compile(str(py), doraise=True)
            check(True, py.name)
        except py_compile.PyCompileError as e:
            check(False, f"{py.name}: {e.msg.splitlines()[0]}")

    # 2 ── inline JS ---------------------------------------------------------
    section("javascript")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    # Both pages carry their logic inline. The story page's script is what
    # fills the T1/T2/T4 figures from validation.json; a syntax slip there
    # would leave every card on its typed fallback without anything failing,
    # so it is checked exactly as the map page is.
    for page in ("index.html", "story.html"):
        page_html = (ROOT / "web" / page).read_text(encoding="utf-8")
        blocks = re.findall(r"<script>(.*?)</script>", page_html, re.S)
        if not blocks:
            check(False, f"no inline <script> block found in web/{page}")
        elif shutil.which("node") is None:
            WARN.append("node not available - JS syntax not checked")
            print("  warn node not available - skipped")
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(blocks[-1])
            r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
            check(r.returncode == 0, f"web/{page}: inline script node --check"
                  + ("" if r.returncode == 0 else f": {r.stderr.strip().splitlines()[0]}"))

    # 3 ── payload contracts -------------------------------------------------
    EXPOSED_SEEN: set[str] = set()
    section("payloads")
    for p in sorted((ROOT / "web" / "data").glob("*.json")):
        if "countries-50m" in p.name:
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        kind = d.get("kind")
        check(kind in KNOWN_KINDS, f"{p.name}: kind={kind!r} recognised")

        # The bilateral weight matrix has no month grid: weights are per
        # benchmark vintage, and the month dimension arrives from gpr.json at
        # render time. Check what it actually claims instead.
        if kind == "bilateral_weights":
            srcs = d.get("sources") or []
            check(bool(srcs) and all(ISO_RE.match(x) for x in srcs),
                  f"{p.name}: {len(srcs)} source ISO3 codes")
            check(bool(d.get("years")) and all(isinstance(y, int) for y in d["years"]),
                  f"{p.name}: benchmark years are integers {d.get('years')}")
            check("choke" not in (d.get("channels") or []),
                  f"{p.name}: chokepoint absent (no bilateral source attribution)")
            bad_idx = bad_w = bad_iso = 0
            for iso, per_ch in (d.get("w") or {}).items():
                if not ISO_RE.match(iso):
                    bad_iso += 1
                for ch, per_yr in per_ch.items():
                    if ch not in (d.get("channels") or []):
                        bad_iso += 1
                    for pairs in per_yr.values():
                        for pair in pairs:
                            if not (isinstance(pair, list) and len(pair) == 2
                                    and 0 <= pair[0] < len(srcs)):
                                bad_idx += 1
                            elif not (0 < float(pair[1]) <= 1.0):
                                bad_w += 1
            # The payload is keyed by the TARGET vintage a month resolves to, not
            # by the year the underlying source published. Keying it by the raw
            # benchmark year shipped a "2022" block for the value-added channel
            # and no "2023" at all, so a client following weight_year_for found
            # nothing for every month from 2024 on. A missing block is silent -
            # the attribution simply comes back short - so it is checked here.
            want_years = {str(y) for y in (d.get("years") or [])}
            gaps = [f"{iso}/{ch}" for iso, per_ch in (d.get("w") or {}).items()
                    for ch, per_yr in per_ch.items() if want_years - set(per_yr)]
            check(not gaps,
                  f"{p.name}: every exposed x channel carries all {len(want_years)} vintages"
                  + ("" if not gaps else " -> missing in " + ", ".join(sorted(gaps)[:5])))
            check(bad_idx == 0, f"{p.name}: every source index is in range")
            check(bad_w == 0, f"{p.name}: every weight lies in (0, 1]")
            check(bad_iso == 0, f"{p.name}: ISO3 keys and declared channels only")
            if EXPOSED_SEEN:
                missing = EXPOSED_SEEN - set(d.get("w") or {})
                check(not missing,
                      f"{p.name}: covers every exposed economy in intensity.json"
                      + ("" if not missing else " -> missing " + ", ".join(sorted(missing)[:5])))
            continue

        # The validation summary has no month grid either: it is the handful of
        # report figures story.html reads at load. Its shape is checked here;
        # its numbers are checked against the report in the methods-review
        # section below.
        if kind == "validation_summary":
            check(all(isinstance(d.get(k), dict) for k in ("t1", "t2", "t4", "anachronistic"))
                  and bool(MONTH_RE.match(str(d.get("months_through")))),
                  f"{p.name}: carries t1, t2, t4, anachronistic and months_through")
            continue

        months = d.get("months", [])
        check(bool(months) and all(MONTH_RE.match(m) for m in months),
              f"{p.name}: months are YYYY-MM ({len(months)})")
        check(months == sorted(months) and len(set(months)) == len(months),
              f"{p.name}: months strictly increasing")
        n = len(months)
        channels = d.get("channels")  # intensity_multi: series/covered keyed by channel
        bad_len = bad_val = bad_chan = 0

        def series_ok(seq) -> tuple[bool, bool]:
            """(right length, values numeric-or-null)"""
            return (len(seq) == n,
                    all(v is None or isinstance(v, (int, float)) for v in seq))

        for iso, rec in d.get("countries", {}).items():
            if not ISO_RE.match(iso):
                bad_val += 1
            for key in ("level", "rebased"):
                node = rec.get(key)
                if node is None:
                    continue
                if isinstance(node, dict):          # per-channel form
                    if channels and set(node) - set(channels):
                        bad_chan += 1
                    seqs = node.values()
                else:                                # flat form
                    seqs = [node]
                for seq in seqs:
                    ok_len, ok_val = series_ok(seq)
                    bad_len += not ok_len
                    bad_val += not ok_val
            cov = rec.get("covered")
            covs = cov.values() if isinstance(cov, dict) else (
                [] if cov is None else [cov])
            if any(not (0.0 <= float(c) <= 1.0) for c in covs):
                bad_val += 1
        check(bad_len == 0, f"{p.name}: all series match month grid")
        check(bad_val == 0, f"{p.name}: values numeric/null, ISO3 keys, covered in [0,1]")
        if channels is not None:
            check(bad_chan == 0, f"{p.name}: series channels within declared {channels}")
        for iso in (d.get("stale_weights") or {}):
            check(iso in d.get("countries", {}),
                  f"{p.name}: stale_weights[{iso}] refers to a present economy")

        # 4 ── coverage counts (attached to the right payload) --------------
        if kind == "gpr_source_side":
            check(len(d["countries"]) == EXPECTED_GPR_SOURCES,
                  f"{p.name}: {len(d['countries'])} GPR source series (expect {EXPECTED_GPR_SOURCES})")
        elif kind and kind.startswith("intensity"):
            EXPOSED_SEEN.update(d.get("countries", {}))
            check(len(d["countries"]) >= MIN_EXPOSED,
                  f"{p.name}: {len(d['countries'])} exposed economies (expect >= {MIN_EXPOSED})")

    # 5 ── banned tokens -----------------------------------------------------
    section("banned tokens")
    banned = [
        (re.compile(r"\bGRE\b"), "GRE (old index name)"),
        (re.compile(r"gre\.json|gre_monthly|03_build_gre"), "gre-era filename"),
        (re.compile(r"api\.mapbox\.com|mapbox-gl(?!-)"), "Mapbox GL dependency"),
    ]
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True).stdout.split()
    # Scope is deliberately .py/.md/.html/.yml/.json/.csv and not .js or .css:
    # the vendored MapLibre build under web/vendor/ is a faithful fork of
    # Mapbox GL and legitimately mentions mapbox:// URL handling and the
    # upstream issue tracker, so scanning it would flag the fork for being a
    # fork. The pages themselves (.html) are scanned, which is where a Mapbox
    # GL tag would reappear; the vendored-assets section below pins the
    # library bytes by hash instead.
    scan = [t for t in tracked if t.endswith((".py", ".md", ".html", ".yml", ".json", ".csv"))
            and not t.startswith("web/data/countries-50m")
            # the verifier, its doc, and CLAUDE.md define/prohibit the banned
            # tokens by name; scanning them is self-reference, not regression
            and not t.startswith(".claude/skills/ribat-verify/")
            and t != "CLAUDE.md"]
    hits = []
    for t in scan:
        try:
            text = (ROOT / t).read_text(encoding="utf-8")
        except Exception:
            continue
        for rx, label in banned:
            if rx.search(text):
                hits.append(f"{t}: {label}")
    check(not hits, "no banned tokens in tracked source"
          + ("" if not hits else " -> " + "; ".join(hits[:5])))

    # 6 ── licence -----------------------------------------------------------
    section("licence")
    for fname in ("LICENSE", "SOURCES.md"):
        f = ROOT / fname
        ok = f.exists() and "Caldara" in f.read_text(encoding="utf-8")
        check(ok, f"{fname} present with Caldara-Iacoviello attribution")

    # 6b ── vendored assets --------------------------------------------------
    # Invariant 1 promises zero third-party requests at runtime. That holds
    # only while every library and font file the pages load is served from
    # web/vendor/ and is the file MANIFEST.json says it is, so the manifest is
    # checked byte-for-byte here and both pages are scanned for anything that
    # would leave the origin. A hash mismatch is a silent upgrade (or a
    # tampered file), not noise: fix the manifest entry deliberately.
    section("vendored assets")
    vendor = ROOT / "web" / "vendor"
    manifest_path = vendor / "MANIFEST.json"
    listed: set[str] = set()
    licence_files: set[str] = set()
    if not manifest_path.exists():
        check(False, "web/vendor/MANIFEST.json exists")
    else:
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
        except Exception as e:  # malformed manifest is a failure, not a crash
            entries = []
            check(False, f"web/vendor/MANIFEST.json parses and carries 'files': {e}")
        check(bool(entries), "MANIFEST.json lists at least one file")
        for entry in entries:
            rel = str(entry.get("path", ""))
            listed.add(rel)
            missing = [k for k in ("path", "source_url", "version", "bytes", "sha256",
                                   "licence", "fetched") if k not in entry]
            if missing:
                check(False, f"{rel}: manifest entry lacks {', '.join(missing)}")
            f = ROOT / rel
            if not rel.startswith("web/vendor/") or not f.is_file():
                check(False, f"{rel}: listed in manifest but not a file under web/vendor/")
                continue
            data = f.read_bytes()
            ok = len(data) == entry.get("bytes") and \
                hashlib.sha256(data).hexdigest() == entry.get("sha256")
            check(ok, f"{rel}: {len(data)} bytes, sha256 "
                      + ("matches manifest" if ok else "or byte count differs from manifest"))
            lf = entry.get("licence_file")
            licence_files.update([lf] if isinstance(lf, str) else (lf or []))
        # (d) every licence file the manifest names is actually shipped
        check(bool(licence_files), "manifest names the licence file of each package")
        for lf in sorted(licence_files):
            check((ROOT / lf).is_file(), f"licence file {lf} present")
        # (c) nothing under web/vendor/ escapes the manifest (the manifest
        # cannot hash itself and is the one exemption)
        on_disk = {p.relative_to(ROOT).as_posix() for p in vendor.rglob("*")
                   if p.is_file() and p.name not in ("MANIFEST.json", ".DS_Store")}
        stray = sorted(on_disk - listed)
        check(not stray, "every file under web/vendor/ is listed in MANIFEST.json"
              + ("" if not stray else " -> " + ", ".join(stray[:5])))
    # (b) neither page reaches a third party: tags, preconnects, CSS imports,
    # url() and fetch() must all be same-origin. data: URIs are not requests.
    leak = [
        (re.compile(r"<script[^>]*\ssrc\s*=\s*[\"']?\s*https?://", re.I), "script src"),
        (re.compile(r"<link[^>]*\shref\s*=\s*[\"']?\s*https?://", re.I), "link href"),
        (re.compile(r"<link[^>]*\srel\s*=\s*[\"']?\s*(preconnect|dns-prefetch)", re.I), "preconnect"),
        (re.compile(r"@import\s+(url\()?\s*[\"']?\s*https?://", re.I), "@import"),
        (re.compile(r"url\(\s*[\"']?\s*https?://", re.I), "url()"),
        (re.compile(r"fetch\(\s*[\"'`]https?://"), "fetch()"),
    ]
    for page in ("index.html", "story.html"):
        text = (ROOT / "web" / page).read_text(encoding="utf-8")
        found = [label for rx, label in leak if rx.search(text)]
        check(not found, f"web/{page}: no third-party script, stylesheet, preconnect, "
                         "@import, url() or fetch()"
              + ("" if not found else " -> " + ", ".join(found)))

    # 7 ── export contract ---------------------------------------------------
    # A downloaded CSV leaves the interface and loses every caveat the panels
    # carry, so the header block is the only thing standing between the file
    # and a misreading. These checks fail the build if it is stripped.
    section("export contract")
    idx = ROOT / "web" / "index.html"
    html = idx.read_text(encoding="utf-8") if idx.exists() else ""
    check("function toCSV(" in html and "URL.createObjectURL" in html,
          "index.html: export machinery present")
    check("Caldara" in html and "CC-BY" in html.split("const CITATION")[-1][:400],
          "export header carries the Caldara-Iacoviello CC-BY citation")
    for key in ("downloaded", "normalisation", "channel_mix", "coverage", "caution"):
        check(f"['{key}'," in html, f"export header declares '{key}'")
    for ch in ("trade", "va", "energy", "crm", "choke"):
        check(f"'{ch}'" in html.split("EXPORT_CHANNELS = [")[-1][:80],
              f"export columns cover channel '{ch}'")
    check("covered_choke is intentionally empty" in html,
          "export header explains why chokepoint coverage is blank")

    # A chart leaves with no stylesheet and no sibling markup, so the figure has
    # to carry its own colours, key, caption and attribution or it travels as an
    # unsourced picture.
    check("function chartFigure(" in html and "image/svg+xml" in html,
          "index.html: chart SVG export present")
    check('xmlns="http://www.w3.org/2000/svg"' in html,
          "chart export emits a standalone SVG namespace")
    check("replace(/var\\(--([a-z]+)\\)/g" in html,
          "chart export resolves CSS custom properties to literals")
    check("body += t(PAD, y, CITATION" in html or "wrapText(CITATION" in html,
          "chart export burns in the Caldara-Iacoviello citation")
    check("not a forecast" in html,
          "chart export burns in the not-a-forecast caution")

    check("function toGeoJSON(" in html and "application/geo+json" in html,
          "index.html: GeoJSON export present")
    check("props.attribution = CITATION" in html,
          "GeoJSON repeats attribution per feature (foreign members may be dropped)")
    check("byIso" in html and "MultiPolygon" in html,
          "GeoJSON merges multi-feature economies into one feature each")

    # data/processed/ is gitignored and the refresh runs in CI, so a working tree
    # can rebuild a shorter payload from older inputs without saying so.
    # The reverse map inverts the question: not what an economy bears, but which
    # economies produce a selected country's exposure. Its whole risk is quiet
    # incompleteness - the chokepoint channel has no source country, so an
    # attribution that does not say so reads as though it accounts for
    # everything. Every surface that shows it must disclose the residual.
    section("reverse map (source attribution)")
    check("function attribution(" in html and "SHARE_BREAKS" in html,
          "index.html: source attribution present")
    check("'./data/weights.json'" in html and "'./data/gpr.json'" in html,
          "reverse payloads are fetched by the page")
    check("function loadReverse(" in html and "reverseReady()" in html,
          "reverse payloads load on demand, not at page load")
    check("different month grids" in html,
          "refuses to attribute when gpr.json and intensity.json disagree on months")
    check("['choke', th.choke]" in html.replace('"', "'"),
          "denominator includes chokepoint, so shares reconcile with Intensity")
    rev = html.split("function detailSources(")[-1].split("\nfunction ")[0]
    check("residualShare" in rev and "unattributable" in rev,
          "panel discloses the unattributable chokepoint share")
    check("chokepoint transit" in html.lower(),
          "screen-reader table names the unattributable row")
    check("row_type" in html and "'unattributed'" in html,
          "export carries the residual as a labelled row, not a silent shortfall")
    check("unattributed_choke_share" in html,
          "export metadata states the unattributed share")
    check("attrPng" in html.split("function exportMapPNG(")[-1].split("\nfunction ")[0],
          "PNG says whose sources it shows and what it leaves out")
    check('id="btnSources"' in html and 'id="btnExposure"' in html,
          "map view toggle present")
    check('id="dlSources"' in html,
          "source attribution is downloadable")

    # The Sankey's whole claim is the middle column: without it the picture is a
    # ranked bar chart with curves on it. And its honesty rests on one scale
    # across both columns, so the source column ends short by exactly the
    # unattributable share - drop that and the diagram silently asserts the
    # attribution is complete.
    check("function sankeySVG(" in html, "index.html: source-routing Sankey present")
    check(">SOURCE<" in html and ">CHANNEL<" in html,
          "Sankey keeps its middle column (source -> channel -> economy)")
    check("no source country" in html,
          "chokepoint band is marked as having no inflow")
    check("short of the channel column" in html,
          "caption explains the column shortfall as the unattributable share")
    check('data-chart="sankey"' in html and "'routing'" in html,
          "Sankey exports as its own figure")
    # The arithmetic lives in sankeyRender since the panel and the expanded view
    # were split into two frames over one model. Both frames must still share one
    # scale AND one gap budget: unequal gap spending between the columns fakes the
    # shortfall just as effectively as an unequal scale, and at 43 source nodes it
    # would have swallowed the residual entirely.
    check("function sankeyModel(" in html and "function sankeyRender(" in html,
          "Sankey model and render are separable, so both frames share one arithmetic")
    sk = html.split("function sankeyRender(")[-1].split("\nfunction ")[0]
    check("a.total" in sk and "scale" in sk,
          "both columns share one scale, so the shortfall is to scale")
    check("budget" in sk and "srcGap" in sk,
          "both columns share one gap budget, so the shortfall is not gap artefact")

    # Expanded view. The un-pooled frame is the only place a reader can inspect
    # the pooled tail, and it must carry the same disclosures as the panel.
    check('id="sankeyModal"' in html and 'aria-modal="true"' in html,
          "expanded routing view is a real dialog")
    check("function closeModal(" in html and "'Escape'" in html,
          "expanded view closes on Escape")

    # The expanded source table opens the pooled tail the panel can only assert.
    # One dialog serves both it and the Sankey: a second would mean a second
    # focus trap and a second Escape handler racing the first.
    check("function openSourcesModal(" in html and "function openSankeyModal(" in html
          and "function openModal(" in html,
          "one dialog shell serves both expanded views")
    check('id="sourcesPanel"' in html and "sourcesTableHTML(" in html,
          "source-country list expands to a full-window table")
    check("<th class=\"nm\" scope=\"row\"" in html and 'scope="col"' in html,
          "expanded source list is a real table with row and column headers")
    check("Chokepoint, unattributable" in html and "tfoot" in html,
          "expanded source table foots to attributed + chokepoint")
    check("sankeyPct(r.share * 100)" in html,
          "source shares use adaptive precision, so the ranked column still sums")
    check("SANKEY_GEOM" in html and "pool: 0" in html,
          "expanded view un-pools: every source country is drawn individually")
    check("skReturnFocus" in html, "expanded view restores focus on close")
    check("short of the channel column: chokepoint transit weights a strait" in html,
          "expanded view brackets and numbers the chokepoint shortfall, not just the panel")
    check('data-root="modal"' in html and "chartFigure(which, where)" in html,
          "SVG download works from the expanded view as well as the panel")
    check("sankeyBandText" in html and "aria-label" in html,
          "bands carry the tooltip text as an aria-label, so hover and screen reader agree")
    check("sankeyTipHTML" in html and "getAttribute('aria-label')" in html,
          "the tooltip renders the aria-label itself rather than a parallel string")
    check('tabindex="0"' in html and "sk-band" in html,
          "bands and nodes are focusable")
    check("sk-hl" in html and "opacity" in html and "sk-lit" in html,
          "dim/lit state is opacity only, no second palette (invariant 5)")

    # Provenance rots when it is typed by hand, and this repository has already
    # shipped a payload note that was wrong about its own contents. The README
    # block is generated; this fails if it has drifted from the payload it
    # claims to describe, which is the only thing that makes it worth trusting.
    section("provenance")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    gpr_p = ROOT / "web" / "data" / "gpr.json"
    have_block = "<!-- PROVENANCE:START -->" in readme and "<!-- PROVENANCE:END -->" in readme
    check(have_block, "README carries a generated provenance block")
    if have_block and gpr_p.exists():
        g = json.loads(gpr_p.read_text(encoding="utf-8"))
        blk = readme.split("<!-- PROVENANCE:START -->")[1].split("<!-- PROVENANCE:END -->")[0]
        digest = hashlib.sha256(json.dumps(
            {"m": g["months"], "c": g["countries"]}, sort_keys=True).encode()).hexdigest()
        check(digest in blk,
              "README series digest matches web/data/gpr.json")
        check(g["months"][-1] in blk,
              f"README states the published data month ({g['months'][-1]})")
        wb = g.get("workbook_sha256")
        check(wb in blk if wb else "not recorded" in blk,
              "README states the workbook digest, or says it is not recorded")
        check("do not edit by hand" in blk,
              "block says it is generated, so nobody hand-edits it into a lie")

    section("pipeline guards")
    p3 = (ROOT / "pipeline" / "03_build_intensity.py")
    src3 = p3.read_text(encoding="utf-8") if p3.exists() else ""
    check("def guard_no_regression(" in src3,
          "03 refuses to overwrite a richer payload with a poorer one")
    check("--allow-regression" in src3,
          "03 offers an explicit override for intended shrinkage")
    check("sys.exit(1)" in src3,
          "03 exits non-zero when it refuses, so CI cannot ignore it")
    # 01 publishes web/data/gpr.json, which the site reads directly, so a stale
    # workbook in data/raw can cost it a month exactly as it could for 03.
    p1 = (ROOT / "pipeline" / "01_load_gpr.py")
    src1 = p1.read_text(encoding="utf-8") if p1.exists() else ""
    check("REFUSING to overwrite" in src1 and "sys.exit(1)" in src1,
          "01 refuses to publish a shorter gpr.json than the one on disk")
    check("--allow-regression" in src1,
          "01 offers an explicit override for intended shrinkage")
    check("--stamp-only" in src1,
          "01 can restamp provenance without a workbook, which clones lack")

    section("export contract (map)")
    # The v4 spelling passes this file's eye but not MapLibre's: v5 ignores a
    # top-level preserveDrawingBuffer silently. Require the nested form, which is
    # the one that actually reaches the GL context.
    check("canvasContextAttributes" in html and "preserveDrawingBuffer: true" in html,
          "map back buffer is readable via canvasContextAttributes (PNG export)")
    # Match the assignment, not the word: the comment above it necessarily
    # mentions the top-level spelling in order to warn about it.
    assigns = [ln for ln in html.splitlines() if "preserveDrawingBuffer:" in ln]
    check(bool(assigns) and all("canvasContextAttributes" in ln for ln in assigns),
          "preserveDrawingBuffer is only set inside canvasContextAttributes, "
          "not at the top level where v5 ignores it")
    check("function exportMapPNG(" in html and "'image/png'" in html,
          "index.html: map PNG export present")
    # Scope to the function body, not a fixed character window: the window was
    # 3000 chars and adding one sentence to the footer caution pushed the tick
    # copy past it, failing a check about code that had not changed.
    png_body = html.split("function exportMapPNG(")[-1].split("\nfunction ")[0]
    check("#ticks span" in png_body,
          "PNG footer copies the legend's real break values")
    check("CITATION" in png_body,
          "PNG footer carries the citation")

    section("map coverage")
    # The render loop skips features MapLibre cannot key state by. That skip is
    # silent by construction, so a payload economy whose geometry lost its id
    # would simply stop being coloured without anything raising. These checks
    # are what make the skip safe to keep: they fail if the map ever stops
    # being able to paint something the data can colour.
    topo = json.loads((ROOT / "web" / "data" / "countries-50m.json")
                      .read_text(encoding="utf-8"))
    geoms = topo["objects"]["countries"]["geometries"]
    table = html.split("const NUM_TO_A3 =")[-1].split("};")[0]
    num_to_a3 = {int(n): a3 for n, a3 in re.findall(r"(\d+)\s*:\s*'([A-Z]{3})'", table)}
    check(bool(num_to_a3), f"NUM_TO_A3 parsed from index.html ({len(num_to_a3)} entries)")

    # Natural Earth zero-pads its numeric ids ("032"), so the lookup must pass
    # through int() exactly as the page passes through Number(f.id). Comparing
    # the padded string against the table would match nothing and report every
    # country unreachable.
    paintable = {num_to_a3[int(g["id"])] for g in geoms
                 if g.get("id") is not None and int(g["id"]) in num_to_a3}

    payload: set[str] = set()
    for fname, key in (("gpr.json", "countries"), ("intensity.json", "countries"),
                       ("weights.json", "w")):
        f = ROOT / "web" / "data" / fname
        if f.exists():
            payload |= set(json.loads(f.read_text(encoding="utf-8")).get(key) or {})
    orphans = sorted(payload - paintable)
    check(not orphans,
          f"every payload economy reaches a paintable feature ({len(payload)} checked)"
          + ("" if not orphans else " -> unreachable: " + ", ".join(orphans[:5])))

    # An entry no feature id matches is a mistyped or retired code. It colours
    # nothing, and nothing else in this file would report it.
    dead = sorted(set(num_to_a3.values()) - paintable)
    check(not dead, "no NUM_TO_A3 entry is unmatched by a feature id"
          + ("" if not dead else " -> " + ", ".join(dead[:5])))

    # Guards the guard: without it setFeatureState is handed an undefined id and
    # MapLibre answers with an ErrorEvent for each such feature on every repaint.
    check("if (f.id == null) continue;" in html,
          "render loop skips id-less features instead of calling setFeatureState "
          "on them")

    # ── methods review: payload fields, coverage toggle, anachronism flag ----
    # The review found three things the interface could not say: that a channel
    # value scales with its covered share (a ranking confound under percentile
    # colouring), that 84% of the slider runs on a benchmark that postdates it,
    # and that the chokepoint channel fed an economy's own GPR back through its
    # own strait. Each fix has a payload field, an interface surface and a
    # METHODOLOGY section; these checks fail if any of the three goes missing
    # or if the documented numbers drift from the committed validation report.
    section("methods review contract")
    CHOKEPOINTS = {"red_sea", "hormuz", "malacca", "taiwan_strait", "bosphorus", "danish_straits"}
    ip = ROOT / "web" / "data" / "intensity.json"
    d = json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else {}
    if d.get("kind") == "intensity_multi":
        months = d.get("months") or []
        econ = set(d.get("countries") or {})
        through = d.get("weights_anachronistic_through")
        check(isinstance(through, str) and bool(MONTH_RE.match(through))
              and bool(months) and through <= months[-1],
              f"intensity.json: weights_anachronistic_through is YYYY-MM and <= last month ({through!r})")
        # Derived, never typed in: the last month with no benchmark strictly
        # before its year, which is the fallback branch of weight_year_for.
        ys = d.get("weight_years") or []
        if ys and months:
            exp = max((m for m in months if not any(int(y) < int(m[:4]) for y in ys)), default=None)
            check(exp == through,
                  f"intensity.json: weights_anachronistic_through matches the vintage rule on "
                  f"weight_years {ys} (rule -> {exp})")
        lit = d.get("choke_littorals")
        check(isinstance(lit, dict) and set(lit) == CHOKEPOINTS
              and all(isinstance(v, list) and v and all(ISO_RE.match(x) for x in v)
                      for v in lit.values()),
              "intensity.json: choke_littorals keys are the six chokepoints, values ISO3 lists")
        gp = ROOT / "web" / "data" / "gpr.json"
        srcs: set[str] = set()
        if isinstance(lit, dict) and gp.exists():
            srcs = set(json.loads(gp.read_text(encoding="utf-8")).get("countries") or {})
            stray = sorted({x for v in lit.values() for x in v} - srcs)
            check(not stray, "intensity.json: every littoral has a GPR series"
                  + ("" if not stray else " -> " + ", ".join(stray)))
        excl = d.get("choke_self_excluded")
        check(isinstance(excl, dict) and set(excl) <= econ
              and all(isinstance(v, list) and v and set(v) <= CHOKEPOINTS for v in excl.values()),
              "intensity.json: choke_self_excluded keys are present economies, values chokepoint ids")
        # Both fields are recomputed from the tracked inputs, not from each
        # other: 03 emits choke_littorals and choke_self_excluded from one
        # littoral dict, so checking the pairs against the payload's own table
        # would pass a mis-filtered table consistently. The rule is structural -
        # chokepoints.csv filtered to states with a GPR series, and an economy is
        # self-excluded at exactly the straits where it is the only such state,
        # over the economies that have a trade channel (the set 03 builds
        # chokepoint rows for; TWN has none).
        ck_p = ROOT / "data" / "reference" / "chokepoints.csv"
        if isinstance(lit, dict) and isinstance(excl, dict) and ck_p.exists() and srcs:
            with ck_p.open(newline="", encoding="utf-8") as fh:
                table = {row["chokepoint"]: [x for x in row["gpr_littoral_states"].split(";") if x]
                         for row in csv.DictReader(fh)}
            exp_lit = {pnt: [x for x in states if x in srcs] for pnt, states in table.items()}
            check(exp_lit == lit,
                  "intensity.json: choke_littorals equals chokepoints.csv filtered to GPR-covered states"
                  + ("" if exp_lit == lit else f" -> expected {json.dumps(exp_lit, sort_keys=True)}"))
            trade_econ = {iso for iso, rec in (d.get("countries") or {}).items()
                          if "trade" in (rec.get("rebased") or {})}
            sole: dict[str, list[str]] = {}
            for pnt, states in exp_lit.items():
                if len(states) == 1 and states[0] in trade_econ:
                    sole.setdefault(states[0], []).append(pnt)
            check({k: sorted(v) for k, v in sole.items()} == {k: sorted(v) for k, v in excl.items()},
                  f"intensity.json: choke_self_excluded equals the sole-covered-littoral pairs "
                  f"recomputed from chokepoints.csv and gpr.json ({json.dumps(excl, sort_keys=True)})")
        check("top_sources" not in d,
              "intensity.json: top_sources absent (the reverse map derives it)")
        check("own GPR" in (d.get("source") or ""),
              "intensity.json: source string states the own-GPR exclusion")

        # Interface surfaces. Exact ids and header keys are the contract the
        # front end was built to; METHODOLOGY 5.4, 5.7 and 3.4 name them.
        for tok, why in (
            ('id="btnCovRaw"', "coverage toggle: as-observed button"),
            ('id="btnCovNorm"', "coverage toggle: per-observed-dependency button"),
            ('id="covNote"', "coverage toggle: note states the identity and the caveats"),
            ('id="vintageNote"', "legend carries the weight-vintage caption"),
            ("['coverage_normalisation',", "export header records the coverage mode"),
            ("['anachronistic_weights',", "export header records the pre-2020 fallback"),
            ("illustrative starting point", "slider note labels the default mix"),
            # Code forms, not bare names: the comments mention all three too,
            # and a comment would satisfy a substring check.
            ("state.data?.choke_self_excluded?.[", "detail panel reads choke_self_excluded from the payload"),
            ("function chanVal(", "one helper divides channel values, so panel/export/attribution agree"),
            ("function vintageFor(", "vintage derived from weight_years, not from lazily loaded weights.json"),
            ("state.data?.weights_anachronistic_through", "anachronism flag read from the payload"),
        ):
            check(tok in html, f"index.html: {why} ({tok})")
        st_blk = html.split("const state = {")[-1].split("\n};")[0]
        check("covnorm: false," in st_blk,
              "index.html: as-observed stays the default (invariant 7) (covnorm: false, in the state block)")
        cols = html.split("const EXPORT_COLS")[-1].split(";")[0]
        check("'weight_vintage'" in cols and "'weights_anachronistic'" in cols,
              "EXPORT_COLS carry weight_vintage and weights_anachronistic")
        det = html.split("function detail(")[-1]
        multi = det.split("if (state.kind === 'intensity_trade')")[0]
        check("top_sources" not in multi,
              "detail panel (intensity_multi) no longer reads top_sources")
        check("d3js.org" not in html and "/d3@" not in html and "d3.min.js" not in html,
              "index.html does not load D3 (SOURCES lists only what is loaded)")

        # Documentation. METHODOLOGY is the contract; its section numbers and
        # export column list must match the code, and SOURCES must name the two
        # sources actually joined.
        meth_p = ROOT / "METHODOLOGY.md"
        meth = meth_p.read_text(encoding="utf-8") if meth_p.exists() else ""
        heads = re.findall(r"^## (\d+)\.", meth, re.M)
        check(bool(heads) and len(heads) == len(set(heads)),
              f"METHODOLOGY: no two '## N.' headings share a number ({', '.join(heads)})")
        check(bool(re.search(r"^\*\*5\.7 ", meth, re.M)),
              "METHODOLOGY: 5.7 (anachronistic weight vintages) present")
        check(bool(re.search(r"^\*\*5\.8 ", meth, re.M)),
              "METHODOLOGY: 5.8 (channel discrimination, T4) present")
        # Read the channel order from the code, not from a list typed here:
        # EXPORT_COLS in index.html is built from EXPORT_CHANNELS in exactly
        # this shape, so a reorder there must show up as a doc mismatch.
        m_ch = re.search(r"EXPORT_CHANNELS = \[([^\]]*)\]", html)
        chs = re.findall(r"'([a-z]+)'", m_ch.group(1)) if m_ch else []
        check(bool(chs), f"index.html: EXPORT_CHANNELS parsed ({', '.join(chs)})")
        exp_cols = (["iso3", "name", "month", "intensity"]
                    + ["c_" + c for c in chs]
                    + ["covered_" + c for c in chs]
                    + ["weights_stale", "weight_vintage", "weights_anachronistic"])
        # The column list is one backticked, comma-separated block starting at
        # iso3; it must equal EXPORT_COLS in order, so the two cannot drift.
        blk = re.search(r"`(iso3,[^`]*)`", meth)
        listed = [c.strip() for c in blk.group(1).replace("\n", " ").split(",")] if blk else []
        check(bool(chs) and listed == exp_cols,
              "METHODOLOGY 6 lists the export columns exactly as EXPORT_COLS derived from EXPORT_CHANNELS"
              + ("" if listed == exp_cols else f" -> doc has {listed}"))
        for key in ("coverage_normalisation", "anachronistic_weights", "weights_anachronistic_through",
                    "choke_self_excluded"):
            check(f"`{key}`" in meth, f"METHODOLOGY names the payload/header key `{key}`")
        src_p = ROOT / "SOURCES.md"
        src = src_p.read_text(encoding="utf-8") if src_p.exists() else ""
        for tok in ("WITS", "TiVA", "UN Comtrade"):
            check(tok in src, f"SOURCES.md names the joined source '{tok}'")

        # The committed validation report must agree with the payload it was
        # run against. story.html no longer types the report's figures: 04
        # writes them to web/data/validation.json and the page fills data-stat
        # hooks from it at load, so the checks are (i) the summary equals the
        # report, figure by figure, and (ii) the page fetches it and carries the
        # hooks. A monthly refresh then cannot leave a stale number on the page.
        rep_p = ROOT / "data" / "processed" / "validation_report.txt"
        if rep_p.exists():
            rep = rep_p.read_text(encoding="utf-8")
            check("MISMATCH" not in rep, "validation report: payload and recomputed rules agree")
            check("T4  STATIC STRUCTURE" in rep, "validation report carries T4")
            m = re.search(r"anachronistic or contemporaneous through (\d{4}-\d{2})", rep)
            check(bool(m) and m.group(1) == through,
                  "validation report's anachronism cutoff equals the payload's")

            vs_p = ROOT / "web" / "data" / "validation.json"
            vs = json.loads(vs_p.read_text(encoding="utf-8")) if vs_p.exists() else {}
            check(vs.get("kind") == "validation_summary",
                  "web/data/validation.json present with kind validation_summary")
            check(vs.get("months_through") == (months[-1] if months else None),
                  "validation.json months_through equals intensity.json's last month")

            def near(a, b) -> bool:
                # Both sides are the same float at three decimals; the tolerance
                # only absorbs the format-vs-round representation of a tie.
                try:
                    return abs(float(a) - float(b)) <= 5e-4
                except (TypeError, ValueError):
                    return False

            t1s, t2s, t4s, ans = (vs.get(k) or {} for k in ("t1", "t2", "t4", "anachronistic"))
            t1 = re.search(r"Cross-sectional Spearman, mean\s*:\s*([-\d.]+)\s*\(min.*?n=(\d+) months\)", rep)
            check(bool(t1) and near(t1s.get("cross_sectional_mean"), t1.group(1))
                  and t1s.get("n_months") == int(t1.group(2)),
                  "validation.json T1 mean and month count equal the report's"
                  + (f" ({t1.group(1)}, n={t1.group(2)})" if t1 else ""))
            pp = re.search(r"Pooled Pearson\s+own-GPR vs Intensity\s*:\s*([-\d.]+)", rep)
            ps = re.search(r"Pooled Spearman own-GPR vs Intensity\s*:\s*([-\d.]+)", rep)
            check(bool(pp) and bool(ps) and near(t1s.get("pooled_pearson"), pp.group(1))
                  and near(t1s.get("pooled_spearman"), ps.group(1)),
                  "validation.json T1 pooled correlations equal the report's")
            per = dict(re.findall(r"^\s+(trade|va|energy|crm|choke)\s+[-\d.]+\s+[-\d.]+\s+([-\d.]+)\s+\(",
                                  rep.split("T2  CHANNEL")[0], re.M))
            check(bool(per) and all(near((t1s.get("per_channel") or {}).get(ch), v)
                                    for ch, v in per.items()),
                  f"validation.json T1 per-channel means equal the report's ({len(per)} channels)")
            m2 = re.search(r"Pairs above 0\.9: (.*)", rep)
            rep_pairs = re.findall(r"(\w+)-(\w+) ([\d.]+)", m2.group(1)) if m2 else []
            vs_pairs = {tuple(sorted((a, b))): v for a, b, v in (t2s.get("pairs_above_0_9") or [])}
            check(bool(m2) and len(rep_pairs) == len(vs_pairs)
                  and all(near(vs_pairs.get(tuple(sorted((a, b)))), v) for a, b, v in rep_pairs),
                  "validation.json T2 pairs above 0.9 equal the report's ("
                  + (", ".join(f"{a}-{b} {v}" for a, b, v in rep_pairs) or "none") + ")")
            mo = re.search(r"Mean off-diagonal Spearman:\s*([-\d.]+)", rep)
            dc = re.search(r"Distinguishable channels at that threshold: (\d+)", rep)
            check(bool(mo) and bool(dc) and near(t2s.get("mean_offdiagonal"), mo.group(1))
                  and t2s.get("distinguishable_channels") == int(dc.group(1)),
                  "validation.json T2 mean off-diagonal and bloc count equal the report's")
            blk_a = rep.split("Sample A:")[-1].split("Sample B:")[0]
            mix = re.search(r"Intensity \(default mix\)\s+\d+\s+\d+\s+([\d.]+)\s+([\d.]+)\s+[\d.]+\s+([\d.]+)\s+([\d.]+) \(",
                            blk_a)
            t4 = re.search(r"Verdict \(Sample A, default mix\): residual ([\d.]+)", rep)
            mob = re.search(r"Ranking mobility ([\d.]+) ->", rep)
            check(bool(mix) and bool(t4) and bool(mob)
                  and near(t4s.get("economy_share"), mix.group(1))
                  and near(t4s.get("month_share"), mix.group(2))
                  and near(t4s.get("residual_share"), mix.group(3))
                  and near(t4s.get("residual_share"), t4.group(1))
                  and near(t4s.get("ranking_mobility"), mix.group(4))
                  and near(t4s.get("ranking_mobility"), mob.group(1)),
                  "validation.json T4 shares and mobility equal the report's Sample A default mix"
                  + (f" (residual {t4.group(1)}, mobility {mob.group(1)})" if t4 and mob else ""))
            ck_m = re.search(r"^\s+choke\s+\d+\s+\d+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+) \(",
                             blk_a, re.M)
            check(bool(ck_m) and near(t4s.get("choke_ranking_mobility"), ck_m.group(1)),
                  "validation.json T4 chokepoint mobility equals the report's Sample A line")
            an = re.search(r"anachronistic or contemporaneous through (\d{4}-\d{2}): (\d+) of (\d+) months \(([\d.]+)%\)", rep)
            check(bool(an) and ans.get("through") == an.group(1) and ans.get("n") == int(an.group(2))
                  and vs.get("n_months_total") == int(an.group(3))
                  and near(ans.get("share"), float(an.group(4)) / 100),
                  "validation.json anachronism cutoff, count and share equal the report's")

            story_p = ROOT / "web" / "story.html"
            story = story_p.read_text(encoding="utf-8") if story_p.exists() else ""
            check("'./data/validation.json'" in story,
                  "story.html fetches ./data/validation.json at load")
            check("function fillStats(" in story and "data-stat" in story.split("function fillStats(")[-1][:1200],
                  "story.html fills the data-stat hooks from the summary")
            for hook, why in (("t1_mean", "T1 mean"), ("t1_n", "T1 month count"),
                              ("t4_residual", "T4 residual share"), ("t4_mobility", "T4 ranking mobility")):
                check(f'data-stat="{hook}"' in story, f"story.html carries the {why} hook (data-stat=\"{hook}\")")
            for a, b, _ in rep_pairs:
                check(f'data-stat="t2_{a}_{b}"' in story or f'data-stat="t2_{b}_{a}"' in story,
                      f"story.html carries a hook for the T2 pair {a}-{b} the report names")
    else:
        WARN.append("intensity.json is not kind=intensity_multi - methods review checks skipped")
        print("  warn intensity.json is not intensity_multi - skipped")

    # ── result --------------------------------------------------------------
    print()
    for w in WARN:
        print(f"warn: {w}")
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s)")
        for m in FAIL:
            print(f"  - {m}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
