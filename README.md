# GridWise

GridWise turns campus operator notes written in ordinary language into a validated, minimum-cost 24-hour electricity schedule.

```
request -> real DeepSeek interpretation -> deterministic guardrails -> linear program -> independent replay -> response
```

A real generative model is the only component that reads human language. Its output is treated as untrusted structured data: it is parsed strictly, validated deterministically, turned into optimizer constraints, and the finished schedule is serialized, decoded and independently replayed before anything is returned. No public sample phrase, scenario identifier or reference schedule is ever consulted by application code.

## Endpoints

| Endpoint | Behaviour |
|---|---|
| `GET /` | A small demo page for humans: edit the operator notes in plain English, run them, and see the interpretations, the 24-hour plan and the cost. It calls the same public `/optimize-energy` a judge calls and has no privileged path of its own. Excluded from the OpenAPI schema. |
| `GET /health` | `200` with `{"status":"ok"}` once the provider configuration is present and the solver has imported. `503` with `{"status":"not_ready"}` otherwise. |
| `POST /optimize-energy` | `200` with the interpretations, 24 hourly decisions, recomputed totals and a short summary. `400` for malformed or structurally invalid input. `500`, controlled and sanitized, for provider, interpretation, solver or replay failure. |

Error bodies are `{"error": {"code": ..., "message": ...}}`. They never contain input values, stack traces or credentials. A provider failure is never converted into fabricated `no_op` entries, and a directive is never relaxed to manufacture a successful response.

## Setup

Requires Python 3.12 and a DeepSeek API key.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env    # then set DEEPSEEK_API_KEY in .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Linux use `python3.12 -m venv .venv`, `cp .env.example .env`, and `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

### Configuration

Only `DEEPSEEK_API_KEY` is required. Everything else has a working default.

| Variable | Default | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | *(none)* | Provider credential. Without it `/health` stays `503` and the service never invents a schedule. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Provider endpoint. |
| `DEEPSEEK_MODEL` | `deepseek-flash` | Interpretation model. |
| `GRIDWISE_REQUEST_DEADLINE` | `25` | Seconds for the whole request, inside the published 30-second limit. |
| `GRIDWISE_MODEL_PHASE` | `20` | Seconds for the interpretation phase, including retries. |
| `GRIDWISE_MODEL_ATTEMPT` | `9` | Seconds for one provider attempt. |
| `GRIDWISE_MAX_ATTEMPTS` | `2` | At most one retry, never a hidden chain of provider-side retries. |
| `GRIDWISE_MAX_OUTPUT_TOKENS` | `1024` | Output allowance for up to three directive records. |

The key is read from the environment, or from a local `.env` for convenience. It is never logged, echoed, returned, committed or copied into the image. `.env` and private-key patterns are excluded from Git and the Docker build context; those exclusions do not encrypt local files.

## Live deployment

The service runs on an Azure Ubuntu 24.04 VM (Central India, Standard D2as v4) in Docker, published on port 80:

| | |
|---|---|
| Demo page | `http://20.193.131.121/` |
| Health | `http://20.193.131.121/health` |
| Optimize | `http://20.193.131.121/optimize-energy` |

```bash
curl -i http://20.193.131.121/health
curl -s -X POST http://20.193.131.121/optimize-energy -H 'Content-Type: application/json' --data @examples/sample_request.json
```

`examples/sample_request.json` is a complete, self-contained scenario written for this project. Its three notes exercise a solar reduction ("11 AM to 1 PM ... about 30%" becomes hours `[11, 12]` with factor `0.3`), a reserve ("from 6 PM until 9 PM" becomes hours `[18, 19, 20]` at 150 kWh) and a distractor that is correctly returned as `no_op`.

No login, VPN or manual step is needed to reach it. The container uses `--restart unless-stopped` and the Docker service is enabled at boot, so the endpoint returns after a VM restart.

## Docker

The image contains no credential; the key is supplied at run time.

```bash
docker build -t gridwise:1.1.0 .
docker run -d --name gridwise --restart unless-stopped -p 80:8000 -e DEEPSEEK_API_KEY=your-key-here gridwise:1.0.0
curl -i http://localhost/health
```

The container listens on `0.0.0.0:8000`, runs as an unprivileged user, and carries a `HEALTHCHECK` that polls `/health`.

### Published image

The image is public on Docker Hub and requires no login to pull:

| | |
|---|---|
| Tag | `tasrifahmed/gridwise:1.1.0` (also `:latest`) |
| Digest | `sha256:e71f2661443313c97e6b341c72e94ec0ff0fad42e217b47ad3d1bdb00cb0cd1f` |

```bash
docker pull tasrifahmed/gridwise:1.1.0
docker run -d --name gridwise -p 80:8000 -e DEEPSEEK_API_KEY=your-key-here tasrifahmed/gridwise:1.1.0
curl -i http://localhost/health
```

To pin the exact build, pull by digest:

```bash
docker pull tasrifahmed/gridwise@sha256:e71f2661443313c97e6b341c72e94ec0ff0fad42e217b47ad3d1bdb00cb0cd1f
```

Anonymous pull access was verified against the registry with no credentials: the manifest for `1.1.0` returns HTTP 200 and the digest above. This is the same image currently serving the public endpoint.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_samples
.\.venv\Scripts\python.exe -m scripts.solve_samples
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

Tests require no credentials and spend no credit: the provider boundary is exercised with a stub transport. The two sample scripts read the organizer pack offline; `check_samples` replays the published reference schedules and `solve_samples` solves each case with the LP and compares cost. Neither is imported by the application.

One further script does make real, paid provider calls and is therefore never part of the test run:

```powershell
.\.venv\Scripts\python.exe -m scripts.measure_interpretation --report tmp/interpretation.json
```

### Measured results, 18 September 2026

| Check | Result |
|---|---|
| `pytest -q` | **257 passed**, 2.5 s |
| Reference replay (`check_samples`) | **10/10** references valid, 18 notes, 240 hours |
| LP cost comparison (`solve_samples`) | **10/10** public costs reproduced exactly (difference `0.0`), ~4 ms per solve |
| Real-model interpretation (`measure_interpretation`) | **18/18** public notes and **20/20** independent paraphrases correct; interpretation p95 1.20 s |
| End-to-end over live HTTP | **10/10** cases returned `200` with valid schedules and exact reference costs |
| Readiness | `/health` answered `200 ok` **1.04 s** after process start (target ≤ 60 s) |
| Request latency | mean 0.88 s, **p95 1.35 s**, max 1.35 s (target ≤ 5 s for full marks) |

Against the **deployed public endpoint** at `http://20.193.131.121`, measured from a separate machine over the internet: `/health` answered `200 ok` **0.15 s** after a container restart, all **10/10** cases returned `200` with valid schedules and exact reference costs, request latency was median 1.15 s and **p95 1.38 s**, and malformed JSON and a structurally invalid body both returned `400` with no input echoed. Under concurrent load, 30 requests at concurrency 5 and 30 more at concurrency 10 gave **60/60 valid**.

The **first** request to a fresh container originally took 8.09 s, because HiGHS pays a one-off setup cost on its first solve and the provider connection had to be opened. Startup now performs a throwaway solve and opens the provider connection before reporting ready, which brought the first request down to **1.12 s**. That startup probe lists models; it runs no inference and spends no tokens.

These runs were sequential on one machine. They are not a load test and do not measure behaviour under concurrent judging traffic.

## Modules

| Module | Responsibility |
|---|---|
| `app/main.py` | Two exact routes, readiness, request deadline, sanitized error handling |
| `app/config.py` | Environment settings and deadline budgets; credential values never logged |
| `app/interpreter.py` | DeepSeek request, strict JSON parsing, bounded retries; notes passed as delimited data |
| `app/schemas.py` | Required fields, strict finite numbers, 24-hour coverage, battery consistency, directive shapes, response ordering |
| `app/directives.py` | One interpretation per note, reserve guardrails, safe hour sorting, hourly operating bounds |
| `app/optimizer.py` | Signed-flow continuous LP over 96 variables, exact schedule reconstruction, grounded summary |
| `app/replay.py` | Independent energy, directive, state, rate, neutrality and aggregate checks, without the bounds builder |
| `app/jsonio.py` | JSON parsing and serialization with no duplicate keys, NaN, Infinity or blanket rounding |
| `scripts/` | Offline reference checks, LP cost comparison and real-model accuracy measurement; none imported by the app |

## How the schedule is computed

For each hour the program uses grid import `g`, solar use `s`, signed battery change `b` and end-of-hour energy `E` — 96 continuous variables. Positive `b` charges, negative discharges, so one action per hour falls out without binary variables.

```
minimize  SUM(tariff[h] * g[h])

g[h] + s[h] - b[h] = demand[h]
E[0] - b[0] = initial_energy
E[h] - E[h-1] - b[h] = 0          for h = 1..23
E[23] = initial_energy

0 <= g[h] <= active grid cap       (unbounded above with no cap)
0 <= s[h] <= effective solar
active reserve <= E[h] <= capacity
-max_discharge <= b[h] <= max_charge
```

Negative lower bounds for `b` are set explicitly, because a solver's default nonnegative bounds would silently forbid discharging. The published model is lossless, so no efficiency factor, degradation cost, integer variable or peak penalty is introduced. Cost is the only stated objective; peak grid usage is a reported metric.

Grid import is then derived from the hourly balance and battery energy from the running total of the emitted movements, so both identities hold by construction rather than by solver tolerance. Solver output that disagrees with that reconstruction by more than 1e-6 is rejected rather than published.

## Rules this implementation follows

Multiple reserves combine by maximum, grid caps by minimum, and prohibition windows by union. Identical overlapping solar factors apply once. **Different overlapping solar factors fail explicitly**, because the supplied rules do not define how to combine them; inventing a merge rule would be a guess presented as an answer. Time windows include the start hour and exclude the end. A reserve constrains energy *after* each listed hour. Solar may be curtailed; grid export is not modelled. An 80% reduction leaves factor 0.2.

Comparisons use absolute tolerance only, defaulting to the published 0.01 kWh / 0.01 BDT. Tests check the public references at 1e-9 and analytical optima at 1e-9. A dimensionless solar factor is compared at 1e-12, because a kWh tolerance is not a factor tolerance. Fields are not blanket-rounded to two decimals.

Input metadata outside the required fields is ignored. Numeric strings, booleans as numbers, nonfinite values, negative quantities and inconsistent battery bounds are rejected. Zero capacity and zero rates are allowed. Request hours may arrive unordered; output hours are always chronological.

## Status and remaining work

Implemented and measured: contracts, guardrails, real interpretation, the optimizer, independent replay, the wired API, and the Dockerfile.

Outstanding: the submission video. Cross-midnight and equal-start-end time windows remain unresolved in the supplied rules and are not claimed as answered.

## Credits and sources

The original problem statement, participant guide and public sample pack are preserved under `BUP_CSE_FEST_2026_Participant_Docs/`, with searchable text copies under `readable_rules/`; the original PDFs remain authoritative. The reference pack is used only for local verification and tests.

Built with [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, [Pydantic](https://docs.pydantic.dev/latest/concepts/strict_mode/), [SciPy `linprog` with HiGHS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html), NumPy, HTTPX, pytest and Ruff. Interpretation uses the hosted [DeepSeek API](https://api-docs.deepseek.com/) with [JSON output mode](https://api-docs.deepseek.com/guides/json_mode/) and thinking disabled. AI coding assistants (Codex, Claude Code) assisted with design, implementation and review; the team owns and must be able to explain the submitted architecture and logic.

See `STEP_2_DESIGN.md` for the source-linked requirement table, `STEP_3_RESULTS.md` and `STEP_4_RESULTS.md` for staged evidence, and `WORK_PLAN.md` for the plan.
