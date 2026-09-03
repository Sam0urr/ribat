"""
04_validate.py — empirical validation of the Intensity index.

Four tests, each capable of failing and reported whether or not it flatters
the index:

  T1 DISCRIMINANT VALIDITY. If Intensity_i correlates ~1 with economy i's own
     source-side GPR, the exposure weighting adds nothing and the map is a
     re-plot of Caldara-Iacoviello. Reports pooled and cross-sectional rank
     correlation, PER CHANNEL. The trade line stays the headline, but the
     chokepoint channel is the one place an economy's own GPR could leak back
     in (through the littoral mean; 03 now excludes it), and a trade-only T1
     could not see that.

  T2 CHANNEL DISCRIMINATION. If the channels move together, the sliders are
     decorative. Reports the cross-channel Spearman matrix and NAMES the pairs
     above 0.9: two channels that co-move that tightly are one slider wearing
     two labels, so the count of distinguishable channels is the number of
     blocs, not the number of sliders.

  T3 EVENT STUDIES. Pre-registered expectations for known episodes: which
     economies should move, on which channel. Reports the actual top movers
     so the expectation can be scored honestly. Chokepoint events also list
     which economies have their own GPR removed from the littoral mean at the
     relevant strait, and for which the strait is dropped entirely.

  T4 STATIC STRUCTURE OR TIME SERIES? T1 shows the cross-section differs from
     GPR; nothing there shows the ranking MOVES. If INT ~ economy effect x
     global factor, the month slider is a static dependency map recoloured by
     world risk. Two-way fixed-effects decomposition
         y_it = mu + alpha_i + gamma_t + eps_it
     by two-way demeaning on the balanced panel, for the default-mix rebased
     Intensity (theta 55/25/10/10 over the channels present, recomputed here
     from intensity_monthly.csv as web/index.html does) and for each channel:
     share of total variance carried by economy effects alone, by month
     effects alone, by both, and the residual 1 - R2_twoway. Plus ranking
     mobility: mean Spearman between the cross-sectional ranking at t and at
     t-12. Thresholds are fixed in the constants below, before the numbers.

Sample rule. T1, T2 and T4 use months from the first properly LAGGED vintage:
years strictly after the earliest benchmark year, i.e. 2020-01 with benchmarks
2019/2021/2023. Months before the first benchmark fall back to it, so their
weights postdate them (anachronistic); months in the benchmark year itself use
contemporaneous rather than lagged weights. T3 keeps every pre-registered event
and flags those months as "anachronistic or contemporaneous"; T4 is repeated
on the full 1985-present sample under that caveat. Benchmark years are read
from trade_weights.csv - the list 03_build_intensity.py derives them from -
never typed in, and the payload's weights_anachronistic_through is checked
against the same rule.

Cross-checks against the payload. The header recomputes, from
chokepoints.csv, the GPR panel and the trade-channel economies, which
(economy, strait) pairs are sole-covered-littoral pairs over ALL six straits
and prints MISMATCH if the payload's choke_self_excluded differs; the per-event
note in T3 repeats the comparison for the strait behind each chokepoint event.

Input:  data/processed/intensity_monthly.csv; own GPR via 03.load_gpr() (the
        fresher of gpr_country_monthly.csv and web/data/gpr.json, as 03 used);
        trade_weights.csv; data/reference/chokepoints.csv;
        web/data/intensity.json (cross-check of choke_self_excluded and
        weights_anachronistic_through, when present)
Output: data/processed/validation_report.txt
        web/data/validation.json - a small tracked summary (kind
        validation_summary) of the T1, T2 and T4 figures and the anachronism
        share, which web/story.html reads at load so the numbers it quotes are
        the report's and cannot go stale between refreshes; the verifier checks
        it against the report.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
WEB = ROOT / "web" / "data"
OUT = PROC / "validation_report.txt"
SUMMARY = WEB / "validation.json"

CHANNELS = ["trade", "va", "energy", "crm", "choke"]

# The interface's default channel mix (web/index.html, state.weights), gross
# trade basis. An illustrative starting point, not a derived weighting. T4
# recomputes Intensity under it because the payload ships channels separately
# and the mix is applied client-side, renormalised over the channels present.
DEFAULT_MIX = {"trade": 55, "energy": 25, "crm": 10, "choke": 10}

# T4 thresholds, fixed before the numbers were seen. Residual share of variance
# left after economy and month effects: below T4_STATIC the panel is a fixed
# structure recoloured by a global factor and the monthly framing is not
# earned; above T4_DYNAMIC economy-specific month-to-month variation is
# substantial; between them the framing is partly earned. A mean 12-month rank
# correlation above T4_STICKY means the ranking barely moves within a year.
T4_STATIC = 0.10
T4_DYNAMIC = 0.30
T4_STICKY = 0.90
T4_LAG = 12

# T2: channel pairs with Spearman above this are reported as near-collinear.
COLLINEAR = 0.9

# Pre-registered expectations. Written from the mechanism, not from the data.
EVENTS = [
    ("2019-09", "Abqaiq strike on Saudi oil processing", "energy",
     "Gulf-dependent oil importers: JPN, KOR, IND, CHN, TWN"),
    ("2022-02", "Russian invasion of Ukraine", "energy",
     "European importers of Russian supply: POL, HUN, DEU, ITA, FIN, TUR"),
    ("2022-08", "Taiwan Strait crisis (Pelosi visit)", "choke",
     "Economies routing through the Taiwan Strait: JPN, KOR, PHL, EU-Asia traders"),
    ("2023-10", "Israel-Gaza war onset", "choke",
     "Red Sea corridor users: EU-Asia traders (DEU, NLD, ITA, POL) via EGY littoral"),
    ("2024-01", "Red Sea shipping attacks", "choke",
     "Same Red Sea corridor, sustained: EU-Asia traders"),
    ("2001-09", "9/11 [ANACHRONISTIC WEIGHTS]", "trade",
     "US-dependent economies: CAN, MEX"),
    ("1990-08", "Iraq invades Kuwait [ANACHRONISTIC WEIGHTS]", "energy",
     "Oil importers exposed to Saudi GPR"),
]

# Strait behind each chokepoint event, for the self-exclusion note. Kept apart
# from EVENTS so the pre-registered tuples above stay exactly as written.
EVENT_STRAIT = {"2022-08": "taiwan_strait", "2023-10": "red_sea", "2024-01": "red_sea"}

BASELINE_MONTHS = 12
TOP_N = 6


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def load_gpr_panel() -> pd.DataFrame:
    """Own-GPR from the SAME source 03 built Intensity from.

    03.load_gpr() takes the fresher of data/processed/gpr_country_monthly.csv
    and the tracked web/data/gpr.json (a clone has only the latter; a working
    tree can hold a CSV one workbook behind it). T1 joins Intensity to own GPR
    month by month, so reading a different panel here would silently shorten
    T1's sample relative to T2-T4 - which is exactly what happened when the
    CSV stopped at 2026-07 while Intensity ran to 2026-08 (n=79 vs T=80). The
    module is loaded by path because its file name starts with a digit."""
    spec = importlib.util.spec_from_file_location(
        "build_intensity", ROOT / "pipeline" / "03_build_intensity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gpr, _source = mod.load_gpr()
    return gpr[gpr["variant"] == "recent"]


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    it = pd.read_csv(PROC / "intensity_monthly.csv", parse_dates=["month"])
    return it, load_gpr_panel()


def load_payload() -> dict:
    p = WEB / "intensity.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_years(payload: dict) -> list[int]:
    """Benchmark years exactly as 03 derives them: trade_weights.csv, with the
    payload's weight_years as the fallback for a tree without the CSV."""
    p = PROC / "trade_weights.csv"
    if p.exists():
        return sorted(int(y) for y in pd.read_csv(p)["year"].unique())
    if payload.get("weight_years"):
        return sorted(int(y) for y in payload["weight_years"])
    raise SystemExit("no benchmark years: need trade_weights.csv or web/data/intensity.json")


def load_littorals() -> dict[str, list[str]]:
    ck = pd.read_csv(REF / "chokepoints.csv")
    return {r.chokepoint: [s for s in str(r.gpr_littoral_states).split(";") if s]
            for r in ck.itertuples()}


# ---------------------------------------------------------------------------
# T1
# ---------------------------------------------------------------------------
def _corr_block(m: pd.DataFrame) -> tuple[float, float, pd.Series]:
    pear = m["rebased"].corr(m["gpr_rebased"])
    spear = m["rebased"].corr(m["gpr_rebased"], method="spearman")
    xs = [g["rebased"].corr(g["gpr_rebased"], method="spearman")
          for _, g in m.groupby("month") if len(g) > 3]
    return pear, spear, pd.Series(xs, dtype=float).dropna()


def t1_discriminant(it: pd.DataFrame, gpr: pd.DataFrame, out: list[str],
                    lo: pd.Timestamp) -> dict[str, tuple[float, float, pd.Series]]:
    """Returns {channel: (pooled Pearson, pooled Spearman, cross-sectional
    Spearman by month)} so main() can publish the summary."""
    out += ["", "=" * 72,
            "T1  DISCRIMINANT VALIDITY - is Intensity just re-plotting GPR?",
            "=" * 72,
            f"  Sample: months >= {lo:%Y-%m}, the first properly lagged vintage. Earlier",
            "  months use contemporaneous or anachronistic weights and are excluded."]
    own = gpr[["iso3", "month", "gpr_rebased"]]
    res: dict[str, tuple[float, float, pd.Series]] = {}
    for ch in CHANNELS:
        sub = it[(it["channel"] == ch) & (it["month"] >= lo)]
        m = sub[["exposed_iso3", "month", "rebased"]].merge(
            own, left_on=["exposed_iso3", "month"], right_on=["iso3", "month"], how="inner")
        if not m.empty:
            res[ch] = _corr_block(m)
    if "trade" not in res:
        out.append("  no overlap")
        return res
    pear, spear, xs = res["trade"]
    out += [f"  Pooled Pearson  own-GPR vs Intensity : {pear: .3f}",
            f"  Pooled Spearman own-GPR vs Intensity : {spear: .3f}",
            f"  Cross-sectional Spearman, mean       : {xs.mean(): .3f}"
            f"   (min {xs.min(): .2f}, max {xs.max(): .2f}, n={len(xs)} months)",
            "  (headline: trade channel, gross basis)",
            "",
            "  Per channel - own GPR (rebased) vs the channel's rebased value:",
            "  channel  pooled Pearson  pooled Spearman  x-sect Spearman mean  (min, max, n months)"]
    for ch in CHANNELS:
        if ch not in res:
            out.append(f"  {ch:<7}  not in panel")
            continue
        pear, spear, xs = res[ch]
        out.append(f"  {ch:<7}  {pear: 14.3f}  {spear: 15.3f}  {xs.mean(): 20.3f}  "
                   f"({xs.min(): .2f}, {xs.max(): .2f}, n={len(xs)})")
    out += ["",
            "  Interpretation: values near +1 would mean the exposure weighting is",
            "  redundant. Values near 0 mean Intensity ranks economies differently",
            "  from source-side GPR - i.e. it carries information GPR does not.",
            "  The chokepoint line is the one a trade-only T1 could not see: the",
            "  littoral mean now excludes the exposed economy's own GPR (03), so a",
            "  value well above the other channels here would mean a leak remains."]
    return res


# ---------------------------------------------------------------------------
# T2
# ---------------------------------------------------------------------------
def _blocs(names: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Connected components of the near-collinear graph: each is one bloc."""
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    return sorted(groups.values(), key=lambda g: (-len(g), g))


def t2_channels(it: pd.DataFrame, out: list[str], lo: pd.Timestamp) -> dict:
    """Returns the near-collinear pairs, the mean off-diagonal Spearman and
    the number of blocs, for the summary file."""
    out += ["", "=" * 72,
            "T2  CHANNEL DISCRIMINATION - are the sliders decorative?",
            "=" * 72,
            f"  Sample: months >= {lo:%Y-%m} (first properly lagged vintage);",
            "  Spearman over economy-months, rebased values."]
    w = (
        it[it["month"] >= lo]
        .pivot_table(index=["exposed_iso3", "month"], columns="channel", values="rebased")
        .dropna(how="all")
    )
    corr = w.corr(method="spearman").round(3)
    out.append(corr.to_string())
    names = list(corr.columns)
    pairs = [(names[i], names[j], float(corr.iloc[i, j]))
             for i in range(len(names)) for j in range(len(names)) if i < j]
    vals = [v for _, _, v in pairs]
    high = [(a, b, v) for a, b, v in pairs if v > COLLINEAR]
    blocs = _blocs(names, [(a, b) for a, b, _ in high])
    out += ["",
            f"  Mean off-diagonal Spearman: {np.mean(vals): .3f}",
            f"  Pairs above {COLLINEAR:.1f}: "
            + (", ".join(f"{a}-{b} {v:.3f}" for a, b, v in high) or "none"),
            f"  Distinguishable channels at that threshold: {len(blocs)} - "
            + "; ".join("/".join(g) for g in blocs)]
    # For each channel outside a multi-member bloc, its range of correlation
    # with the others - the reader can see how far it stands apart.
    for g in blocs:
        if len(g) > 1:
            continue
        ch = g[0]
        others = [v for a, b, v in pairs if ch in (a, b)]
        if others:
            out.append(f"  {ch} vs the other channels: {min(others):.2f}-{max(others):.2f}")
    out += ["",
            "  Interpretation: near +1 across the board would mean the channels are",
            "  the same signal and the mix is cosmetic. A pair above 0.9 is one",
            "  slider wearing two labels, so the honest count of channels is the",
            "  number of blocs above, not the number of sliders."]
    if any({a, b} <= {"trade", "crm", "va"} for a, b, _ in high):
        out += ["  Here trade, the CRM proxy (WITS ores-and-metals import shares) and the",
                "  value-added basis co-move above 0.9: gross import shares of ores and",
                "  metals are near-collinear with gross trade shares, so the CRM slider",
                "  is not yet a fourth independent channel. The material-level CRM",
                "  upgrade (METHODOLOGY 3.3) is what would make it one. Energy and the",
                "  chokepoint channel stand apart and are the channels the mix can",
                "  actually move."]
    return {"pairs_above": high, "mean_offdiagonal": float(np.mean(vals)) if vals else None,
            "distinguishable": len(blocs)}


# ---------------------------------------------------------------------------
# T3
# ---------------------------------------------------------------------------
def t3_events(it: pd.DataFrame, out: list[str], years: list[int],
              littorals: dict[str, list[str]], payload: dict) -> None:
    out += ["", "=" * 72,
            "T3  EVENT STUDIES - pre-registered expectations vs actual top movers",
            "=" * 72]
    first = min(years)
    exposed_choke = set(it.loc[it["channel"] == "choke", "exposed_iso3"].unique())
    payload_excl = payload.get("choke_self_excluded") or {}
    for month_s, label, channel, expectation in EVENTS:
        t = pd.Timestamp(month_s + "-01")
        sub = it[it["channel"] == channel]
        cur = sub[sub["month"] == t].set_index("exposed_iso3")["rebased"]
        base_win = sub[(sub["month"] < t) &
                       (sub["month"] >= t - pd.DateOffset(months=BASELINE_MONTHS))]
        base = base_win.groupby("exposed_iso3")["rebased"].mean()
        if cur.empty or base.empty:
            out += ["", f"  {month_s}  {label}: no data"]
            continue
        # Two metrics, because they disagree and only one is meaningful here.
        # Percentage change explodes for economies whose baseline exposure is
        # near zero, so it ranks the LEAST exposed first - an artifact. Absolute
        # change in index points is comparable across economies and is the
        # metric the expectations were written against.
        abs_d = (cur - base).dropna().sort_values(ascending=False)
        pct_d = ((cur - base) / base * 100).replace([np.inf, -np.inf], np.nan).dropna()
        top_abs = ", ".join(f"{i} {v:+.1f}" for i, v in abs_d.head(TOP_N).items())
        top_pct = ", ".join(f"{i} {v:+.0f}%" for i, v in
                            pct_d.sort_values(ascending=False).head(TOP_N).items())
        out += ["",
                f"  {month_s}  {label}   [channel: {channel}]",
                f"    expected      : {expectation}",
                f"    observed (abs): {top_abs}",
                f"    observed (pct): {top_pct}",
                f"    median abs move: {abs_d.median():+.1f} index points"]
        if channel == "choke" and month_s in EVENT_STRAIT:
            p = EVENT_STRAIT[month_s]
            lit = littorals.get(p, [])
            partial = [s for s in lit if s in exposed_choke and len(lit) > 1]
            dropped = [s for s in lit if s in exposed_choke and len(lit) == 1]
            unexposed = [s for s in lit if s not in exposed_choke]
            note = (f"    self-exclusion at {p}: covered littorals {', '.join(lit) or 'none'}; "
                    f"own GPR removed from the littoral mean for {', '.join(partial) or 'none'}; "
                    f"strait dropped entirely (sole covered littoral) for "
                    f"{', '.join(dropped) or 'none'}")
            if unexposed:
                note += f"; {', '.join(unexposed)} has no chokepoint channel (not a reporter)"
            out.append(note)
            if payload_excl:
                pay_dropped = sorted(i for i, ps in payload_excl.items() if p in ps)
                if pay_dropped != sorted(dropped):
                    out.append(f"    MISMATCH payload choke_self_excluded at {p}: "
                               f"{pay_dropped or 'none'} vs chokepoints.csv {sorted(dropped) or 'none'}")
        # Months in or before the first benchmark year: the vintage does not
        # precede them. In the benchmark year itself the weights are
        # contemporaneous rather than lagged; before it they postdate the month.
        if t.year <= first:
            out.append(f"    WARNING {t.year} <= first benchmark {first} - weights are "
                       f"anachronistic or contemporaneous ({first} vintage)")


# ---------------------------------------------------------------------------
# T4
# ---------------------------------------------------------------------------
def default_mix_series(it: pd.DataFrame) -> pd.DataFrame:
    """Default-mix rebased Intensity as intensityAt() in web/index.html forms
    it: theta-weighted mean over the channels PRESENT for that economy-month,
    gross trade basis. An economy without any mix channel (TWN, va only) has
    no value, exactly as in the interface."""
    w = (it[it["channel"].isin(DEFAULT_MIX)]
         .pivot_table(index=["exposed_iso3", "month"], columns="channel", values="rebased"))
    th = pd.Series({c: float(DEFAULT_MIX[c]) for c in w.columns})
    num = w.mul(th, axis=1).sum(axis=1, min_count=1)
    den = w.notna().mul(th, axis=1).sum(axis=1)
    y = (num / den).dropna()
    return y.rename("rebased").reset_index()


def balanced_panel(df: pd.DataFrame, lo: pd.Timestamp | None) -> pd.DataFrame:
    """Economies x months, keeping only economies observed at every month in
    the window. Two-way demeaning is an exact orthogonal decomposition only on
    a balanced panel, so unbalanced rows are dropped rather than imputed."""
    sub = df if lo is None else df[df["month"] >= lo]
    p = sub.pivot_table(index="exposed_iso3", columns="month", values="rebased")
    p = p.dropna(axis=1, how="all")
    return p.dropna(axis=0, how="any")


def twoway_fe(panel: pd.DataFrame) -> dict[str, float]:
    """Variance shares of y_it = mu + alpha_i + gamma_t + eps_it by two-way
    demeaning. On a balanced N x T panel the economy, month and residual sums
    of squares are orthogonal and add to the total, so
        economy  = SS_alpha / SS_total   (R2 of economy dummies alone)
        month    = SS_gamma / SS_total   (R2 of month dummies alone)
        both     = economy + month       (R2 of the two-way model)
        residual = 1 - both.
    A panel that is exactly additive in economy and month effects returns
    residual 0."""
    y = panel.to_numpy(dtype=float)
    n, t = y.shape
    mu = y.mean()
    a = y.mean(axis=1) - mu
    g = y.mean(axis=0) - mu
    eps = y - mu - a[:, None] - g[None, :]
    ss_tot = float(((y - mu) ** 2).sum())
    if ss_tot == 0.0:
        return {"n": n, "t": t, "economy": np.nan, "month": np.nan,
                "both": np.nan, "residual": np.nan}
    ss_a = t * float((a ** 2).sum())
    ss_g = n * float((g ** 2).sum())
    ss_e = float((eps ** 2).sum())
    return {"n": n, "t": t, "economy": ss_a / ss_tot, "month": ss_g / ss_tot,
            "both": (ss_a + ss_g) / ss_tot, "residual": ss_e / ss_tot}


def rank_mobility(panel: pd.DataFrame, lag: int = T4_LAG) -> pd.Series:
    """Spearman between the cross-sectional ranking at t and at t - lag months,
    for every t whose lagged month is in the panel."""
    cols = set(panel.columns)
    xs = []
    for m in panel.columns:
        prev = m - pd.DateOffset(months=lag)
        if prev in cols:
            xs.append(panel[m].corr(panel[prev], method="spearman"))
    return pd.Series(xs, dtype=float).dropna()


def _t4_table(series: dict[str, pd.DataFrame], lo: pd.Timestamp | None,
              out: list[str]) -> dict[str, dict[str, float]]:
    out.append(f"  {'series':<22} {'N':>3} {'T':>4} {'economy':>8} {'month':>7} "
               f"{'both':>7} {'residual':>9}   rank(t, t-12) mean (min, max, n)")
    got: dict[str, dict[str, float]] = {}
    for name, df in series.items():
        p = balanced_panel(df, lo)
        if p.shape[0] < 4 or p.shape[1] < T4_LAG + 2:
            out.append(f"  {name:<22} insufficient balanced panel ({p.shape[0]} x {p.shape[1]})")
            continue
        fe = twoway_fe(p)
        rm = rank_mobility(p)
        fe["mobility"] = float(rm.mean()) if len(rm) else np.nan
        got[name] = fe
        out.append(f"  {name:<22} {fe['n']:>3} {fe['t']:>4} {fe['economy']:8.3f} "
                   f"{fe['month']:7.3f} {fe['both']:7.3f} {fe['residual']:9.3f}   "
                   f"{rm.mean():.3f} ({rm.min():.2f}, {rm.max():.2f}, n={len(rm)})")
    return got


def _t4_log_line(df: pd.DataFrame, lo: pd.Timestamp | None, out: list[str]) -> None:
    """Robustness: the 'structure x global factor' reading is multiplicative,
    which is additive in logs. Economies with a non-positive value anywhere in
    the window are dropped and counted."""
    p = balanced_panel(df, lo)
    keep = (p > 0).all(axis=1)
    q = np.log10(p[keep])
    if q.shape[0] < 4:
        out.append("  robustness (log10 of the default mix): insufficient positive panel")
        return
    fe = twoway_fe(q)
    out.append(f"  robustness, default mix in log10 (N={fe['n']}, {int((~keep).sum())} "
               f"economies with a non-positive value dropped): economy {fe['economy']:.3f}, "
               f"month {fe['month']:.3f}, residual {fe['residual']:.3f}")


def t4_structure(it: pd.DataFrame, out: list[str], lo: pd.Timestamp,
                 anach_through: str, n_anach: int, n_months: int,
                 first: int) -> dict[str, dict[str, float]]:
    """`first` is the earliest benchmark year, read from trade_weights.csv
    like every other year in the report. Returns the Sample A table."""
    out += ["", "=" * 72,
            "T4  STATIC STRUCTURE OR TIME SERIES? - two-way fixed effects",
            "=" * 72,
            "  y_it = mu + alpha_i + gamma_t + eps_it on the balanced panel (economies",
            "  observed at every month in the window); shares of total variance.",
            f"  'Intensity (default mix)' = theta {DEFAULT_MIX['trade']}/{DEFAULT_MIX['energy']}/"
            f"{DEFAULT_MIX['crm']}/{DEFAULT_MIX['choke']} over trade/energy/crm/choke present,",
            "  rebased, gross trade basis, recomputed here from intensity_monthly.csv."]
    series: dict[str, pd.DataFrame] = {"Intensity (default mix)": default_mix_series(it)}
    for ch in CHANNELS:
        series[ch] = it.loc[it["channel"] == ch, ["exposed_iso3", "month", "rebased"]]

    out += ["", f"  Sample A: months >= {lo:%Y-%m} (first properly lagged vintage)"]
    got_a = _t4_table(series, lo, out)
    _t4_log_line(series["Intensity (default mix)"], lo, out)

    out += ["", f"  Sample B: full sample {it['month'].min():%Y-%m} to {it['month'].max():%Y-%m}",
            f"  CAVEAT: weights are anachronistic or contemporaneous through {anach_through}",
            f"  ({n_anach} of {n_months} months, {n_anach / n_months:.1%}): those months answer",
            "  'who would be exposed given the earliest benchmark structure', so month",
            f"  effects here mix world risk with a frozen {first} dependency map."]
    _t4_table(series, None, out)
    _t4_log_line(series["Intensity (default mix)"], None, out)

    out += ["",
            "  Interpretation: a residual share near zero means Intensity is a fixed",
            "  dependency structure recoloured by a global factor - the cross-section",
            "  differs from GPR (T1) but does not MOVE, and the monthly framing is not",
            f"  earned. Thresholds fixed in advance: residual < {T4_STATIC:.2f} static;",
            f"  {T4_STATIC:.2f}-{T4_DYNAMIC:.2f} partly dynamic; > {T4_DYNAMIC:.2f} substantial",
            "  economy-specific month-to-month variation. Ranking mobility above",
            f"  {T4_STICKY:.2f} means the cross-sectional ranking barely moves within a year."]
    mix = got_a.get("Intensity (default mix)")
    if mix:
        r, mob = mix["residual"], mix["mobility"]
        verdict = ("static structure recoloured by a global factor; the monthly framing is not earned"
                   if r < T4_STATIC else
                   "partly dynamic: most variance is economy structure plus a common month factor, "
                   "but a material share is economy-specific movement"
                   if r < T4_DYNAMIC else
                   "substantial economy-specific month-to-month variation; the monthly framing is earned")
        out += ["",
                f"  Verdict (Sample A, default mix): residual {r:.3f} -> {verdict}.",
                f"  Ranking mobility {mob:.3f} -> "
                + ("the ranking barely moves within a year." if mob > T4_STICKY
                   else "the ranking does move within a year.")]
    return got_a


# ---------------------------------------------------------------------------
def main() -> None:
    it, gpr = load()
    payload = load_payload()
    years = load_years(payload)
    first = min(years)
    # First properly lagged vintage: the first year strictly greater than the
    # earliest benchmark year. Months in or before that year are excluded from
    # T1/T2/T4 Sample A (see module doc).
    lo = pd.Timestamp(year=first + 1, month=1, day=1)
    months = sorted(it["month"].unique())
    anach = [m for m in months if pd.Timestamp(m).year <= first]
    anach_through = pd.Timestamp(max(anach)).strftime("%Y-%m") if anach else "none"
    pay_through = payload.get("weights_anachronistic_through")
    agree = ("payload agrees" if pay_through == anach_through
             else f"MISMATCH payload says {pay_through!r}") if payload else "no payload to check"

    out = ["Intensity index - validation report",
           f"generated {pd.Timestamp.today():%Y-%m-%d}",
           f"months {it['month'].min():%Y-%m} to {it['month'].max():%Y-%m}, "
           f"{it['exposed_iso3'].nunique()} economies, "
           f"channels: {', '.join(sorted(it['channel'].unique()))}",
           f"own-GPR panel through {gpr['month'].max():%Y-%m}, the source 03 built Intensity from "
           f"(fresher of gpr_country_monthly.csv and web/data/gpr.json), so T1 and T4 share one sample",
           f"benchmark years {', '.join(map(str, years))} (trade_weights.csv); "
           f"weights properly lagged from {lo:%Y-%m}; T1/T2/T4 Sample A use months >= {lo:%Y-%m}",
           f"weights anachronistic or contemporaneous through {anach_through}: "
           f"{len(anach)} of {len(months)} months ({len(anach) / len(months):.1%}) "
           f"use the {first} benchmark - {agree}"]
    littorals = load_littorals()
    excl = payload.get("choke_self_excluded")
    if excl is not None:
        out.append("payload choke_self_excluded (strait dropped from own channel, sole covered "
                   "littoral): " + (json.dumps(excl) if excl else "none"))
        # Recomputed from the tracked littoral table over ALL six straits, not
        # only the two behind T3's chokepoint events (where nothing is ever
        # dropped): the rule is "the economy is the strait's only GPR-covered
        # littoral", over the economies that have a trade channel, which is the
        # set 03 builds chokepoint rows for. Hormuz and the Bosphorus are the
        # pairs that actually exist, and this is the line that checks them.
        present = set(gpr["iso3"].unique())
        exposed_trade = set(it.loc[it["channel"] == "trade", "exposed_iso3"].unique())
        sole: dict[str, list[str]] = {}
        for pnt, states in littorals.items():
            covered = [s for s in states if s in present]
            if len(covered) == 1 and covered[0] in exposed_trade:
                sole.setdefault(covered[0], []).append(pnt)
        sole = {k: sorted(v) for k, v in sorted(sole.items())}
        got = {k: sorted(v) for k, v in sorted((excl or {}).items())}
        out.append("recomputed from chokepoints.csv over all six straits (covered littorals "
                   "with a GPR series, economies with a trade channel): "
                   + (f"MISMATCH payload {json.dumps(got)} vs recomputed {json.dumps(sole)}"
                      if got != sole else f"{json.dumps(sole)} - payload agrees"))
    t1 = t1_discriminant(it, gpr, out, lo)
    t2 = t2_channels(it, out, lo)
    t3_events(it, out, years, littorals, payload)
    t4 = t4_structure(it, out, lo, anach_through, len(anach), len(months), first)
    text = "\n".join(out)
    OUT.write_text(text)
    print(text)
    write_summary(it, gpr, lo, t1, t2, t4, anach_through, len(anach), len(months))


def _r3(x) -> float | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 3)


def write_summary(it: pd.DataFrame, gpr: pd.DataFrame, lo: pd.Timestamp,
                  t1: dict, t2: dict, t4: dict, anach_through: str,
                  n_anach: int, n_months: int) -> None:
    """web/data/validation.json: the handful of figures web/story.html quotes,
    at the report's own precision (three decimals). The story page used to
    carry them as typed text, which the monthly refresh could not update; now
    it reads this file, and the verifier fails if it disagrees with the report.
    Nothing here is computed afresh - every value is the one just printed."""
    per_ch = {ch: _r3(xs.mean()) for ch, (_, _, xs) in t1.items()}
    pear, spear, xs = t1.get("trade", (np.nan, np.nan, pd.Series(dtype=float)))
    mix = t4.get("Intensity (default mix)") or {}
    choke = t4.get("choke") or {}
    summary = {
        "kind": "validation_summary",
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "months_through": f"{it['month'].max():%Y-%m}",
        "n_months_total": n_months,
        "n_economies": int(it["exposed_iso3"].nunique()),
        "sample_start": f"{lo:%Y-%m}",
        "t1": {"cross_sectional_mean": _r3(xs.mean()) if len(xs) else None,
               "n_months": int(len(xs)),
               "pooled_pearson": _r3(pear), "pooled_spearman": _r3(spear),
               "per_channel": per_ch},
        "t2": {"pairs_above_0_9": [[a, b, _r3(v)] for a, b, v in t2.get("pairs_above", [])],
               "mean_offdiagonal": _r3(t2.get("mean_offdiagonal")),
               "distinguishable_channels": t2.get("distinguishable")},
        "t4": {"residual_share": _r3(mix.get("residual")),
               "month_share": _r3(mix.get("month")),
               "economy_share": _r3(mix.get("economy")),
               "ranking_mobility": _r3(mix.get("mobility")),
               "choke_ranking_mobility": _r3(choke.get("mobility"))},
        "anachronistic": {"through": anach_through, "n": n_anach,
                          "share": _r3(n_anach / n_months) if n_months else None},
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=1) + "\n")
    print(f"\nwrote {SUMMARY}")


if __name__ == "__main__":
    main()
