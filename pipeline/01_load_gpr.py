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
    import json

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

    payload = {
        "kind": "gpr_source_side",
        "months": month_labels,
        "countries": countries,
        "source": "Caldara & Iacoviello (2022), country-specific GPR, CC-BY",
        "downloaded": date.today().isoformat(),
    }
    web_dir = ROOT / "web" / "data"
    web_dir.mkdir(parents=True, exist_ok=True)
    out = web_dir / "gpr.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out}  ({len(countries)} countries x {len(months)} months)")


def main() -> None:
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
