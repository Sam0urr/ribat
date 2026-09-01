---
name: ribat-verify
description: >
  Verify the Ribat repository before any commit, push, or publish: compile all
  pipeline stages, syntax-check the inline front-end JS, validate the web
  payload contracts (kind, month grid, country arrays, coverage, stale-weight
  flags), scan for banned residual tokens from the GRE-era naming, and confirm
  licence/attribution files are intact. Use whenever pipeline/, web/, or the
  payload schema changed, when preparing a commit, or when asked to "verify",
  "check", or "run the checks" on this project.
---

# ribat-verify

Run the deterministic check suite:

```bash
python3 .claude/skills/ribat-verify/verify.py
```

Exit code 0 with `ALL CHECKS PASSED` is the only acceptable pre-commit state.

## What it checks, and what a failure means

1. **Python compilation** — every `pipeline/*.py` byte-compiles. Failure:
   syntax error; fix before anything else.
2. **Inline JS syntax** — the last `<script>` block of `web/index.html` passes
   `node --check`. Failure: the map will not load at all.
3. **Payload contract** — for each JSON payload in `web/data/`:
   `kind` is one of the values the front-end loader dispatches on; `months`
   strictly increasing `YYYY-MM`; every per-country series has exactly
   `len(months)` entries of numbers/nulls; `covered` in [0, 1] where present;
   `stale_weights` entries name real countries. Failure: the front end will
   silently mis-render — this is the class of bug (silent fallback, dropped
   countries) that has bitten this project before.
4. **Coverage counts** — expected number of GPR source series (44) and a sane
   number of exposed economies (>= 40). Failure: a join regressed.
5. **Banned tokens** — no residual GRE-era names (word-bounded GRE, gre.json,
   gre_monthly) and no Mapbox GL imports anywhere in tracked source. Failure:
   naming or stack regression.
6. **Licence and attribution** — LICENSE and SOURCES.md exist and still carry
   the Caldara-Iacoviello citation. Failure: CC-BY obligation broken; blocks
   publish.

## Rules

- Never mark work done while this fails; fix or explicitly report the failure.
- If a check is wrong because the schema legitimately evolved, update
  verify.py and CLAUDE.md in the same commit as the schema change.
- After changing 03_build_intensity.py, also re-run
  `python3 pipeline/04_validate.py` and read the report — a validation
  regression is a finding to surface, not noise to suppress.
