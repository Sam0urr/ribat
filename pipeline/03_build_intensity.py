"""
03_build_intensity.py — join country GPR with trade weights into the Intensity index.

INT_i,t = sum_j w_ij * G_j,t          (METHODOLOGY.md section 2)

Trade channel only for now (Phase 1). Energy / CRM / chokepoint channels are
Phase 2; the web payload carries per-channel values so the front end's channel
sliders have something to weight when those exist. Until then every channel
except trade is null and the sliders stay disabled.

Weight vintage: each month t uses the LATEST benchmark year strictly BEFORE t
(2019 for months in 2015-2020, 2021 for 2021-2023, 2023 for 2024-).
Contemporaneous weights are deliberately not used — section 5.3.

Both GPR normalisations propagate: intensity_level uses raw article shares,
intensity_rebased uses each source country's own-mean-100 series.

Input:  data/processed/gpr_country_monthly.csv   (01)
        data/processed/trade_weights.csv         (02)
Output: data/processed/intensity_monthly.csv
        web/data/intensity.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
WEB = ROOT / "web" / "data"

START_YEAR = 1985  # weights from 2019 are ahistorical before ~2015; keep the
                   # full recent range anyway and let the reader judge — the
                   # alternative (silently truncating) hides the design choice.


def weight_year_for(month: pd.Timestamp, years: list[int]) -> int:
    prior = [y for y in years if y < month.year]
    return max(prior) if prior else min(years)


def main() -> None:
    gpr = pd.read_csv(PROC / "gpr_country_monthly.csv", parse_dates=["month"])
    gpr = gpr[(gpr["variant"] == "recent") & (gpr["month"].dt.year >= START_YEAR)]

    w = pd.read_csv(PROC / "trade_weights.csv")
    years = sorted(w["year"].unique())
    print(f"weights: {len(w):,} pairs, benchmark years {years}")

    # month -> weight vintage
    months = sorted(gpr["month"].unique())
    vintage = {m: weight_year_for(pd.Timestamp(m), years) for m in months}
    gpr = gpr.assign(wyear=gpr["month"].map(vintage))

    # Carry forward the last reported benchmark for non-reporters.
    # Russia stops reporting to Comtrade after 2021 and Venezuela earlier; an
    # exact-year join silently drops them from the map for recent months, which
    # reads as a rendering bug rather than a data limitation. METHODOLOGY.md
    # section 3.1 specifies carry-forward, so implement it and record which
    # vintage was actually used, per economy, so the interface can say so.
    avail = w.groupby("exposed_iso3")["year"].unique().to_dict()
    blocks = []
    for target in years:
        for exp, ys in avail.items():
            prior = [y for y in ys if y <= target]
            use = max(prior) if prior else min(ys)
            blk = w[(w["exposed_iso3"] == exp) & (w["year"] == use)].copy()
            blk["wyear"] = target
            blk["weight_vintage"] = use
            blocks.append(blk)
    w = pd.concat(blocks, ignore_index=True)

    stale = {
        exp: int(max(ys))
        for exp, ys in avail.items()
        if max(ys) < max(years)
    }
    if stale:
        print(f"carried-forward weights (last reported year): {stale}")

    # join: exposed i <- source j
    merged = gpr.merge(
        w.rename(columns={"source_iso3": "iso3"}),
        on=["iso3", "wyear"],
        how="inner",
    )
    merged = merged.assign(
        c_level=merged["w_trade"] * merged["gpr"],
        c_rebased=merged["w_trade"] * merged["gpr_rebased"],
    )
    intens = (
        merged.groupby(["exposed_iso3", "month"])
        .agg(
            intensity_level=("c_level", "sum"),
            intensity_rebased=("c_rebased", "sum"),
            covered_share=("covered_share", "first"),
            n_sources=("iso3", "nunique"),
            wyear=("wyear", "first"),
            weight_vintage=("weight_vintage", "first"),
        )
        .reset_index()
    )

    intens.to_csv(PROC / "intensity_monthly.csv", index=False)
    print(f"wrote {PROC / 'intensity_monthly.csv'}  ({len(intens):,} rows)")

    # ---- web payload -------------------------------------------------------
    month_labels = [pd.Timestamp(m).strftime("%Y-%m") for m in months]
    idx = {pd.Timestamp(m): i for i, m in enumerate(months)}

    countries: dict[str, dict] = {}
    for iso, grp in intens.groupby("exposed_iso3"):
        lvl = [None] * len(months)
        reb = [None] * len(months)
        for m, l, r in zip(grp["month"], grp["intensity_level"], grp["intensity_rebased"]):
            lvl[idx[m]] = round(float(l), 4)
            reb[idx[m]] = round(float(r), 2)
        countries[iso] = {
            "level": lvl,
            "rebased": reb,
            "covered": round(float(grp["covered_share"].iloc[-1]), 3),
        }

    # top source decomposition for the latest month, for the detail panel
    last = max(months)
    top_sources: dict[str, list] = {}
    lm = merged[merged["month"] == last]
    for iso, grp in lm.groupby("exposed_iso3"):
        top = grp.nlargest(5, "c_rebased")
        top_sources[iso] = [
            [r["iso3"], round(r["w_trade"], 4), round(r["c_rebased"], 1)]
            for _, r in top.iterrows()
        ]

    payload = {
        "kind": "intensity_trade",
        "months": month_labels,
        "countries": countries,
        "top_sources": top_sources,
        "weight_years": [int(y) for y in years],
        "stale_weights": stale,
        "source": "Intensity = trade-weighted Caldara & Iacoviello country GPR. "
                  "Weights: WITS/UN Comtrade benchmark years.",
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
    }
    WEB.mkdir(parents=True, exist_ok=True)
    out = WEB / "intensity.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out}  ({len(countries)} exposed economies x {len(months)} months)")

    latest = intens[intens["month"] == last].nlargest(10, "intensity_rebased")
    print(f"\nTop 10 exposed economies, {pd.Timestamp(last):%Y-%m} (rebased Intensity):")
    print(latest[["exposed_iso3", "intensity_rebased", "intensity_level", "covered_share"]]
          .round(2).to_string(index=False))


if __name__ == "__main__":
    main()
