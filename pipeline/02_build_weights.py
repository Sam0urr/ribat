"""
02_build_weights.py — bilateral trade dependency weights from WITS.

Why WITS and not the Comtrade API directly: WITS serves the same underlying
UN Comtrade data, needs no API key, and its partner/all endpoint has no
500-record cap (the Comtrade free preview truncates at 500 rows, which is
almost exactly one reporter's partner count x two flows — silent-truncation
territory). Verified live 2026-08-31.

Benchmark years, not monthly series (METHODOLOGY.md section 5.3): weights must
be lagged / pre-shock to mitigate endogeneity, so a few benchmark cross-sections
are the design, not a compromise. 2024 is not yet in WITS; latest is 2023.

  2019  pre-Covid baseline
  2021  pre-invasion baseline
  2023  latest available

Requests: 44 reporters x 3 years x 2 flows = 264, throttled, cached to
data/raw/wits/ so re-runs cost nothing.

Output: data/processed/trade_weights.csv
  exposed_iso3, source_iso3, year, w_trade, covered_share
  w_trade       = (M_ij + X_ij) / (M_i + X_i), partners restricted to GPR-44
  covered_share = share of i's total trade with GPR-44 partners (excl. self)
"""

from __future__ import annotations

import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "raw" / "wits"
OUT = ROOT / "data" / "processed" / "trade_weights.csv"

YEARS = [2019, 2021, 2023]
FLOWS = {"M": "MPRT-TRD-VL", "X": "XPRT-TRD-VL"}
THROTTLE_S = 0.6

GPR44 = [
    "ARG","AUS","BEL","BRA","CAN","CHE","CHL","CHN","COL","DEU","DNK","EGY",
    "ESP","FIN","FRA","GBR","HKG","HUN","IDN","IND","ISR","ITA","JPN","KOR",
    "MEX","MYS","NLD","NOR","PER","PHL","POL","PRT","RUS","SAU","SWE","THA",
    "TUN","TUR","TWN","UKR","USA","VEN","VNM","ZAF",
]

URL = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade/"
    "reporter/{rep}/year/{year}/partner/all/product/total/indicator/{ind}"
)

SERIES_RX = re.compile(
    r'<Series [^>]*PARTNER="([A-Z0-9]+)"[^>]*>\s*<Obs [^>]*OBS_VALUE="([0-9.eE+-]+)"'
)


def fetch(rep: str, year: int, flow: str) -> str | None:
    """Return raw XML, from cache if present. None = no data for this cell."""
    f = CACHE / f"{rep}_{year}_{flow}.xml"
    if f.exists():
        return f.read_text() or None
    url = URL.format(rep=rep.lower(), year=year, ind=FLOWS[flow])
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (research; Intensity index pipeline)"}
    )  # WITS rejects the default Python-urllib agent
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                xml = r.read().decode()
            f.write_text(xml)
            time.sleep(THROTTLE_S)
            return xml
        except urllib.error.HTTPError as e:
            if e.code == 404:
                f.write_text("")  # negative-cache: reporter-year not in WITS
                time.sleep(THROTTLE_S)
                return None
            time.sleep(3 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    print(f"  FAILED {rep} {year} {flow} after retries", file=sys.stderr)
    return None


def parse(xml: str) -> dict[str, float]:
    """PARTNER iso3 -> value. Includes WLD (world total)."""
    return {p: float(v) for p, v in SERIES_RX.findall(xml)}


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, rep in enumerate(GPR44, 1):
        print(f"[{n:2d}/44] {rep}", flush=True)
        for year in YEARS:
            flows = {}
            for flow in FLOWS:
                xml = fetch(rep, year, flow)
                flows[flow] = parse(xml) if xml else {}
            # Comtrade codes Taiwan as "Other Asia, nes" (OAS); that bucket
            # is overwhelmingly Taiwan, so remap it. Documented assumption.
            for f in flows:
                if "OAS" in flows[f]:
                    flows[f]["TWN"] = flows[f].pop("OAS")
            # Denominator: the reported WLD total, NOT the sum over partners —
            # partner/all includes World Bank region and income aggregates
            # (ECS, EAS, NAC, ...) which double-count massively (sum of
            # partners ~ 2x WLD for DEU 2023).
            total = sum(flows[f].get("WLD", 0.0) for f in FLOWS)
            if total <= 0:
                continue
            partners = set(flows["M"]) | set(flows["X"])
            gpr_partners = [p for p in partners if p in GPR44 and p != rep]
            covered = sum(
                flows[f].get(p, 0.0) for f in FLOWS for p in gpr_partners
            ) / total
            for p in gpr_partners:
                w = (flows["M"].get(p, 0.0) + flows["X"].get(p, 0.0)) / total
                if w > 0:
                    rows.append(
                        {"exposed_iso3": rep, "source_iso3": p, "year": year,
                         "w_trade": round(w, 6), "covered_share": round(covered, 4)}
                    )

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)

    print(f"\nwrote {OUT}  ({len(df):,} rows)")
    if not df.empty:
        summary = (
            df.groupby("year")
            .agg(reporters=("exposed_iso3", "nunique"),
                 pairs=("w_trade", "size"),
                 mean_covered=("covered_share", "mean"))
            .round(3)
        )
        print(summary.to_string())
        missing = [
            (y, r) for y in YEARS for r in GPR44
            if df[(df.year == y) & (df.exposed_iso3 == r)].empty
        ]
        if missing:
            print(f"\nMISSING reporter-years ({len(missing)}):")
            for y, r in missing:
                print(f"  {r} {y}")


if __name__ == "__main__":
    main()
