# GridWise — 3-minute video script

**Target 2:45.** The limit is a hard 3:00, so this leaves margin. Speak at a normal pace; the word
count is tuned for roughly 145 words per minute. Production quality is explicitly not judged — one
clean take is enough.

## What the rules require you to cover

The guide asks the video to explain **the problem**, an **architecture overview**, your **solution
approach**, the **LLM → deterministic guardrails → optimizer flow**, and **how the system is run and
tested**. All five are covered below, in that order.

## Before you start recording

1. Open `assets/architecture.html` in your browser, press **F11** for full screen.
2. Open a second tab at **http://20.193.131.121/**
3. Open a PowerShell window in `E:\bup prili`, already sized large and readable.
4. Start your screen recorder. Record the whole screen at 1080p.

---

## SCENE 1 — The problem · `assets/architecture.html` · 0:00–0:22

> "A campus gets electricity three ways: the grid, its solar panels, and a battery. Every hour has a
> different tariff, so the cheapest plan is not obvious. The complication is that operators don't
> write constraints as maths — they write notes like *'panel cleaning from 11 to 1, expect about 30%
> of normal solar'*. GridWise turns those notes into a validated, minimum-cost 24-hour schedule."

## SCENE 2 — Architecture · same slide, point along the row · 0:22–0:58

> "The architecture is six stages. A request arrives with 24 hours of demand, solar and tariff, the
> battery limits, and up to three notes. Schema validation rejects anything malformed as a 400.
>
> Stage three is the language model — DeepSeek. It is the **only** component that reads human
> language, and the notes are passed to it as delimited data, never as instructions, so a note can't
> hijack the prompt. It returns one structured directive per note.
>
> Stage four treats that output as **untrusted**. Deterministic guardrails check the directive type,
> its exact shape, one entry per note, hours sorted and in range, solar factor between zero and one,
> reserve within battery capacity."

## SCENE 3 — Solver and replay · same slide, the equation band · 0:58–1:22

> "Only then do the directives become hard constraints in a linear program — 96 continuous variables
> over 24 hours, minimising the cost of imported grid electricity, solved with SciPy's HiGHS.
>
> And stage six is the part I'd most like you to notice: the finished plan is serialized, decoded,
> and re-checked by **separate code** — energy balance, battery state, every directive, all the
> totals — before it's returned. The solver's word is never taken for it."

## SCENE 4 — Live demo · switch to `http://20.193.131.121/` · 1:22–2:10

> "Here it is running, publicly, on an Azure VM."

**Click Run optimization.** While it runs (about 1.3 seconds):

> "Three notes. Panel cleaning 11 AM to 1 PM at about 30% solar — the model returned
> `solar_reduction`, hours 11 and 12, factor 0.3. Note the window rule: the start hour is included,
> the end hour excluded. A 150 kWh reserve from 6 to 9 PM became `minimum_battery_reserve` on hours
> 18, 19 and 20. And the library announcement is correctly ignored as `no_op`."

**Now edit a note live** — change `30%` to `10%`, or add `Do not charge the battery between 2 PM and
4 PM` — and click **Run optimization** again.

> "Change the note, and the directive, the schedule and the cost all change with it. Nothing here is
> pattern-matched — that is a real model reading real language."

## SCENE 5 — How it's run and tested · PowerShell · 2:10–2:45

Run: `.\.venv\Scripts\python.exe -m pytest -q`

> "257 tests, and they need no API key and spend no credit — the provider boundary is stubbed.
> Separately, the optimizer solves all ten official sample cases and reproduces every published cost
> **exactly**, and interpretation is correct on all 18 public notes plus 20 paraphrases I wrote
> myself. The live endpoint answers with a p95 of 1.4 seconds, and there's a pullable Docker image
> as a fallback. Thank you."

---

## Numbers you can quote, all measured

| Claim | Value |
|---|---|
| Official sample costs reproduced | 10/10, difference exactly 0.0 |
| Notes interpreted correctly | 38/38 (18 public + 20 own paraphrases) |
| Tests | 257 passing |
| Live p95 latency | 1.38 s (limit 30 s; full marks under 5 s) |
| `/health` ready after restart | 0.15 s (limit 60 s) |
| Concurrent load | 60/60 valid at concurrency 5 and 10 |

## Do not say

- Don't claim anything about hidden cases — you have no evidence about those.
- Don't call the schedule "provably optimal" in general. It is optimal **for this stated model**,
  and it matches all ten published costs.
- Don't show `.env`, the `.pem` file, or any key on screen.

## After recording

Upload as MP4 or to Drive/YouTube **unlisted**, then **open the link in a private window** to confirm
judges can actually reach it. Check the duration is at or under 3:00.
