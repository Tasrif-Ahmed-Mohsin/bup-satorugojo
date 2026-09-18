GridWise preliminary: focus targets and staged work plan

Current checkpoint: Steps 1 through 6 are complete and the service is deployed. Schemas, directive guardrails, the independent replay checker, the continuous LP scheduler, the real DeepSeek interpreter and the wired API are implemented; 257 tests pass; all 10 public reference replays pass; the LP reproduces all 10 published costs exactly; real-model interpretation scored 38/38 notes across the public set and this project's own paraphrases; and the public endpoint at http://20.193.131.121 returned 10/10 valid schedules with p95 1.29 s, plus 60/60 valid under concurrent load. See STEP_5_6_RESULTS.md. Outstanding: repository push, Docker image publication, and the submission video. Local Git has the work committed on main; the remote git@github.com:Tasrif-Ahmed-Mohsin/bup-satorugojo.git is configured but authentication is still pending.

User-confirmed context: the event is running now; submission is due 18 September 2026 at 11 PM Bangladesh time (UTC+6). Azure Virtual Machine hosting and the hosted DeepSeek API are the user's choices. After comparing Gemini free API with DeepSeek paid API, the user supplied DeepSeek credentials and explicitly authorized keeping them locally for project implementation, reporting USD 1.50 of DeepSeek credit. Gemini is only a possible future fallback. DEEPSEEK_API_KEY is configured in a local .env excluded by .gitignore and .dockerignore; Windows file access is restricted to the current user and SYSTEM. No API request has been made and no credit has been spent. Keys posted in chat should be replaced before deployment. No secret value is recorded in this plan. DeepSeek account/model access, Azure region/subscription/quota, and Azure spending cap remain unconfirmed. Implementation begins only after Step 3 approval.

The user requested approval before moving to each further step. Complete only the approved step, report evidence and remaining uncertainty, then ask before continuing. A prompt for a later step does not authorize all following steps. Step 3 was approved with the instruction to build thoughtfully according to the plan and rules while leaving deployment for later. A later "continue" during that build kept Step 3 underway; Step 4 remains the next checkpoint.

**What was inspected**

The original folder contained exactly three files and no application code, README, AGENTS.md, or additional project instruction file:

| Reference | File | Authority |
|---|---|---|
| P | `BUP_CSE_FEST_2026_Participant_Docs/BUP_CSE_FEST_2026_Preliminary_Problem_Statement_GridWise_LLM.pdf` (9 pages) | API behavior, schemas, interpretation, guardrails, energy rules, and optimization validity |
| G | `BUP_CSE_FEST_2026_Participant_Docs/BUP_CSE_FEST_2026_Participant_Guide_&_Evaluation_Rubric_GridWise_LLM.pdf` (11 pages) | Participation, deployment, repository, submission, performance, scoring, and penalties |
| S | `BUP_CSE_FEST_2026_Participant_Docs/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json` (version 2.0) | Ten worked examples; not the hidden judge set |

Both PDFs were read and their rendered pages inspected. All ten sample cases were parsed; an independent in-memory replay checked all 240 reference hours, the 18 note mappings, directive compliance, battery transitions and bounds, energy balances, neutrality, and reported totals. No violations were found. This checks reference validity; it does not independently prove reference optimality or test an application. Temporary extraction/rendering files were removed after inspection; the original documents were preserved.

The separate official rulebook mentioned in G was not present. No claim is made to have reviewed it or any later organizer announcements.

Readable source copies are now available in `readable_rules/GridWise_Problem_Statement.txt`, `readable_rules/GridWise_Participant_Guide_and_Rubric.txt`, and the combined `readable_rules/GridWise_All_Rules.txt`. These preserve the full extracted PDF text and original page references, normalize bullet glyphs and blank spacing, and transcribe the problem statement's embedded flow diagram. All 20 source pages passed a per-page alphanumeric-token completeness comparison between the standard and layout text extractions. The visibly incomplete scoring sentence is flagged without guessing its ending. Original PDFs remain authoritative. This conversion does not advance the implementation checkpoint.

**The problem and the proposed solution**

Build one public JSON API. It receives 24 hourly demand/solar/tariff entries, battery parameters, and 1-3 operator notes. A real language-capable generative model must interpret the notes. Validated directives become constraints on a minimum-cost energy schedule. Return the interpretations, 24 hourly decisions, independently recalculated metrics, and a short summary. [P pp.2-8]

Proposed flow:

`Request validation -> LLM note interpretation -> deterministic directive validation -> constraint construction -> linear-programming solver -> independent schedule replay -> JSON response`

The judge checks the organizer's true interpretation, not merely whether a schedule matches our own reported interpretation. A structurally valid but semantically wrong directive can still invalidate a case. [G pp.6-9]

**Focus targets, in priority order**

| Target | Required result | Evidence before declaring it complete | Scoring relationship |
|---|---|---|---|
| F1. Exact contract | Correct endpoint names, status codes, JSON fields, note mapping, and 24-hour coverage | Positive and negative contract checks tied to P | API/schema: 10 points |
| F2. Correct interpretation | Real LLM understands all five active directive types and no_op, including paraphrases | Exact semantic comparison against annotated public and additional synthetic cases; confirm actual model path | Interpretation: 25 points |
| F3. Valid constraints and schedule | Guardrails reject bad model output; every directive and energy rule is enforced | Independent replay of every emitted hour and aggregate | Directive application/correctness: 25 points |
| F4. Minimum grid cost | Solve the stated continuous optimization problem with reliable numerical handling | Feasible optimal solver status, public reference cost comparisons, and analytical small cases | Optimization: 10 points, only for valid cases |
| F5. Reliable API | Controlled errors, stable repeated requests, bounded LLM latency | Startup, latency, provider-failure, and repeated-request measurements | Performance/reliability: 10 points |
| F6. Reachable, reproducible runtime | One public service and a tested pullable Docker fallback | External API checks and clean pull/run test | Deployment/Docker: 10 points |
| F7. Complete handover | README, configuration names, source, credits, limitations, sample procedure, and <=3-minute video | Clean-environment reproduction and accessible artifacts | Documentation: 10 points; video is required and tie-break only |

Interpretation and constraint correctness together account for 50/100 points. Optimization accounts for 10/100 and cannot compensate for an invalid schedule. [G pp.6-10]

**Rules that must remain visible during implementation**

- `GET /health`: HTTP 200 and JSON containing `status: "ok"` when ready. `POST /optimize-energy`: exact spelling. Malformed JSON/structurally invalid requests use 400; 422 is optional for semantic invalidity; internal failures must be controlled. [P p.4]
- One interpretation per note in zero-based `note_index` order. Active types: `solar_reduction`, `minimum_battery_reserve`, `no_charge_window`, `no_discharge_window`, `max_grid_window`. Only `no_op` uses `applies=false` and a null adjustment. [P pp.3-7]
- Directive hour lists are sorted unique integers 0-23. Windows include their start and exclude their end: 1 PM to 3 PM means [13,14]. [P pp.3-4]
- An 80% solar reduction means usable factor 0.2. A reserve expressed as a percentage of capacity must be converted using the supplied capacity. [P pp.4,9; S SAMPLE-03, SAMPLE-09]
- Preserve base demand, tariffs, and battery parameters. Do not infer extra demand from an unrelated event announcement. [P pp.4-6]
- Reserve constraints apply to energy **after** each listed hour. Solar use may be below available solar; unused solar is curtailed. Grid export is excluded. [P pp.4,6]
- One battery action per hour; obey charge/discharge rates, reserve and capacity bounds, and energy balance. Final energy after hour 23 must equal initial energy. [P pp.6-8]
- Cost is sum of grid energy times hourly tariff. Peak grid usage is reported; it is not an additional stated optimization objective. [P pp.4,7]
- Retain sufficient numerical precision and recompute totals from the actual emitted schedule. Stated tolerance is 0.01 kWh / 0.01 BDT unless an official judge package is stricter. Do not assume rounding every field to two decimals is safe. [P pp.8-9]
- Health must become ready within 60 seconds. Each optimization request has a 30-second limit; p95 <=5 seconds earns full latency marks. These are measured targets, not guarantees provided by a hosting platform. [G p.8]
- A real LLM must be in the interpretation path. Sole phrase matching or using AI only to write the summary makes the solution ineligible for the final preliminary shortlist. [G pp.4-5,9]
- Submit a public endpoint, source repository, self-contained README/configuration, pullable Docker image with exact tag/digest, and accessible video no longer than 3 minutes. The repository must be created after question reveal, private during the event, and public after the deadline. [G pp.3-6,11]
- No keys, passwords, tokens, .env contents, or secret-bearing logs/responses in submitted artifacts. Credit external tools and libraries; the team must understand and own the architecture and logic. [G p.5]

**Why a continuous linear program is the preferred solver**

This is a mathematical inference from P, not an organizer-mandated technology choice.

For each hour h define grid import g[h], solar use s[h], battery energy after the hour E[h], and signed battery change b[h]. Positive b charges; negative b discharges. All four are continuous variables, giving 96 variables for 24 hours.

```text
Minimize sum(tariff[h] * g[h])

g[h] + s[h] = demand[h] + b[h]
E[h] = E[h-1] + b[h], with E[-1] = initial_energy

0 <= g[h] <= active_grid_cap[h]   (no upper cap unless a directive sets one)
0 <= s[h] <= effective_solar[h]
active_reserve[h] <= E[h] <= capacity
-max_discharge <= b[h] <= max_charge

No charge in hour h:    b[h] <= 0
No discharge in hour h: b[h] >= 0
Both restrictions:     b[h] = 0
E[23] = initial_energy
```

Convert the sign of b into the required single action and its non-negative magnitude. This avoids simultaneous charge/discharge without binary variables. The supplied model specifies no conversion losses, battery degradation, integer energy quantities, or extra peak penalty; do not introduce them.

Multiple reserve requirements combine through their maximum; multiple grid caps through their minimum; prohibition windows through their union. Solar-reduction overlap needs clarification, as recorded below.

| Approach | Assessment for this challenge |
|---|---|
| Continuous LP | Recommended: directly represents the published rules and decimal energy values; targets the global cost optimum of the formulated model |
| Greedy cheap-charge/expensive-discharge | Useful intuition, but not a reliable solution to interacting reserve, rate, time-window, and grid-cap constraints |
| Discretized dynamic programming | Possible, but energy discretization adds approximation and scaling choices unnecessary for this continuous model |
| Mixed-integer optimization | Possible, but binary action decisions are unnecessary with the signed battery-flow formulation |
| LLM-generated hourly schedule | Too difficult to guarantee balance, constraints, and optimality; use the model for note interpretation and a solver for scheduling |

Step 2 implementation design: Python, FastAPI, typed request/response validation, SciPy `linprog(method="highs")`, a DeepSeek API adapter, Docker, and an Azure Ubuntu x64 VM. The VM choice supersedes the earlier Container Apps suggestion. Exact dependency versions will be pinned after compatibility checks. SciPy's official API supports linear objectives, equality/inequality constraints, variable bounds, and HiGHS solvers: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html . The bundled analysis environment does not currently include SciPy; no installation has been attempted.

FastAPI's default request-validation handling needs deliberate mapping to this competition's status-code rules. Official handler customization is documented at https://fastapi.tiangolo.com/tutorial/handling-errors/ .

**Measures to reduce hallucinations and unsupported assumptions**

1. Maintain requirement IDs with source document/page, acceptance check, and status. Separate official requirements, design choices, and open questions.
2. Use the LLM only to extract the allowed directives. Supply battery capacity when needed for percentage reserves. Treat operator notes as data, not instructions to override the system or schema.
3. Prefer provider-supported structured output if the selected model supports it; verify support against that provider's current documentation before coding.
4. Validate note coverage, type, exact adjustment shape, applies semantics, sorted hours, finite numbers, factor [0,1], reserve within capacity, and non-negative caps before optimization.
5. Check semantic correctness with independently annotated paraphrases and percentage/time examples. JSON validity alone cannot prove correct understanding. No prompt can guarantee zero hallucinations.
6. Handle malformed output/provider failure with a bounded retry or an explicitly evaluated real-model fallback within the request deadline, then a controlled error if necessary. Never convert model failure into fabricated no_op entries or silently ignore a relevant constraint.
7. Build an independent replay validator. It must recompute battery state, energy balance, directive compliance, and metrics instead of trusting optimizer-reported totals.
8. Compare sample interpretation semantics and valid optimal cost, not exact hourly schedules or explanation wording. Never hard-code sample phrases, IDs, values, or answers.
9. At every checkpoint report commands actually run, observed results, changed files, and untested claims. A mock model passing tests is not evidence that the real LLM works.

**Open questions and gaps**

| Item | What is known | What is still needed |
|---|---|---|
| Event timing | User confirmed 18 September 2026, 11 PM Bangladesh deadline; event is live | Submission portal and evaluation duration |
| Official rulebook | G refers to another rulebook | The current rulebook and any organizer amendments or stricter judge package |
| Overlapping solar reductions | P defines original solar multiplied by a factor for each directive | Organizer rule for different solar factors affecting the same hour; do not assume multiplication, minimum factor, or last-wins |
| Cross-midnight windows | Whole-hour start-inclusive/end-exclusive convention is defined | How a wrapped window maps to this specific 24-hour scenario |
| Public API/Docker wording | Repeated explicit requirements and scoring cover both artifacts | One awkward parenthetical on G p.3 says 'Public API URL Recommended'; plan both artifacts unless organizers clarify otherwise |
| Hosting/model resources | User selected DeepSeek API and Azure VM; DeepSeek credentials configured locally | Accessible DeepSeek model, quota, Azure subscription/region/VM availability, budget |
| Judge workload | Repeated requests and latency limits are specified | Expected concurrency/request count and how fallback model credentials are supplied securely to judges |

The optimization-score note on G p.7 visibly ends mid-sentence in its zero-optimum special case. The displayed general ratio is clear; do not invent the missing text or build our own judge-specific assumptions around it.

Future tests should cover forced solar curtailment (none of the public references require it), all-no_op requests, factor 0/1, tight reserves, zero caps/rates where valid, decimal values, unordered input hours, overlapping compatible constraints, malformed input, provider timeouts/rate limits, invalid model output, and paraphrases. Ambiguous timing/solar-overlap tests need documented assumptions or organizer answers first.

**What the user needs to provide, and when**

| Stage | Information or resource | How to provide it |
|---|---|---|
| Before affected implementation | Any additional official rulebook or organizer updates | Deadline is confirmed; provide only additional available document paths/links |
| Before model selection | Available DeepSeek models/quota, spending allocation from USD 1.50 credit, Azure credits | Model names and budget; no credentials |
| Before real LLM testing | DeepSeek model identifier, usable quota/billing, API credentials configured | DEEPSEEK_API_KEY is already configured locally; do not print it or ask for it again |
| Before packaging | GitHub account/repository policy and Docker Hub/GHCR or other registry choice | Names/URLs; authenticated tools can be set up in the approved step |
| Before Azure deployment | Active subscription, authorized login/resource-creation permission, region, resource group/app names, budget and evaluation duration | Non-secret configuration and local Azure login; no account password sharing |
| Before Azure deployment | Exact image tag/digest, image pull access, service port, model environment-variable names, SSH public key/admin username/source IP | Reviewed VM deployment configuration; no private key in chat |
| Before submission | Public URL, repository URL, pullable image, accessible <=3-minute video, submission method | Final artifact locations, reviewed against the guide |

For the selected DeepSeek API, `DEEPSEEK_API_KEY` is already configured locally. In the approved deployment step, configure it as an Azure secret referenced by the container environment. A project setting such as `DEEPSEEK_MODEL` will specify the exact model ID. These names are project conventions, not contest fields. Current candidate: `deepseek-flash` with thinking disabled, subject to measured extraction accuracy and latency. Current official references: https://api-docs.deepseek.com/quick_start/pricing/ and https://api-docs.deepseek.com/guides/thinking_mode/ . No secret values should appear in this plan, prompts, screenshots, repository, image, or logs. Local .env storage is plaintext protected by file permissions and exclusion rules; it is not encrypted storage.

For an optional Gemini fallback, Gemini supports structured outputs with a subset of JSON Schema and Python schema definitions through Pydantic: https://ai.google.dev/gemini-api/docs/structured-output . Its credential can be configured as GEMINI_API_KEY if later authorized. Verify the chosen model's support and schema compatibility before implementation. Structured output helps formatting but does not guarantee correct interpretation. Select an available text model by a small measured extraction/latency check; do not invent a model ID or assume free-tier quota will cover judging. Do not add a second provider unless there is time to test it properly.

Azure VM is the user's selected host. Proposed starting size: Standard_B2ls_v2 (2 vCPUs, 4 GiB RAM), Ubuntu Server 24.04 LTS x64 Gen2, 32 GiB Standard SSD or the selected image's larger minimum, a Standard static public IPv4, and Docker. No GPU is needed because DeepSeek inference is remote. This is an engineering estimate pending load tests, not a competition minimum. B-series CPU credits can limit sustained compute. Use a regular VM, not Spot, for evaluation continuity.

Expose host HTTP port 80 to the app's container port 8000 for the minimal contest-compliant endpoint; add HTTPS on 443 if configured. Restrict SSH 22 to the administrator's IP and use key authentication. Keep credentials in runtime environment configuration. Region, quota, image minimum disk, spending cap and final portal estimate must be reviewed before provisioning.

Official Microsoft references checked during planning:

- VM size and burst behavior: https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bsv2-series
- Linux VM setup: https://learn.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-portal
- Managed disk types: https://learn.microsoft.com/en-us/azure/virtual-machines/disks-types
- Public IP: https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses
- Quota: https://learn.microsoft.com/en-us/azure/virtual-machines/quotas

A private registry accessible from the VM is not automatically pullable by judges. Test the actual fallback access arrangement. Keep the official repository private until the required time; inspect what an image exposes before publishing it during the event.

**Sequential prompts for further work**

Use one prompt at a time. These are future requests, not work already authorized. No cloud purchases or model calls are needed to review the design. The project checkpoint should be updated after each approved step.

Live-round planning budgets against the confirmed 11 PM deadline: Step 2 is complete; Step 3 about 20-25 minutes; Step 4 about 20-25; Step 5 about 25-30; Step 6 about 30-40; Step 7 about 25-30; Step 8 about 15-20. These are planning estimates, not completion promises. Reserve remaining time for failures. Prepare DeepSeek access, Azure login, registry access, and the video in parallel where teammates are available. Keep the required artifacts in scope; optional UI and additional infrastructure are unnecessary for the published judge path.

Reusable instruction to prepend when starting a new task:

> Read WORK_PLAN.md and the relevant original source pages. Preserve the approved checkpoint. Work only on the step I authorize. Prioritize interpretation and constraint correctness. Distinguish official rules, design choices, and unknowns. Do not invent requirements, credentials, successful tests, or deployment results. Do not hard-code public cases. Cite the requirement behind each important behavior. Report observed validation results and remaining gaps, then stop and ask before the next step. Do not expose secrets.

Steps 1 and 2 are complete; Step 3's local implementation and verification are complete, with GitHub synchronization pending authentication. The prompts below remain as a record of the approved sequence; the next implementation prompt is Step 4.

2. Requirements and design approval:

> Proceed with Step 2 only for the live round using DeepSeek API and Azure VM. Review any additional rulebook/organizer updates I provide. Confirm the exact deadline and create a concise source-linked requirements/acceptance matrix, ambiguity register, and API/LLM/validator/LP design. Explain the signed battery-flow formulation. Finalize the simplest stack and VM specification consistent with our experience and budget; identify the DeepSeek model/access checks needed. Do not implement the application or create paid resources. Show the decisions for review, then ask before Step 3.

Acceptance: every mandatory behavior is traceable; unresolved rules are visible; stack and resource choices are agreed or explicitly pending.

3. Contracts and independent validation:

> Proceed with Step 3 only using the approved design. After confirming question reveal, create the required new private GitHub repository using my selected account and develop the round solution there. Create the project structure, exact request/response schemas, deterministic directive validation, and an independent schedule replay validator. Preserve the original sample pack and implement a runner for all 10 public references. Add meaningful negative tests for hour coverage, malformed values, inconsistent directives, invalid energy accounting, and neutrality. No real-model calls or deployment yet. Report actual results, then ask before Step 4.

Acceptance: all ten references replay successfully; deliberately invalid schedules/directives are rejected; official error-code rules are represented.

4. Mathematical optimizer:

> Proceed with Step 4 only. Implement the approved continuous LP with signed battery flow, using trusted structured directives as isolated test inputs. Enforce every energy/directive constraint and end-of-day neutrality. Serialize at sufficient precision and replay the emitted plan independently. Compare public-case costs with the supplied reference costs and test analytical edge cases including curtailment and tight constraints. Do not claim the full LLM pipeline is complete. Report solver status and observed differences, then ask before Step 5.

Acceptance: public costs match within the official tolerance, constraints pass independent replay, and solver failures are controlled. Any discrepancy is explained before proceeding.

5. Real LLM interpretation:

> Proceed with Step 5 only. Using DeepSeek and DEEPSEEK_API_KEY already configured locally, verify the selected model's official API/schema support and implement real note interpretation into the exact directive contract. Add deterministic validation, capacity-based percentages, controlled output/provider failures, and bounded retries within the request budget. Evaluate all sample notes plus independently annotated paraphrases and distractors. Separate structural validity from semantic accuracy. Report measured accuracy, latency, and failures; then ask before Step 6.

Acceptance: the real model is demonstrably on the interpretation path; every public note is checked; paraphrase failures and provider limits are visible rather than hidden by mocks.

6. End-to-end reliability and deployment preparation:

> Proceed with Step 6 only. Integrate the two required API endpoints, status/error behavior, real LLM, validators, and optimizer. Run all public requests end to end and measure startup, repeated-request stability, and latency. Build and locally test the Docker image with no embedded credentials. Write a clean quickstart, sample commands, dependency/model disclosure, and limitations. Prepare the concrete deployment configuration and cost factors for the chosen host, including image, port, ingress, scaling, and secret references. Do not create cloud resources or publish artifacts yet. Present the tested result and ask for approval of Step 7 and its exact configuration.

Acceptance: working local/container API; independently validated outputs; documented latency and remaining gaps; a reviewable deployment proposal within the user's budget.

7. Approved deployment and external verification:

> Proceed with Step 7 using the deployment configuration and spending scope I approved. Publish the required container artifact with the agreed access policy and deploy the tested image to the selected host. Configure secrets securely and keep repository visibility consistent with event rules. Test both endpoints from outside the development environment, verify readiness and repeated LLM-backed requests, and check the judge's Docker fallback path. Report actual URLs/image references and observed results. Then stop and ask before Step 8.

Acceptance: publicly reachable API, stable real-model requests, working image pull/run, and no undocumented manual setup for judges. Hosting alone does not imply correctness or full marks.

8. Submission readiness:

> Proceed with Step 8 only. Audit the implementation and deployment against every requirement and scoring category. Verify README reproduction, final sample results, repository timing/visibility plan, exact fallback image reference, and secret hygiene. Prepare the submission details and a concise <=3-minute video script explaining the problem, LLM/guardrail/optimizer flow, and run/testing procedure. List any remaining user actions such as recording/uploading the video and the approved repository visibility change. Do not claim a video exists or that submission is complete unless verified. Show the package for review before submitting anything.

Acceptance: all required artifacts are present and accessible, or outstanding user actions are explicitly listed. Submission and timed visibility changes occur only when instructed.

At the end of each step: summarize what changed, which acceptance checks actually passed, what remains uncertain, and ask whether to proceed to the next named step. Correct problems within the currently approved step before requesting progression.
