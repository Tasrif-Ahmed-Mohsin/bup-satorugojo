# Step 3 — local contracts and validation foundation

Completed locally on 18 September 2026 after the user approved the next build step. Deployment remains a later job. The source-linked design in `STEP_2_DESIGN.md` governs implementation.

## Focus targets and results

| Target | Implemented evidence | Limit |
|---|---|---|
| Exact JSON contract | Typed requests, directives and responses; strict numbers and hour/note coverage; malformed HTTP input maps to sanitized 400 | Full successful API path awaits optimizer/model integration |
| Deterministic directive guardrails | Exact shapes, applies/no_op semantics, unique sorted hours, reserves bounded by capacity, supported hourly bound combinations | Structural validity alone does not prove language accuracy |
| Independent schedule validation | Own directive interpretation and replay; reported and reconstructed states; rates, solar, grid caps, balances, neutrality and totals | Validity does not establish minimum cost |
| Public reference verification | All 10 references pass, covering 18 notes and 240 hours; complete output serialized and decoded first | These are organizer outputs, not generated schedules |
| Reproducible local setup | Python 3.12 virtual environment, pinned dependencies, documented commands and regression tests | Clean Linux/container reproduction remains untested |
| Repository and credentials | Local Git initialized; supplied remote configured; API env file and SSH private-key patterns excluded from Git and Docker | Remote push, visibility and creation time remain unverified pending GitHub authentication |

## Checks actually run

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_samples --report tmp/step_3_reference_report.json
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

- **186 tests passed**, final run 0.47 seconds. Two upstream test-client deprecation warnings remain (HTTPX and an AnyIO alias); no failures.
- **10/10 public reference schedules passed**; every reported total matched recomputation. Reference costs in order: 38365, 42885, 35480, 40495, 33950, 34090, 38550, 37665, 34873 and 41620 BDT.
- Ruff passes. Installed packages have no declared dependency conflicts.
- Original sample pack SHA-256: `fa6abd71868e0faf429a87429d7d4a2b7bfd38c5551565637498d7fec68d5f32`.
- No DeepSeek calls, solver runs, paid resource creation, deployment, or remote repository writes occurred.

Tests cover number coercion, NaN/Infinity and overflow, missing/duplicate hours and notes, unsupported/contradictory directive shapes, capacity and rate bounds, overlapping compatible constraints, battery neutrality, forged totals, forced solar curtailment, zero capacity/rates, and end-of-hour reserve timing. The API scaffold rejects malformed/duplicate-field JSON without echoing input.

An independent code review found two gaps and both now have regression tests: alternating small errors in emitted battery states could conceal a larger adjacent-transition error; and trusted-only replay could let extraction and application tolerances combine into a violation of a reported directive. Replay now checks cumulative and adjacent states, and checks both reported and trusted interpretations when reference annotations are supplied.

## API readiness and unresolved work

The route scaffold exposes the required route names but deliberately reports `/health` as 503/not_ready. A valid `/optimize-energy` input receives a controlled 500/pipeline_not_ready. It cannot fabricate a successful schedule. The required 200 readiness and optimization behavior are integration-stage deliverables.

Different overlapping solar-reduction factors remain unspecified by the source and fail explicitly. Same-day whole-hour semantics and percentage interpretation will be evaluated through the real LLM in Step 5. No hidden-test performance, accuracy, optimality or latency claim is made.

Selected GitHub remote: `git@github.com:Tasrif-Ahmed-Mohsin/bup-satorugojo.git`. SSH returned `Permission denied (publickey)`; `gh auth status` reported no signed-in account; anonymous repository metadata returned 404, which does not prove visibility or existence. Source remains local. Authenticate locally with `gh auth login` before remote verification/synchronization. Do not paste credentials into chat. An existing remote history must be inspected before any future push; no force push is planned.

## Next checkpoint: Step 4, pending approval

Implement the signed-flow continuous linear program using already validated structured directives. Require an optimal solver result, serialize and independently replay each emitted response, compare all ten public costs, and test analytical cases with curtailment and tight constraints. This stage still does not deploy or make real-model calls.

Suggested next prompt:

> Proceed with Step 4: implement and test the continuous LP optimizer using the approved design and independent replay checker. Use trusted structured directives for isolated tests, compare all ten public reference costs, and report actual results before asking to start real DeepSeek interpretation. Keep deployment for later.
