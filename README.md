# GridWise

GridWise converts campus operator notes into validated operational directives and a minimum-cost 24-hour electricity schedule. The required final architecture is:

`request -> real DeepSeek interpretation -> deterministic guardrails -> linear program -> independent replay -> response`

**Current checkpoint: Step 3 validation foundation.** Request/response contracts, directive bounds, offline reference replay, tests, and API route scaffolding are implemented. The optimizer and real model adapter are not implemented yet. This is not a submission-ready API: `/health` intentionally returns **503** with `{"status":"not_ready"}` and a structurally valid `/optimize-energy` request returns a controlled **500**. No reference schedule is used as an API answer.

## Local verification

Use Python 3.12. Run these commands from the repository root in PowerShell; activation is unnecessary:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_samples
.\.venv\Scripts\python.exe -m ruff check app scripts tests
```

On Linux, create the environment with `python3.12 -m venv .venv` and substitute `.venv/bin/python` for `.\.venv\Scripts\python.exe`. The installed Windows environment was tested; clean Linux/container reproduction remains a packaging-stage check.

The sample command reads the original organizer pack, validates all ten inputs and reference outputs, derives bounds, and independently replays all 240 reference hours. It exits nonzero if any check fails. It **does not run a solver or call a language model**, and passing it does not prove either optimality or language interpretation accuracy. To save results:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_samples --report tmp/reference-report.json
```

All installed dependencies, including test tools and transitive dependencies, are pinned in `requirements.txt`. Tests require no credentials or paid services.

## Implemented boundaries

| Module | Responsibility |
|---|---|
| `app/schemas.py` | Exact required fields, strict finite numeric values, 24-hour coverage, battery consistency, directive shapes, and response ordering |
| `app/directives.py` | One interpretation per note, reserve-capacity guardrails, safe hour sorting, and hourly operating bounds |
| `app/replay.py` | Independent energy/directive/state/rate/neutrality/aggregate checks without using the bounds builder |
| `app/jsonio.py` | JSON parsing/serialization with no duplicate object keys, NaN, Infinity, or blanket numeric rounding |
| `app/main.py` | Exact route scaffolding and sanitized malformed-input errors; no operational optimization yet |
| `scripts/check_samples.py` | Offline reference validity checks only; not imported by the application |

The replay checker accepts the complete decoded response and never modifies it. Optional independently annotated `trusted_directives` also check the reported interpretation meaning; explanations are not compared word for word. With no trusted annotations, replay checks consistency with the reported directives, not whether human language was interpreted correctly.

Input metadata outside the required fields is ignored. Numerical strings, booleans as numbers, nonfinite values, negative demand/solar/tariff/rates, and inconsistent initial battery bounds are rejected. Nonnegative numeric domains beyond explicit source clauses are engineering decisions recorded in `STEP_2_DESIGN.md`. Zero capacity and zero rates are allowed. Request hours may arrive unordered; output hours must be chronological.

Multiple reserves combine by maximum, grid caps by minimum, and prohibition windows by union. Identical overlapping solar factors apply once. **Different overlapping solar factors fail explicitly** because the supplied rules do not define how to combine them. Empty directive hour arrays are allowed by the structural schema because the source specifies no minimum length; semantic evaluation must still determine the right affected hours.

Physical comparisons use absolute tolerance only, defaulting to the published 0.01 kWh/BDT. Tests also check the public references at 1e-9. Trusted solar-factor comparison uses 1e-12 because a dimensionless factor is not a kWh quantity. This is a local comparison policy, not a claim about an unpublished judge.

## Inspecting the API scaffold

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, `curl.exe -i http://127.0.0.1:8000/health` should currently return **503**, not readiness. Open `/docs` to inspect the required request/response schemas. Structurally invalid optimization requests return sanitized HTTP 400. A complete operational example, measured startup/request timings, Docker commands, and external access checks will be documented after integration and packaging.

## Credentials and repository

The future model adapter will use `DEEPSEEK_API_KEY` from the runtime environment. `.env.example` contains names only. The current tests and scaffold do not load `.env`, call DeepSeek, or spend credit. Never put API tokens or SSH private keys in source, issue text, logs, container layers, or responses. `.env` and private-key file patterns are excluded from Git and Docker build contexts. Those exclusions do not encrypt local files.

The selected remote is `git@github.com:Tasrif-Ahmed-Mohsin/bup-satorugojo.git`. Local Git is initialized. Remote access, creation time, and visibility have not been verified: SSH authentication failed and GitHub CLI is not signed in. No push or visibility change has been performed. The organizer requires a repository created after reveal, private during the event and public after the deadline. Repository authentication can be completed locally with `gh auth login`; never send an account token in chat.

## Rules, credits, and remaining work

The original problem statement, participant guide and public sample JSON are preserved under `BUP_CSE_FEST_2026_Participant_Docs/`. Searchable copies are under `readable_rules/`; the original PDFs remain authoritative. The reference pack is used only for tests and local verification. No public phrase, scenario identifier, or reference schedule is used as an application lookup.

The implementation uses [Pydantic strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/), [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/), Uvicorn, pytest, Ruff, and HTTPX for local API tests. Codex assisted with design, implementation, and review; the team should review and understand the submitted logic. No optimizer or provider integration is being credited as complete at this checkpoint.

Next approved stages remain: continuous LP and analytical checks; real DeepSeek extraction and measured semantic tests; full API reliability and Docker packaging; Azure VM deployment; submission/video audit. See `WORK_PLAN.md` and `STEP_2_DESIGN.md` for source-linked requirements and step boundaries. Each next stage requires the user's go-ahead.
