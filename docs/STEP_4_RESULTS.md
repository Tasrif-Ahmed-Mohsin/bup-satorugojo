# Step 4 — continuous LP optimizer

Completed locally on 18 September 2026 after the user approved Step 4 only. No language-model
call, no deployment, and no remote repository write occurred in this step. The source-linked
design in `STEP_2_DESIGN.md` governs the formulation.

## What was built

| File | Role |
|---|---|
| `app/optimizer.py` | Signed-flow continuous LP, exact schedule reconstruction, grounded summary, and the solve/serialize/decode/replay boundary |
| `tests/test_optimizer.py` | 54 checks: ten public cost comparisons, analytical optima, directive boundaries, infeasibility, and a seeded randomized sweep |
| `scripts/solve_samples.py` | Offline LP solve and reference cost comparison with an optional JSON report |
| `requirements.txt` | Adds the pinned `numpy==2.5.3` and `scipy==1.16.2` actually installed and used |

The model is exactly the one recorded in `STEP_2_DESIGN.md`: 96 continuous variables — grid import
`g`, solar use `s`, signed battery change `b` and end-of-hour energy `E` for each of 24 hours —
minimising `SUM(tariff[h] * g[h])` subject to the hourly balance, the state transition, and final
energy equal to initial energy. Negative lower bounds are set explicitly for `b`, because SciPy's
default nonnegative bounds would silently prohibit discharging. No binary variables, conversion
efficiency, degradation term or peak penalty was introduced.

## Checks actually run

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.solve_samples --report tmp/step_4_lp_report.json
.\.venv\Scripts\python.exe -m scripts.check_samples
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

- **240 tests passed** (186 existing plus 54 new), 2.48 seconds. The two upstream test-client
  deprecation warnings remain; no failures.
- **10/10 public cases solved and matched.** Every recalculated cost equalled the reference cost
  with a difference of exactly `0.0`, not merely inside the published 0.01 BDT tolerance:
  38365, 42885, 35480, 40495, 33950, 34090, 38550, 37665, 34873 and 41620 BDT.
- Each generated response was serialized, decoded, and replayed against the organizer's
  independently annotated directives (`trusted_directives`); all ten passed.
- **10/10 reference replays still pass** (18 notes, 240 hours); the Step 3 behaviour is unchanged.
- Solve plus full replay took **about 4 ms per case** on this machine (14.7 ms on the first case,
  which includes SciPy warm-up). This is a local measurement, not an end-to-end API latency.
- Ruff passes. `pip check` reports no broken requirements.

### Randomized robustness sweep

600 synthetic scenarios with random demand, solar, tariffs (including zero tariffs), battery
parameters and 1–3 random directives produced **473 schedules that all passed independent replay**,
**91 controlled `infeasible_scenario` errors** and **36 directive rejections**. No `solver_failed`
result, uncontrolled exception or replay failure occurred. A seeded 150-case version of this sweep
is part of the test suite.

## Design decisions made in this step

- **Exact reconstruction instead of trusting solver output.** Grid import is derived from the hourly
  balance and battery energy from the running total of the emitted battery movements, so both
  identities hold by construction rather than by solver tolerance. Solver values that disagree with
  this reconstruction by more than 1e-6 are rejected rather than published.
- **Tie-breaking only when it is free.** Zero or equal tariffs leave the cost objective indifferent
  between paid grid import and free solar, so a cost-optimal schedule can still contain pointless
  imports. A second pass minimises total grid energy while holding cost at the optimum. Minimising
  imports is *not* a stated objective and it directly opposes battery arbitrage, so the refined
  schedule is kept only when it costs no more than the first. An earlier version allowed the
  constraint's feasibility slack to act as a cost allowance and inflated an analytical optimum by
  5.6e-7 BDT; that is fixed and covered by tests.
- **Errors stay static.** `OptimizerError` carries fixed codes (`infeasible_scenario`,
  `solver_failed`, `invalid_schedule`) and never includes scenario or operator-note text.
- **The summary is derived, not generated.** It reports directive counts, checked totals, battery
  cycling and curtailment. It never echoes operator-note text, which is untrusted input.
- **Nothing is returned unchecked.** `optimize_scenario` returns the decoded payload that passed
  replay. Recomputing or reformatting any field afterwards would publish something the checker
  never saw.

## Limits of this evidence

- **The optimizer is not wired into the API.** Step 4 was scoped to the solver and its isolated
  tests, so `/health` still returns 503/`not_ready` and a valid `/optimize-energy` request still
  returns the controlled 500/`pipeline_not_ready`. Integration is Step 6.
- **No language model is in the path yet.** All ten comparisons used the organizer's structured
  directives as trusted test input. This establishes optimizer correctness, not interpretation
  accuracy. Public phrases, case identifiers and reference schedules are still never consulted by
  application code.
- **Optimality is optimality of the formulated program.** Matching all ten published costs exactly
  is strong evidence the formulation matches the organizer's, but it is not a proof about hidden
  cases.
- **Equal-cost schedules are not unique.** On SAMPLE-01 our plan has `peak_grid_kwh` 187.5 where the
  reference has 175, at identical cost (38365 BDT) and identical total grid (2692.5 kWh). The source
  checklist states the judge verifies that `total_grid_kwh`, `total_cost_bdt` and `peak_grid_kwh`
  "match values recalculated from hourly_plan" (P p.8), so peak is a self-consistency check on our
  own plan, which replay enforces. It is not an additional objective, and the rules state none.
- No latency, reliability or deployment claim is made. Nothing was pushed, deployed or published.

## Next checkpoint: Step 5, pending approval

Real DeepSeek note interpretation with strict guardrails, bounded retries and deadlines, then
measured accuracy against the public notes and independent paraphrases. That step spends credit and
makes real external calls, so it needs the user's explicit go-ahead.
