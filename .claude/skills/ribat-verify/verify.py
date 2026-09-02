#!/usr/bin/env python3
"""Ribat pre-commit verification. Deterministic; no network. Exit 0 = pass."""
from __future__ import annotations

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

KNOWN_KINDS = {"gpr_source_side", "intensity_trade", "intensity_multi", "bilateral_weights"}
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
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not blocks:
        check(False, "no inline <script> block found in web/index.html")
    elif shutil.which("node") is None:
        WARN.append("node not available - JS syntax not checked")
        print("  warn node not available - skipped")
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(blocks[-1])
        r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        check(r.returncode == 0, "inline script node --check"
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
    sk = html.split("function sankeySVG(")[-1].split("\nfunction ")[0]
    check("a.total" in sk and "scale" in sk,
          "both columns share one scale, so the shortfall is to scale")

    section("pipeline guards")
    p3 = (ROOT / "pipeline" / "03_build_intensity.py")
    src3 = p3.read_text(encoding="utf-8") if p3.exists() else ""
    check("def guard_no_regression(" in src3,
          "03 refuses to overwrite a richer payload with a poorer one")
    check("--allow-regression" in src3,
          "03 offers an explicit override for intended shrinkage")
    check("sys.exit(1)" in src3,
          "03 exits non-zero when it refuses, so CI cannot ignore it")

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
