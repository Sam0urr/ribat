"""
02c_build_va_weights.py — value-added dependency weights from OECD TiVA (Phase 3).

Measure FDVA ("origin of value added in final demand"): value added originating
in source country j that is embodied in economy i's final demand. Unlike gross
bilateral trade, this looks through third countries — the German importer of
Polish intermediates embodying Russian inputs shows up as exposed to Russia
(METHODOLOGY.md section 5.2). Shares are computed here:

    w^va_ij = FDVA_{j -> i} / (FDVA_{W -> i} - FDVA_{i -> i})

Foreign-only denominator: domestic value added (typically 60-80% of final
demand) is excluded so the weights are scale-comparable with the gross trade
weights, which exclude own-country flows by construction. Without this the
gross/value-added toggle jumps ~3x for denominator reasons alone.

API notes (hard-won, 2026-08-31): the flow lives on the *sti-public* endpoint —
the /public endpoint 500s on every TiVA flow. The only measure with content is
FDVA (USD, annual, 1995-2022); FD_VA_SH exists in the codelist but holds no
data. Key order: MEASURE.VA_SOURCE_AREA.VA_SOURCE_ACTIVITY.FD_AREA.
FD_ACTIVITY.UNIT.FREQ. A too-specific key returns 404 "NoResultsFound", not an
error. Bonus over Comtrade: TWN, RUS and VEN exist as final-demand economies,
so the VA variant has no stale-weight carry-forward.

Benchmark years: 2019, 2021, 2022 (TiVA currently ends 2022).

Requests: one per exposed economy x years batch = 44, throttled, cached to
data/raw/tiva/.

Output: data/processed/va_weights.csv
  exposed_iso3, source_iso3, year, channel(=va), w, covered_share
  covered_share = share of i's foreign-sourced FDVA originating in GPR-44
"""

from __future__ import annotations

import csv
import io
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "raw" / "tiva"
OUT = ROOT / "data" / "processed" / "va_weights.csv"

YEARS = [2019, 2021, 2022]
THROTTLE_S = 1.0

GPR44 = [
    "ARG","AUS","BEL","BRA","CAN","CHE","CHL","CHN","COL","DEU","DNK","EGY",
    "ESP","FIN","FRA","GBR","HKG","HUN","IDN","IND","ISR","ITA","JPN","KOR",
    "MEX","MYS","NLD","NOR","PER","PHL","POL","PRT","RUS","SAU","SWE","THA",
    "TUN","TUR","TWN","UKR","USA","VEN","VNM","ZAF",
]

URL = (
    "https://sdmx.oecd.org/sti-public/rest/data/"
    "OECD.STI.PIE,DSD_TIVA_FDVA@DF_FDVA,1.1/"
    "FDVA.._T.{fd}._T.USD.A?startPeriod={y0}&endPeriod={y1}"
)


def fetch(fd: str) -> str | None:
    f = CACHE / f"fdva_{fd}.csv"
    if f.exists():
        return f.read_text() or None
    url = URL.format(fd=fd, y0=min(YEARS), y1=max(YEARS))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (research; Intensity index pipeline)",
            "Accept": "application/vnd.sdmx.data+csv; charset=utf-8",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                text = r.read().decode()
            f.write_text(text)
            time.sleep(THROTTLE_S)
            return text
        except urllib.error.HTTPError as e:
            if e.code == 404:  # NoResultsFound
                f.write_text("")
                time.sleep(THROTTLE_S)
                return None
            time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(5 * (attempt + 1))
    print(f"  FAILED {fd} after retries", file=sys.stderr)
    return None


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, fd in enumerate(GPR44, 1):
        print(f"[{n:2d}/44] {fd}", flush=True)
        text = fetch(fd)
        if not text:
            continue
        rdr = csv.DictReader(io.StringIO(text))
        vals: dict[tuple[str, int], float] = {}
        for r in rdr:
            try:
                src = r["VALUE_ADDED_SOURCE_AREA"]
                yr = int(r["TIME_PERIOD"])
                v = float(r["OBS_VALUE"])
            except (KeyError, ValueError):
                continue
            if yr in YEARS:
                vals[(src, yr)] = v
        for yr in YEARS:
            total = vals.get(("W", yr), 0.0)
            if total <= 0:
                continue
            own = vals.get((fd, yr), 0.0)
            foreign = total - own
            if foreign <= 0:
                continue
            srcs = [s for (s, y) in vals if y == yr and s in GPR44 and s != fd]
            covered = sum(vals[(s, yr)] for s in srcs) / foreign
            for s in srcs:
                w = vals[(s, yr)] / foreign
                if w > 0:
                    rows.append(
                        {"exposed_iso3": fd, "source_iso3": s, "year": yr,
                         "channel": "va", "w": round(w, 6),
                         "covered_share": round(covered, 4)}
                    )

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(df):,} rows)")
    if not df.empty:
        print(
            df.groupby("year")
            .agg(economies=("exposed_iso3", "nunique"), pairs=("w", "size"),
                 mean_covered=("covered_share", "mean"))
            .round(3).to_string()
        )


if __name__ == "__main__":
    main()
