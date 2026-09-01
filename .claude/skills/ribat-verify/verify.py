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

KNOWN_KINDS = {"gpr_source_side", "intensity_trade", "intensity_multi"}
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
    section("payloads")
    for p in sorted((ROOT / "web" / "data").glob("*.json")):
        if "countries-50m" in p.name:
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        kind = d.get("kind")
        check(kind in KNOWN_KINDS, f"{p.name}: kind={kind!r} recognised")
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
