"""
02b_build_channel_weights.py — energy and raw-material dependency weights.

Same WITS datasource, same cache directory, same construction rules as the
trade channel in 02 (WLD denominator, OAS->TWN remap, GPR-44 restriction),
but product-restricted and IMPORT-SIDE ONLY: dependency through a supply
channel is an import concept, so exports do not enter (unlike w_trade).

Product groups (WITS tradestats-trade codelist, verified 2026-08-31):
  Fuels     SITC section 3 (coal, oil, gas, electricity)   -> w_energy
  OresMtls  SITC 27 + 28 + 68 (ores, minerals, metals)     -> w_crm

OresMtls is a PROXY for the critical-raw-materials channel: it is broader than
the EU CRM Act list (it includes e.g. iron ore) and coarser than HS-6. The
honest upgrade path is JRC RMIS / Comext at HS-6 (METHODOLOGY.md section 3.3);
this proxy exists so the channel ships with a defensible open-data basis.

Requests: 44 reporters x 3 years x 2 products = 264 (imports only), throttled,
cached to data/raw/wits/ as {rep}_{year}_M_{product}.xml.

Output: data/processed/channel_weights.csv
  exposed_iso3, source_iso3, year, channel, w, covered_share
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
OUT = ROOT / "data" / "processed" / "channel_weights.csv"

YEARS = [2019, 2021, 2023]
PRODUCTS = {"energy": "Fuels", "crm": "OresMtls"}
THROTTLE_S = 0.6

GPR44 = [
    "ARG","AUS","BEL","BRA","CAN","CHE","CHL","CHN","COL","DEU","DNK","EGY",
    "ESP","FIN","FRA","GBR","HKG","HUN","IDN","IND","ISR","ITA","JPN","KOR",
    "MEX","MYS","NLD","NOR","PER","PHL","POL","PRT","RUS","SAU","SWE","THA",
    "TUN","TUR","TWN","UKR","USA","VEN","VNM","ZAF",
]

URL = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade/"
    "reporter/{rep}/year/{year}/partner/all/product/{prod}/indicator/MPRT-TRD-VL"
)

SERIES_RX = re.compile(
    r'<Series [^>]*PARTNER="([A-Z0-9]+)"[^>]*>\s*<Obs [^>]*OBS_VALUE="([0-9.eE+-]+)"'
)


def fetch(rep: str, year: int, prod_code: str) -> str | None:
    f = CACHE / f"{rep}_{year}_M_{prod_code}.xml"
    if f.exists():
        return f.read_text() or None
    url = URL.format(rep=rep.lower(), year=year, prod=prod_code)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (research; Intensity index pipeline)"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                xml = r.read().decode()
            f.write_text(xml)
            time.sleep(THROTTLE_S)
            return xml
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                f.write_text("")  # negative-cache
                time.sleep(THROTTLE_S)
                return None
            time.sleep(3 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    print(f"  FAILED {rep} {year} {prod_code} after retries", file=sys.stderr)
    return None


def parse(xml: str) -> dict[str, float]:
    return {p: float(v) for p, v in SERIES_RX.findall(xml)}


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, rep in enumerate(GPR44, 1):
        print(f"[{n:2d}/44] {rep}", flush=True)
        for year in YEARS:
            for channel, prod_code in PRODUCTS.items():
                xml = fetch(rep, year, prod_code)
                if not xml:
                    continue
                m = parse(xml)
                if "OAS" in m:
                    m["TWN"] = m.pop("OAS")
                total = m.get("WLD", 0.0)
                if total <= 0:
                    continue
                gpr_partners = [p for p in m if p in GPR44 and p != rep]
                covered = sum(m[p] for p in gpr_partners) / total
                for p in gpr_partners:
                    w = m[p] / total
                    if w > 0:
                        rows.append(
                            {"exposed_iso3": rep, "source_iso3": p, "year": year,
                             "channel": channel, "w": round(w, 6),
                             "covered_share": round(covered, 4)}
                        )

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(df):,} rows)")
    if not df.empty:
        print(
            df.groupby(["channel", "year"])
            .agg(reporters=("exposed_iso3", "nunique"),
                 pairs=("w", "size"),
                 mean_covered=("covered_share", "mean"))
            .round(3)
            .to_string()
        )


if __name__ == "__main__":
    main()
