GridWise Step 2 Implementation Design

Step 2 is complete as a design deliverable. Step 3 was subsequently approved and implemented locally; see STEP_3_RESULTS.md for actual checks and remaining work. This file records the original design: no application implementation, dependency installation, repository creation, paid model call, VM creation, or deployment was performed during Step 2 itself.

Confirmed decisions: this is the live round; the deadline is 18 September 2026 at 11 PM Bangladesh time (UTC+6). The user chose an Azure virtual machine and the hosted DeepSeek API. The user reported USD 1.50 of DeepSeek credit; Azure spending is separate and its limit is not yet specified. DeepSeek credentials are already configured locally; never print them or request them again.

The smallest suitable design is one Python API, one language-model adapter, deterministic validation, a continuous linear-programming solver, and an independent schedule checker, packaged as one Linux container. The VM runs the application and solver; model inference runs at DeepSeek. A GPU is unnecessary for this design.

**Source authority and evidence**

- P: original 9-page Preliminary Problem Statement in `BUP_CSE_FEST_2026_Participant_Docs`; authoritative for API and challenge behavior.
- G: original 11-page Participant Guide and Evaluation Rubric in the same directory; authoritative for scoring, participation, deployment, and submission.
- S: public sample JSON version 2.0; ten worked reference cases.
- Searchable transcriptions are in `readable_rules`. Page references below refer to original PDF pages.
- The ten reference plans have already passed independent replay across 240 hours. This verifies references, not our future service.
- The full official rulebook and any later organizer amendments have not been supplied. No hidden-case count, judge concurrency, or evaluation end time is known.

**Implementation decisions**

| Area | Selected design | Reason and current limit |
|---|---|---|
| Language | Python 3.12 container runtime | Familiar scientific and API ecosystem; exact dependency versions will be pinned after compatibility checks |
| API | FastAPI with Uvicorn | Two exact routes; customize error handlers to match P |
| Schemas | Pydantic models plus explicit cross-field checks | Keep structural validation separate from semantics |
| Model | DeepSeek `deepseek-flash`, thinking disabled, JSON object output | Current official identifier and supported settings; account access, accuracy and latency still untested |
| API client | One asynchronous HTTP client to DeepSeek | Explicit connection pooling, timeouts, and bounded retry behavior |
| Optimizer | SciPy `linprog(method="highs")` | Published constraints form a continuous LP |
| Verification | Independent replay of the serialized response | Recalculate state and totals instead of trusting solver values |
| Summary | Short deterministic text derived from validated results | Keeps numerical claims grounded and avoids another model call |
| Hosting | Azure Ubuntu x64 VM with Docker | Explicit user preference |
| Persistence | No database needed for the request contract | Each scenario is self-contained; retain only bounded operational logs |
| Credentials | Environment variable at runtime | Keep secrets out of source, image, output and logs |

The official DeepSeek JSON-output guide requires `response_format={"type":"json_object"}`, a JSON instruction/example in the prompt, and adequate output-token allowance. It also warns that empty content can occur. Thinking is enabled by default, so explicitly disable it. These settings improve the interface but do not establish semantic correctness. References: [JSON output](https://api-docs.deepseek.com/guides/json_mode/), [thinking configuration](https://api-docs.deepseek.com/guides/thinking_mode/), [API reference](https://api-docs.deepseek.com/api/create-chat-completion/).

**Request flow and boundaries**

1. Decode JSON, validate structure, validate numeric domains and battery consistency, and check exactly one entry for each hour 0-23. Sort by hour identity internally; do not assume the incoming array is ordered.
2. Send all 1-3 notes together to DeepSeek. Include indexed original note text, battery capacity, the allowed directive definitions, whole-hour convention, and exact expected output shape. Treat notes as data. The model does not need to calculate the 24-hour schedule or alter base forecasts.
3. Parse the model's JSON object containing `directive_interpretation`. Validate its coverage, fields, types, applies semantics, hours and numeric ranges. Sorting already unique valid hours is allowed; fabricating values or missing entries is not.
4. Translate validated directives to effective solar and hourly reserve, charge/discharge, and grid bounds.
5. Solve the LP and require a successful optimal result before labeling the result optimal.
6. Convert signed battery flow into the single required action, normalize only safe numerical artifacts, calculate cost/total grid/peak from those hourly values, and build a grounded summary. Assemble the complete successful response.
7. Serialize the complete response at adequate precision, decode that representation, and independently replay every hour and aggregate. Return the checked payload unchanged; do not recalculate or alter fields after this final check.

`GET /health` checks application readiness without spending an LLM call on each probe. Startup checks include configuration presence, solver import/readiness, and initialized application components. Live provider reachability is established by actual optimization tests; the health route alone does not prove it.

**Exact successful contract**

Request top-level fields: `scenario_id`, `operator_notes`, `hours`, `battery`.

Each hour: `hour`, `demand_kwh`, `solar_kwh`, `tariff_bdt_per_kwh`.

Battery: `capacity_kwh`, `initial_energy_kwh`, `minimum_energy_kwh`, `max_charge_kwh_per_hour`, `max_discharge_kwh_per_hour`.

Response top-level fields: `scenario_id`, `directive_interpretation`, `hourly_plan`, `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh`, `plan_summary`.

Each interpretation: `note_index`, `applies`, `directive_type`, `structured_adjustment`, `explanation`.

Each plan hour: `hour`, `grid_kwh`, `solar_used_kwh`, `battery_action`, `battery_kwh`, `battery_energy_after_kwh`.

| Directive type | Exact adjustment fields | Effect |
|---|---|---|
| `solar_reduction` | `hours`, `factor` | Usable solar equals original solar times the remaining fraction for affected hours |
| `minimum_battery_reserve` | `hours`, `minimum_energy_kwh` | End-of-hour energy is at least both the base reserve and specified reserve |
| `no_charge_window` | `hours` | No charging during affected hours |
| `no_discharge_window` | `hours` | No discharging during affected hours |
| `max_grid_window` | `hours`, `max_grid_kwh` | Import stays below the cap in each affected hour |
| `no_op` | `null` | No scheduling change; `applies=false` |

All active directives have `applies=true`. Exactly one interpretation is returned per note, in note-index order. Exactly 24 plan entries are returned in chronological order. Short explanations need not reproduce reference wording. [P pp.3-8]

**Requirements and acceptance checks**

The following checks are planned, not executed against an application. Each row becomes a specific implementation/review obligation.

| ID | Requirement and source | Acceptance evidence |
|---|---|---|
| R01 | Exact `GET /health` and `POST /optimize-energy`; P p.4 | External route tests and health HTTP 200 containing `status:"ok"` |
| R02 | Required request fields and 1-3 nonempty notes; P p.5 | Valid cases accepted; malformed JSON, missing/wrong-shaped fields, empty or oversized note lists rejected |
| R03 | Exactly 24 unique hour IDs 0-23; P pp.5,8 | Shuffled input succeeds; duplicate, missing, fractional or out-of-range IDs fail |
| R04 | One interpretation per note in index order; P pp.3-4,8 | Missing/duplicate/out-of-range index rejected; full mapping preserved |
| R05 | Only supported directive types and required shapes; P pp.3,5-6 | Typed validation rejects unsupported types, bad fields and invalid adjustments |
| R06 | Applies and no_op semantics; P pp.4,6-7 | no_op always false/null; all active directives true with exact adjustment shape |
| R07 | Sorted unique integer directive hours; P pp.4,6 | Duplicate/out-of-range/fractional hours rejected; approved canonical sorting preserves semantics |
| R08 | Start included, end excluded; P p.3 | 1 PM-3 PM gives [13,14]; noon and same-day end-at-midnight examples checked |
| R09 | Factor is fraction remaining in [0,1]; P pp.4,6,9 | 80% reduction gives 0.2; to 20% gives 0.2; by 20% gives 0.8 |
| R10 | Reserve finite, nonnegative, at most capacity; cap finite/nonnegative; P p.6 | Boundary and invalid-value checks; 50% of 200 kWh reserve gives 100 kWh |
| R11 | Genuine model in interpretation path; P p.2; G pp.4-5,9 | Real-model public-note/paraphrase evaluation and code-path inspection |
| R12 | No invented base data or unsupported rules; P pp.4,6 | Original demand/tariffs/battery object remain unchanged; irrelevant future notes are no_op |
| R13 | Solar bound after adjustments, curtailment allowed, no export; P pp.4,6-8 | Replay checks solar use and nonnegative grid; forced-curtailment fixture |
| R14 | Energy balance every hour; P p.6 | Independently recomputed balance residuals within tolerance |
| R15 | State transition, reserve, capacity and rates; P pp.4,6 | Replay reconstructed from initial energy and actions; end-hour reserve boundary test |
| R16 | Exactly charge/discharge/idle with consistent magnitude; P pp.6-7 | No simultaneous action; idle magnitude zero; no negative magnitudes |
| R17 | Enforce charge/discharge prohibition windows; P p.4 | Individual and overlapping-window tests, including both restrictions forcing idle |
| R18 | Enforce grid cap; P p.4 | Tight-cap scenario that needs advance charging passes replay |
| R19 | End energy equals initial energy; P pp.6-8 | Neutrality check, including initial-energy-above-minimum scenarios |
| R20 | Minimize grid electricity cost only; P p.4 | Solver optimal status and public reference cost comparisons; no invented peak penalty |
| R21 | Correct totals and scenario echo; P pp.7-8 | Recompute all aggregates from emitted/decoded hours and verify scenario_id |
| R22 | Stated absolute tolerance 0.01 kWh/BDT; P p.9 | Decimals and serialization round-trip tests; no two-decimal blanket rounding |
| R23 | Controlled 400/optional 422/500 handling; P p.4; G p.8 | Malformed/semantic/provider/model/solver failure tests with JSON errors and no stack traces |
| R24 | Health ready <=60 seconds, requests <=30 seconds; G p.8 | Timed cold startup and complete request deadlines, including provider failure |
| R25 | Full latency marks require p95 <=5 seconds; G p.8 | Measured warm external real-model requests; no claim based on configuration alone |
| R26 | Public unauthenticated API reachable during judging; G p.4 | Remote calls without login, VPN or manual actions |
| R27 | Pullable Docker fallback, exact tag/digest, bind 0.0.0.0; G pp.3,7-8,11 | Clean pull/run and both route tests; image access verified as judges would access it |
| R28 | Repo created after reveal, private during event, public after deadline; G pp.3,5-6,11 | New repository and explicit visibility timeline reviewed before any change |
| R29 | Self-contained README and clean reproduction; G pp.3,6-8 | Fresh-environment setup, env-variable names, one public sample, provider/solver/credits documented |
| R30 | No exposed secrets; synthetic data only; G p.5 | Source/image/log/error review; no real campus or personal input |
| R31 | Accessible video <=3 minutes; G pp.3,6,8,10-11 | Actual video duration/access checked; explain pipeline and run/test procedure |

Additional domain decisions, clearly distinguished from verbatim input clauses: reject booleans and numeric strings in numerical fields; reject nonfinite values and nonfinite derived calculations; validate `0 <= minimum <= initial <= capacity` and nonnegative rates. Use nonnegative demand/solar/tariff domains unless an organizer amendment says otherwise. Allow zero capacity or zero rates when the resulting scenario is feasible. Avoid arbitrary numeric ceilings. Unknown request keys may be ignored while all required fields are checked; outgoing responses and model adjustments must conform to the defined schema. This avoids inventing an extra contest prohibition on harmless input metadata.

**Mathematical model**

For each of 24 hours use four continuous variables: grid g, solar use s, signed battery change b, and energy after the hour E. There are 96 variables. Positive b means charge, negative b means discharge.

```text
Objective: minimize SUM(tariff[h] * g[h])

g[h] + s[h] - b[h] = demand[h]
E[0] - b[0] = initial_energy
E[h] - E[h-1] - b[h] = 0       for h = 1..23
E[23] = initial_energy

0 <= g[h] <= active_grid_cap[h]    (unbounded above if there is no cap)
0 <= s[h] <= effective_solar[h]
active_reserve[h] <= E[h] <= capacity
-max_discharge <= b[h] <= max_charge
```

Explicitly assign negative lower bounds for b; solver default nonnegative bounds would prohibit discharge. No-charge sets its upper bound to zero; no-discharge sets its lower bound to zero. Both together force idle. Reserve is an end-of-hour bound, not a pre-hour bound. These equations directly represent P's lossless battery rules; no binary variables, degradation terms, efficiency assumptions, or peak objective are needed.

Combine multiple reserve lower bounds with maximum, grid upper bounds with minimum, and prohibition windows by union. Identical repeated solar requirements can be treated idempotently. Different overlapping solar factors remain an organizer ambiguity and must not silently become multiplied, minimum-factor, or last-wins rules.

Normalize negative zero and tiny solver artifacts only before final replay. Retain full useful floating-point precision, use reliable summation, and calculate metrics from the decoded output values. Target tighter internal residuals than the published 0.01 tolerance where numerically practical. An optimal solver result is still rejected if independent replay fails.

**Provider and failure policy**

Model output is untrusted. Every note needs a supported interpretation; do not turn a provider failure into all-no_op output. Public phrases, case IDs, numerical values and reference schedules must never be used as an answer lookup.

Initial proposed settings are `deepseek-flash`, explicit `thinking:{"type":"disabled"}`, JSON object output, concise explanations, and enough output allowance for three complete directive records. A starting maximum of 1024 output tokens is a configuration choice to test, not an official requirement. Use at most one retry, not a sequence of hidden SDK retries. No Gemini fallback is included in the first implementation; it can be added only after its access and behavior are tested.

Proposed deadlines to verify in Step 6:

- Absolute application deadline: 25 seconds from arrival, including queueing.
- Model phase deadline: 20 seconds; at most two attempts, each capped at 8 seconds and shortened by the remaining budget.
- Retry only eligible transient failures or invalid structured output; allow a brief delay only within the remaining deadline. Do not retry bad credentials or exhausted credit.
- Solver time allowance: 2 seconds. Leave time for validation, serialization and controlled error delivery.
- Normal-path performance goal: model around 4 seconds or less, deterministic work around 0.3 seconds or less, with routing margin. These are proposed budgets, not measured results.

An asynchronous provider call prevents network waiting from blocking the server. Move the synchronous solver off the event loop into a bounded execution context, and include queue time in the overall deadline. Start with one Uvicorn process and a small bounded concurrency limit; tune using real measurements. Do not multiply provider retries or native solver threads indiscriminately.

Malformed JSON/structural input errors return 400. Clearly semantic invalid inputs may return 422. Provider timeout, unusable model output, solver failure, or replay failure returns sanitized 500 JSON. An infeasible LP after extraction is not proof that the user's input was wrong: it may indicate a bad interpretation. Never relax directives to make a success response. The error-body format is a project design choice because P does not prescribe one.

DeepSeek documents possible pre-inference waiting; a paid account does not guarantee the competition's latency target. Enforce deadlines locally and measure actual external requests. [DeepSeek service limits](https://api-docs.deepseek.com/quick_start/rate_limit/)

**Azure VM specification**

These are engineering starting recommendations, not official competition minimums or measured capacity guarantees.

| Portal setting | Recommended value |
|---|---|
| Hosting resource | One Azure Virtual Machine |
| Image | Ubuntu Server 24.04 LTS, x64, Generation 2; 22.04 LTS x64 is a compatibility fallback |
| Size | `Standard_B2ls_v2`: 2 vCPUs, 4 GiB RAM |
| Purchase option | Regular pay-as-you-go; avoid Spot for the judging endpoint |
| GPU | None |
| OS disk | 32 GiB Standard SSD, or retain the selected image's larger minimum; no separate data disk initially |
| Public address | One Standard static public IPv4 |
| Network | One VNet/subnet, NIC and NSG |
| Administration | SSH public-key authentication; TCP 22 restricted to the administrator's current public IP |
| Judge access | Public TCP 80 for the HTTP API; TCP 443 if HTTPS is configured |
| Container | Linux/amd64 image, app listening on 0.0.0.0:8000 |
| Port mapping | Minimal initial route: host 80 to container 8000; do not also open public 8000 unnecessarily |
| Outbound | HTTPS access to DeepSeek and the image registry, with working DNS |
| Restart/logging | Restart policy, startup after reboot, container health check, bounded log retention |

The official spec confirms `Standard_B2ls_v2` is x86-64 with 2 vCPUs and 4 GiB RAM. It uses CPU credits and can throttle to its baseline after sustained CPU use. Our remote-model workload is expected to spend time waiting on network I/O, but this is not a substitute for a load test. If unavailable, choose another available x64 SKU with at least 2 vCPUs and 4 GiB after checking price and quota; do not silently switch to Arm64. [Microsoft Bsv2 specifications](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bsv2-series)

32 GiB Standard SSD is a starting disk allowance for Ubuntu, Docker, the image and bounded logs. Do not shrink below the selected image's minimum. Confirm final image/build disk use. [Managed disk types](https://learn.microsoft.com/en-us/azure/virtual-machines/disks-types)

The contest specifies a public HTTP API, so a purchased domain and HTTPS certificate are not prerequisites for the initial judged endpoint. If a DNS name and certificate are configured, add a reverse proxy on 443 and bind the app only to the internal container network or loopback. Credentials used for the outbound DeepSeek request stay in the server environment and travel to DeepSeek over HTTPS; they are never accepted from or returned to judge requests.

Keep the service running throughout the judging window, which may extend beyond submission. Exact VM availability and hourly cost depend on the selected region and subscription. The bill can include VM runtime, disk, public IP and traffic; USD 1.50 of DeepSeek credit does not pay these Azure charges. The portal estimate must be reviewed before provisioning. [Linux VM setup](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-portal), [public IP](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses), [VM quotas](https://learn.microsoft.com/en-us/azure/virtual-machines/quotas)

No managed Container Apps resource is planned now; the VM choice supersedes the earlier hosting proposal.

**Prerequisites and open decisions**

| Item | Status or next information needed |
|---|---|
| Deadline | Confirmed: 18 September 2026, 11 PM Bangladesh time |
| DeepSeek | Key configured locally; credit user-reported; no authenticated model call yet |
| Azure | Need subscription/region, available VM SKU/quota, spending cap, and desired resource names |
| SSH | Need admin username and a local SSH public key; never paste the private key into chat |
| Existing VM | User chose VM hosting; no existing VM has been identified |
| Repository | No Git repository currently in this folder; need the GitHub account/repository name for the new private event repository |
| Registry | Need Docker Hub/GHCR selection and judge-compatible image access |
| Local tools | Git and GitHub CLI are on PATH; Docker and Azure CLI were not found on PATH. This is not proof they are absent elsewhere |
| Packaging path | Decide local Docker build versus building on the approved VM/CI after checking available tooling; a working fallback image is still required |
| Solar overlaps | Ask organizers how different reductions on the same hour combine; no published merge rule |
| Time ambiguity | Same-day standard windows are defined; cross-midnight or equal start/end windows need clarification rather than guessing |
| Guide wording | Plan both public URL and Docker despite p.3 parenthetical ambiguity |
| Source defect | G p.7 optimization note is cut off; preserved in readable source and not reconstructed |
| Evaluation access | Need judging duration and secure model-key handoff mechanism for organizer Docker reproduction |

Pending choices do not prevent schemas, guardrails and replay validation in Step 3. They must be resolved before the dependent provider/deployment work or explicitly documented as limitations. Do not represent an unresolved rule as an official answer.

**Proposed files for implementation**

```text
app/main.py                 routes, startup and exception handling
app/schemas.py              request, directives and response contracts
app/interpreter.py          DeepSeek request, JSON parsing and retry budget
app/directives.py           deterministic guards and hourly bounds
app/optimizer.py            signed-flow LP and action conversion
app/replay.py               independent schedule and totals verification
app/config.py               environment settings, never values in logs
tests/                      meaningful contract, math and failure tests
scripts/check_samples.py    public-case semantic and cost comparisons
Dockerfile                  reproducible Linux runtime
README.md                   complete run, test and fallback instructions
```

This is a proposed file tree only; these application files have not been created.

**Step 3 handoff**

Step 3 implements contracts and independent validation only. It can establish a private repository after reveal, create the structure and tests, and verify all ten reference cases. It does not implement the LP, make paid model calls, or provision the VM yet.

Copy-paste next prompt:

> Proceed with Step 3 only, following STEP_2_DESIGN.md and WORK_PLAN.md. Set up the project and required private event repository using the account/name we agree. Implement request/response schemas, deterministic directive validation and an independent schedule replay validator. Run all ten public reference cases and meaningful invalid-input/schedule checks. Keep secrets excluded from Git and Docker. Report actual results and ask before Step 4.
