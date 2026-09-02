"""
01_load_gpr.py — parse the Caldara & Iacoviello GPR workbook into tidy form.

Discovery-based rather than hardcoded: the workbook's column mnemonics have
changed across vintages, so this script reports what it finds instead of
assuming a fixed schema. Run it first and read the coverage report before
building anything on top.

Input:  data/raw/data_gpr_export.xls
Output: data/processed/gpr_country_monthly.csv
        data/processed/gpr_coverage_report.txt

Data are CC-BY. Citation is mandatory — see METHODOLOGY.md section 6.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "data_gpr_export.xls"
OUT_DIR = ROOT / "data" / "processed"

GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"

# Country-specific series are prefixed GPRC_ (recent, 1985-) or GPRHC_
# (historical, 1900-), followed by an ISO3 code. Verified against the
# 2026-08 vintage: 44 of each. Re-check if the workbook is updated.
COUNTRY_PATTERNS = {
    "recent": r"^GPRC_([A-Z]{3})$",
    "historical": r"^GPRHC_([A-Z]{3})$",
}

EXPECTED_N_COUNTRIES = 44


def load_workbook(path: Path) -> pd.DataFrame:
    if not path.exists():
        sys.exit(
            f"Missing {path}\n\n"
            f"Fetch it with:\n"
            f"  curl -sSL -o {path} {GPR_URL}\n"
        )
    # The workbook is legacy OLE2 (.xls) and needs xlrd; the site has
    # occasionally served .xlsx under the same name, so fall back rather
    # than failing outright.
    try:
        return pd.read_excel(path, engine="xlrd")
    except Exception:
        return pd.read_excel(path, engine="openpyxl")


def find_date_column(df: pd.DataFrame) -> str:
    for candidate in ("month", "Month", "date", "DATE", "obs"):
        if candidate in df.columns:
            return candidate
    # Fall back to the first column that parses as dates for most rows.
    for col in df.columns[:3]:
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().mean() > 0.9:
            return col
    sys.exit(f"Could not identify a date column. Columns seen: {list(df.columns)[:15]}")



def export_web(tidy: pd.DataFrame) -> None:
    """Export the recent-index country series for the web layer.

    This is source-side GPR, not exposure-weighted Intensity. The map labels it as
    such. Once 03_build_intensity.py exists it writes web/data/intensity.json, which the
    front end prefers over this file.
    """

    recent = tidy[(tidy["variant"] == "recent") & (tidy["month"].dt.year >= 1985)]
    months = sorted(recent["month"].unique())
    month_labels = [pd.Timestamp(m).strftime("%Y-%m") for m in months]
    idx = {m: i for i, m in enumerate(months)}

    countries: dict[str, dict] = {}
    for iso, grp in recent.groupby("iso3"):
        lvl = [None] * len(months)
        reb = [None] * len(months)
        for m, g, r in zip(grp["month"], grp["gpr"], grp["gpr_rebased"]):
            i = idx[m]
            lvl[i] = None if pd.isna(g) else round(float(g), 4)
            reb[i] = None if pd.isna(r) else round(float(r), 2)
        countries[iso] = {"level": lvl, "rebased": reb}

    st = RAW.stat()
    payload = {
        "kind": "gpr_source_side",
        "months": month_labels,
        "countries": countries,
        "source": "Caldara & Iacoviello (2022), country-specific GPR, CC-BY",
        # The workbook is republished IN PLACE with prior months revised, so a
        # date does not identify a vintage: two people can fetch "the GPR
        # workbook" weeks apart, get different numbers, and have no way to tell
        # which one produced a given chart. The digest identifies it.
        "workbook_sha256": file_sha256(RAW),
        "workbook_bytes": st.st_size,
        # When the workbook was fetched, not when this script last ran. This was
        # date.today(), which made every rebuild look like a fresh download and
        # told a reader nothing about the vintage they were looking at.
        "downloaded": date.fromtimestamp(st.st_mtime).isoformat(),
        "built": date.today().isoformat(),
    }
    payload["content_sha256"] = series_sha256(month_labels, countries)
    web_dir = ROOT / "web" / "data"
    web_dir.mkdir(parents=True, exist_ok=True)
    out = web_dir / "gpr.json"

    # data/raw is gitignored and the refresh runs in CI, so a working tree can
    # hold a workbook older than the published payload. Rebuilding from it
    # silently dropped a month here - the run printed a clean "wrote ... 499
    # months" and nothing said the file had just lost data. 03 has had this
    # guard since the payload it writes is the one the site reads; 01 writes a
    # published payload too and needs it for the same reason.
    if out.exists() and "--allow-regression" not in sys.argv:
        try:
            prev = json.loads(out.read_text())
        except (json.JSONDecodeError, OSError):
            prev = None
        if prev and prev.get("months"):
            pm, nm = prev["months"], month_labels
            lost = set(prev.get("countries") or {}) - set(countries)
            if nm[-1] < pm[-1] or len(nm) < len(pm) or lost:
                print(f"REFUSING to overwrite {out.name}: "
                      f"{len(pm)} months through {pm[-1]} on disk, "
                      f"{len(nm)} through {nm[-1]} from this workbook"
                      + (f", losing {sorted(lost)}" if lost else ""))
                print("  The workbook in data/raw is almost certainly older than the "
                      "published payload. Re-download it, or pass --allow-regression "
                      "if upstream genuinely withdrew data.")
                sys.exit(1)

    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out}  ({len(countries)} countries x {len(months)} months)")
    print(f"  workbook {payload['workbook_sha256'][:16]}…  fetched {payload['downloaded']}")
    print(f"  series   {payload['content_sha256'][:16]}…  through {month_labels[-1]}")
    stamp_readme(payload)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def series_sha256(months: list[str], countries: dict) -> str:
    """Digest of the data, not the file.

    Deliberately the SAME recipe as the change detection in
    .github/workflows/refresh.yml. If the two ever diverge, the workflow's
    "is this a new vintage" answer and the README's published stamp stop
    describing the same object, and nobody would notice; the verifier compares
    the README against this value for that reason.
    """
    return hashlib.sha256(
        json.dumps({"m": months, "c": countries}, sort_keys=True).encode()
    ).hexdigest()


README_START = "<!-- PROVENANCE:START -->"
README_END = "<!-- PROVENANCE:END -->"


def stamp_readme(payload: dict) -> None:
    """Rewrite the provenance block in README.md from the published payload.

    Hand-maintained provenance rots. This repository has already shipped one
    payload note that was wrong about its own contents, so the block is
    generated rather than typed, and the verifier fails if it drifts from
    web/data/gpr.json.
    """
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    txt = readme.read_text(encoding="utf-8")
    if README_START not in txt or README_END not in txt:
        print(f"NOTE {readme.name} has no provenance markers — not stamped")
        return
    # Describe the payload that is published, not a workbook that happens to be
    # in data/raw. A clone has no workbook at all (it is gitignored), and a
    # maintainer's local copy can be a month behind what CI published - stamping
    # from the file on disk would put a digest in the README for a vintage the
    # site is not serving.
    wb_sha = payload.get("workbook_sha256")
    wb_row = (f"| Workbook SHA-256 | `{wb_sha}` |" if wb_sha else
              "| Workbook SHA-256 | not recorded — this payload predates the field; "
              "the next refresh stamps it |")
    size_row = (f"| GPR workbook | `{RAW.name}`, {payload['workbook_bytes']:,} bytes |"
                if payload.get("workbook_bytes") else f"| GPR workbook | `{RAW.name}` |")
    block = "\n".join([
        README_START,
        "",
        "| | |",
        "|---|---|",
        size_row,
        wb_row,
        f"| Fetched | {payload.get('downloaded', 'unknown')} |",
        f"| Data through | {payload['months'][-1]} |",
        f"| Series SHA-256 | `{payload.get('content_sha256') or series_sha256(payload['months'], payload['countries'])}` |",
        f"| Payload built | {payload.get('built', payload.get('downloaded', 'unknown'))} |",
        "",
        "Generated by `pipeline/01_load_gpr.py`; do not edit by hand. The verifier",
        "fails if this block disagrees with `web/data/gpr.json`.",
        "",
        "The workbook is republished **in place** with recent months revised, so the",
        "filename and the fetch date do not identify a vintage on their own — only the",
        "digests do. To check that a clone holds the same data these numbers were built",
        "from:",
        "",
        "```bash",
        "shasum -a 256 data/raw/data_gpr_export.xls        # must match Workbook SHA-256",
        "python3 -c \"import hashlib,json;d=json.load(open('web/data/gpr.json'));print(hashlib.sha256(json.dumps({'m':d['months'],'c':d['countries']},sort_keys=True).encode()).hexdigest())\"",
        "```",
        "",
        "The second command recomputes Series SHA-256 from the published payload, so it",
        "works without the workbook — which `.gitignore` excludes.",
        "",
        README_END,
    ])
    start = txt.index(README_START)
    end = txt.index(README_END) + len(README_END)
    readme.write_text(txt[:start] + block + txt[end:], encoding="utf-8")
    print(f"stamped {readme.name} provenance block")


def stamp_only() -> int:
    """Refresh the README block from the published payload without rebuilding.

    Needed because the workbook is gitignored: a clone, or a maintainer whose
    local copy is stale, must still be able to regenerate a truthful stamp.
    """
    src = ROOT / "web" / "data" / "gpr.json"
    if not src.exists():
        print(f"no {src} — nothing to stamp")
        return 1
    stamp_readme(json.loads(src.read_text()))
    return 0


def main() -> None:
    if "--stamp-only" in sys.argv:
        sys.exit(stamp_only())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_workbook(RAW)

    date_col = find_date_column(df)
    # The workbook stores month as YYYYMM integers in some vintages and as
    # datetimes in others; handle both.
    raw_dates = df[date_col]
    if pd.api.types.is_numeric_dtype(raw_dates):
        df[date_col] = pd.to_datetime(
            raw_dates.astype("Int64").astype(str), format="%Y%m", errors="coerce"
        )
    else:
        df[date_col] = pd.to_datetime(raw_dates, errors="coerce")
    df = df.dropna(subset=[date_col])

    report: list[str] = [
        "GPR coverage report",
        f"generated    {date.today().isoformat()}",
        f"source file  {RAW.name}",
        f"date column  {date_col}",
        f"date range   {df[date_col].min():%Y-%m} to {df[date_col].max():%Y-%m}",
        f"total cols   {df.shape[1]}",
        "",
    ]

    frames = []
    for variant, pattern in COUNTRY_PATTERNS.items():
        rx = re.compile(pattern)
        cols = sorted(
            c for c in df.columns if isinstance(c, str) and rx.match(c.strip())
        )
        isos = [rx.match(c.strip()).group(1) for c in cols]

        report.append(f"{variant:<12} {len(cols)} country series")
        if variant == "recent" and len(cols) != EXPECTED_N_COUNTRIES:
            report.append(
                f"  WARNING expected {EXPECTED_N_COUNTRIES} recent country series, "
                f"found {len(cols)} — schema may have changed"
            )
        report.append(f"  {', '.join(isos)}" if isos else "  (none found)")
        report.append("")

        if not cols:
            continue

        tidy = (
            df[[date_col] + cols]
            .melt(id_vars=date_col, var_name="series", value_name="gpr")
            .assign(
                iso3=lambda d: d["series"].str.extract(pattern)[0],
                variant=variant,
            )
            .rename(columns={date_col: "month"})
            .drop(columns=["series"])
            .dropna(subset=["gpr"])
        )
        frames.append(tidy)

    if not frames:
        sys.exit(
            "No country series matched the expected mnemonics.\n"
            f"Columns present: {[c for c in df.columns][:40]}\n"
            "Inspect the workbook's mnemonic description columns and update "
            "COUNTRY_PATTERNS."
        )

    tidy = pd.concat(frames, ignore_index=True)

    # Both normalisations, computed here so the web layer can toggle without
    # recomputation. See METHODOLOGY.md section 4 — these answer different
    # questions and neither is the default.
    base = (
        tidy[(tidy["month"].dt.year >= 1985) & (tidy["month"].dt.year <= 2023)]
        .groupby(["iso3", "variant"])["gpr"]
        .mean()
        .rename("base_mean")
    )
    tidy = tidy.merge(base, on=["iso3", "variant"], how="left")
    tidy["gpr_rebased"] = tidy["gpr"] / tidy["base_mean"] * 100
    tidy = tidy.drop(columns=["base_mean"])

    out = OUT_DIR / "gpr_country_monthly.csv"
    tidy.to_csv(out, index=False)

    latest = tidy[tidy["variant"] == "recent"]
    if not latest.empty:
        last_month = latest["month"].max()
        top = (
            latest[latest["month"] == last_month]
            .nlargest(10, "gpr_rebased")[["iso3", "gpr", "gpr_rebased"]]
            .round(2)
        )
        report += [
            f"Top 10 by rebased GPR, {last_month:%Y-%m} (preliminary):",
            top.to_string(index=False),
            "",
            "NOTE the most recent months are preliminary and subject to revision "
            "as delayed newspaper editions enter the search database.",
        ]

    (OUT_DIR / "gpr_coverage_report.txt").write_text("\n".join(report))
    print("\n".join(report))
    print(f"\nwrote {out}  ({len(tidy):,} rows)")
    export_web(tidy)


if __name__ == "__main__":
    main()
