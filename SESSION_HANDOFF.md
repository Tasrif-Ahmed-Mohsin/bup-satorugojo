# GridWise session handoff

Snapshot: **18 September 2026, about 8:21 PM Bangladesh time (UTC+6)**.
Workspace: **`E:\bup prili`**, Windows, PowerShell.
User-confirmed event deadline: **18 September 2026 at 11 PM Bangladesh time**.
If resuming after that date/time, confirm the current event situation before relying on this deadline.

## Current position

**Steps 1 and 2 are complete. Steps 3 and 4 are complete locally. Step 5 has not started and is awaiting approval.**

The project has validated schemas, directive guardrails, an independent schedule checker, the continuous LP optimizer, tests, dependencies and an API scaffold. **There is no real LLM integration yet, the optimizer is deliberately not wired into the route, and no deployment was performed by the assistant.** Read `STEP_4_RESULTS.md` first for the newest evidence and limits.

The user's priorities are to understand the problem and rules, avoid invented requirements, build thoughtfully according to the saved plan, and ask before each next stage. Deployment is explicitly a later job. Continue from existing files; do not restart planning or overwrite the user's work.

## What the user is building

BUP CSE Fest 2026 GridWise preliminary: one public JSON API receives 24 hourly demand/solar/tariff entries, battery parameters and 1–3 operator notes. A real generative language model must interpret every note. Deterministic code validates the structured directives; a mathematical optimizer schedules energy; independent replay checks the complete returned result.

Required final endpoints:

- `GET /health`: HTTP 200 containing `{"status":"ok"}` when ready.
- `POST /optimize-energy`: interpretations, a valid minimum-cost 24-hour plan, totals and a short summary.

Only using AI to write a summary, or replacing interpretation with a phrase lookup, does not meet the mandatory LLM requirement. Public examples must never become application answer lookups.

## Read these files first

1. `STEP_3_RESULTS.md` — actual completed work, test evidence, limitations and next checkpoint.
2. `STEP_2_DESIGN.md` — exact schemas, 31 source-linked requirements, mathematical formulation, provider design and unresolved rules. This records historical Step 2 decisions; its old prerequisites/tree should be interpreted alongside the newer results.
3. `WORK_PLAN.md` — priority targets and the step-by-step sequence. The current checkpoint at its beginning supersedes historical prompts below it.
4. `README.md` — current setup, verification commands and truthful API status.
5. `app/`, `tests/`, `scripts/` — inspect the implemented code before editing.
6. Original sources and searchable copies when resolving any rule question.

Original files, unchanged, under `BUP_CSE_FEST_2026_Participant_Docs/`:

- `BUP_CSE_FEST_2026_Preliminary_Problem_Statement_GridWise_LLM.pdf` — 9 pages.
- `BUP_CSE_FEST_2026_Participant_Guide_&_Evaluation_Rubric_GridWise_LLM.pdf` — 11 pages.
- `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json` — version 2.0, 10 cases, 18 notes, 240 hours.

Searchable conversions under `readable_rules/`: `GridWise_Problem_Statement.txt`, `GridWise_Participant_Guide_and_Rubric.txt`, and combined `GridWise_All_Rules.txt`. All 20 PDF pages were checked for text completeness. These are text versions, not Word documents; original PDFs remain authoritative. The guide's visibly incomplete scoring sentence was flagged, not reconstructed. A separate rulebook mentioned by the guide was not supplied.

## Implemented and verified

| File | Existing implementation |
|---|---|
| `app/schemas.py` | Pydantic request/response/directive models; strict finite numbers; note/hour coverage; battery consistency; exact outgoing shapes/order |
| `app/directives.py` | Deterministic validation and hourly limits; supported combinations; sanitized failures |
| `app/replay.py` | Independent physical, directive, state, rate, neutrality and aggregate checks; optional trusted interpretation comparison |
| `app/jsonio.py` | Strict JSON parsing/serialization; rejects duplicate keys and NaN/Infinity literals |
| `app/main.py` | Exact route names, OpenAPI schemas, sanitized invalid-input handling; deliberately incomplete pipeline |
| `scripts/check_samples.py` | Offline validation of organizer reference schedules, not a solver or endpoint evaluation |
| `tests/` | Contract, malformed-input, directive, replay and regression tests |
| `requirements.txt` | Pinned installed dependencies, including test tools |

Last observed verification:

- **186 tests passed**, final run 0.47 seconds.
- **10/10 reference schedules passed**, covering **18 notes and 240 hours**.
- Ruff passed; `pip check` found no dependency conflicts.
- Two upstream test-client deprecation warnings remain; no test failures.
- Git/Docker exclusions cover `.env`, private-key patterns, the virtual environment and scratch files. The staged secret-pattern scan passed; this is not a guarantee against every possible secret format.
- Original sample file and staged Git blob were verified byte-for-byte equal; SHA-256: `fa6abd71868e0faf429a87429d7d4a2b7bfd38c5551565637498d7fec68d5f32`.

Two independent-review findings were fixed with regression tests: alternating small state errors could conceal a larger adjacent battery-transition error; trusted-only checks could combine extraction and application tolerances into an excessive violation of a reported directive. The checker now verifies both cumulative and adjacent states, and both reported and trusted constraints when annotations are supplied.

**These results establish contract/checker behavior and reference validity. They do not establish generated-plan optimality, LLM accuracy, live API readiness or deployment performance.**

Current intentional API behavior: `/health` returns **503/not_ready**; a structurally valid optimization request returns **500/pipeline_not_ready**. Malformed or structurally invalid requests return sanitized **400**. Do not claim the service is ready or switch health to success before actual integration.

## Next implementation: Step 4

Use Python 3.12 and SciPy `linprog(method="highs")` to implement a continuous LP. SciPy has not been installed or used in this project yet; add and pin it after checking compatibility.

For each hour use grid import `g`, solar use `s`, signed battery change `b` and end-of-hour energy `E`: 96 continuous variables. Positive `b` charges; negative `b` discharges.

```text
Minimize SUM(tariff[h] * g[h])
g[h] + s[h] - b[h] = demand[h]
E[0] - b[0] = initial_energy
E[h] - E[h-1] - b[h] = 0 for h=1..23
E[23] = initial_energy

0 <= g[h] <= active grid cap (otherwise unrestricted above)
0 <= s[h] <= effective solar
active reserve <= E[h] <= capacity
-max_discharge <= b[h] <= max_charge
```

No-charge sets `b` upper bound to zero; no-discharge sets its lower bound to zero; both force idle. Set negative lower bounds explicitly: the solver's default nonnegative bounds would prohibit discharge. The stated lossless model needs no binary variables, efficiency assumptions, degradation cost or peak penalty.

Use trusted structured directives only for isolated Step 4 tests. Require successful optimal solver status, construct the complete response, serialize at sufficient precision, decode and replay it, and return the checked payload unchanged. Compare semantic validity and total cost with the references, not the exact action sequence. Test analytical cases including forced solar curtailment and tight reserves/grid caps. No real-model calls or deployment in Step 4.

Existing interfaces:

```python
ScenarioRequest.model_validate(raw_request)
OptimizationResponse.model_validate(raw_response)
validate_directives(scenario, {"directive_interpretation": raw_entries})
build_hourly_bounds(scenario, validated_directives)
replay_response(scenario, decoded_response, tolerance=0.01, trusted_directives=None)
```

Read the actual definitions before using them. Replay does not call the optimizer's bounds builder; preserve that independence.

## Rules most likely to cause mistakes

- Exactly one interpretation per note in index order; only the five active directive types and `no_op` are supported.
- `no_op` is false/null; active directives are true with exact adjustment shapes.
- Hours are unique integers 0–23, returned sorted. Time windows include the start and exclude the end.
- An 80% solar reduction leaves factor **0.2**. Percentage reserve uses total capacity.
- Reserves constrain energy **after the listed hour**. Curtailment is permitted; grid export is not.
- Preserve base demand, tariff and battery parameters. One battery action per hour; final energy must equal initial energy.
- Cost is grid energy times tariff; peak grid usage is a reported metric, not another objective.
- Published tolerance is absolute 0.01 kWh/BDT; retain precision rather than rounding all fields to two decimals.
- Multiple reserves use maximum, grid caps use minimum, and prohibitions use union. Identical solar factors are idempotent. **Different overlapping solar factors are unspecified and currently fail explicitly.** Do not invent a merge rule.
- Cross-midnight/equal-start-end interpretation remains unresolved. Do not claim an organizer answer that was not supplied.
- Final health readiness must be within 60 seconds; each request within 30 seconds; p95 <=5 seconds earns full latency marks. These targets have not been tested yet.

## Accounts, credentials and hosting

**Provider:** user selected hosted DeepSeek and reported **USD 1.50 credit**. No paid calls have occurred. Earlier planning selected `deepseek-flash`, thinking disabled, JSON object output; verify current official support and actual account access in Step 5. Gemini was discussed but is not integrated or required for the first version.

`DEEPSEEK_API_KEY` was saved with user authorization in local `.env`, excluded from Git/Docker and protected by Windows permissions. It is plaintext, not encrypted. Do not print it, copy it into a handoff, commit it, log it or request it again. API credentials were previously posted in chat; rotation before deployment remains advisable. `.env.example` contains names only. No SSH key contents were read.

**GitHub:** user supplied an already-created repository:
`git@github.com:Tasrif-Ahmed-Mohsin/bup-satorugojo.git`.

Local Git is initialized on `main`; project files are staged, with **no local commit or push yet**. Remote `origin` is configured. SSH access failed with `Permission denied (publickey)`. GitHub CLI reported no signed-in account. Anonymous metadata returned 404, which does not verify repository visibility or creation time. The configured Git author email is a placeholder; confirm the user's intended identity before the first commit. Do not invent it or change global configuration silently.

The user can authenticate locally with `gh auth login`; then verify the intended account, repository access, remote history and private visibility. If using HTTPS authentication, explicitly account for the currently configured SSH remote. Never force-push or overwrite unknown remote history. The organizer requires creation after reveal, private visibility during the event and public visibility after the deadline; no visibility change was made or scheduled.

**Azure:** user chose a single VM, not VMSS, and is creating it manually. Actual VM creation, region, public IP and current state are unverified. No SSH connection or deployment has occurred. The workspace contains `bupXict_key.pem`; leave it local and ignored.

Suggested configuration was Ubuntu 24.04 LTS x64, regular non-Spot VM, 2 vCPU and at least 4 GiB RAM, managed Standard SSD OS disk 32 GiB or the image's larger minimum, no data disk and no GPU. Among visible sizes, B2as_v2 (2 vCPU/8 GiB) was recommended as the cheaper shown option; the last form screenshot still displayed D2as_v4 (2 vCPU/8 GiB), so the final selected size is not confirmed. Portal prices were screenshots, not verified current quotes. SSH should be restricted to the administrator's IP, HTTP public for judging, and the later container should bind 0.0.0.0:8000. Azure spending is separate from DeepSeek credit; Azure budget and evaluation duration remain unspecified.

## Local commands and tools

```powershell
Set-Location 'E:\bup prili'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_samples --report tmp/step_3_reference_report.json
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

The root session's `.venv` commands worked. If the environment needs recreation, follow README with Python 3.12 and `requirements.txt`; do not install into an unrelated global environment. Git and GitHub CLI are installed. Docker and Azure CLI were previously not found on PATH; availability must be rechecked before packaging/deployment, not assumed absent everywhere.

## Remaining sequence

1. **Step 4:** implement and independently verify the LP optimizer.
2. **Step 5:** real DeepSeek note interpretation, strict guardrails, capacity/time semantics, bounded failures; measure public-note/paraphrase accuracy and latency.
3. **Step 6:** full API integration, readiness, deadlines/reliability, Docker and complete reproduction documentation.
4. **Step 7:** separately approved Azure deployment and pullable image publication, external API and fallback tests.
5. **Step 8:** submission audit, repository visibility handling, final links and an accessible video no longer than three minutes. No video or submission exists yet.

At each boundary, report actual evidence and ask before the next step. Do not treat this checklist as blanket authorization.

## Copy-paste prompt for a new session

```text
Continue my GridWise project in E:\bup prili. Read SESSION_HANDOFF.md first, then STEP_3_RESULTS.md, STEP_2_DESIGN.md, WORK_PLAN.md and README.md. Inspect the existing app/tests/scripts and Git state; preserve all current work. Do not restart the project or repeat completed PDF conversions and planning.

Steps 1–2 and Step 3's local foundation are complete. The last verified result was 186 passing tests and all 10 organizer reference schedules passing independent replay (18 notes, 240 hours). These are reference checks, not generated optimization or real LLM results. The API is intentionally not ready. No optimizer, real DeepSeek adapter or deployment exists yet.

I now approve Step 4 only: implement the continuous LP optimizer from the saved design with SciPy HiGHS and signed battery flow. Use validated structured directives for isolated tests. Enforce every energy/directive constraint and final battery neutrality; retain numerical precision; serialize the full response and verify it with the independent replay checker. Compare all 10 public-case costs and add meaningful analytical tests for curtailment, tight reserves/grid caps and other boundary cases. Do not hard-code references or invent missing rules.

Use the saved sources as authoritative, separate facts from assumptions, and report commands actually run and results observed. Deployment is later. Do not make real-model calls in this step. Keep .env and private keys local, excluded and out of outputs. My chosen GitHub remote is git@github.com:Tasrif-Ahmed-Mohsin/bup-satorugojo.git; authentication and remote verification are pending. Inspect remote history before any future push and do not change visibility or force-push.

The previously confirmed deadline was 18 September 2026, 11 PM Bangladesh time. Check the current time before treating that deadline as still live. After Step 4, stop with a concise progress report and ask me before starting Step 5, the real DeepSeek integration.
```
