# GridWise — video script

**2:30. Limit is 3:00.** Read it out. Short lines. Go slow.

**Setup:** `assets/architecture.html` open, press F11 · second tab on `http://20.193.131.121/` ·
PowerShell in `E:\bup prili`, big font · start recorder.

---

## 1 — The problem · slide · 0:00–0:20

> "This is GridWise.
>
> A campus gets power from three places. The grid, solar panels, and a battery.
>
> The grid price changes every hour. So the cheapest plan is hard to find.
>
> And staff do not write maths. They write notes. Like: *cleaning from 11 to 1, solar will be about
> 30 percent.*
>
> GridWise reads those notes and makes the cheapest 24-hour plan."

## 2 — The six steps · slide, point at each box · 0:20–1:00

> "Six steps.
>
> **One.** A request comes in. 24 hours of demand, solar and price. Battery limits. Up to three notes.
>
> **Two.** We check the data. If it is wrong, we return 400.
>
> **Three.** DeepSeek. This is the only part that reads human language. We send the notes as data, not
> as commands. So a note cannot change our instructions. It returns one directive per note.
>
> **Four.** We do not trust that answer. Our own code checks it. Correct type. Correct shape. One
> entry per note. Hours 0 to 23, in order. Solar factor between zero and one. Reserve inside the
> battery size.
>
> **Five.** Now the directives become real constraints. A linear program. 96 variables. It finds the
> lowest grid cost. We use SciPy HiGHS.
>
> **Six.** We do not trust the solver either. We turn the plan into JSON, read it back, and different
> code checks everything again. Energy balance. Battery level. Every directive. All totals.
>
> Only a plan that passes step six is sent back."

## 3 — Live demo · `http://20.193.131.121/` · 1:00–1:55

> "Here it is, live on an Azure server."

**Click "Run optimization".**

> "Three notes.
>
> Cleaning 11 AM to 1 PM, about 30 percent. It returned `solar_reduction`, hours 11 and 12, factor
> 0.3. Look at the hours — the start hour is inside, the end hour is not. That is the rule.
>
> Keep 150 kilowatt-hours from 6 to 9 PM. It returned `minimum_battery_reserve` on hours 18, 19, 20.
>
> The library note does not change power. So, `no_op`. Ignored."

**Change `30%` to `10%`. Click Run again.**

> "I change the note. The directive changes. The plan changes. The cost changes.
>
> This is not keyword matching. This is a real model reading real language."

## 4 — Testing · PowerShell · 1:55–2:30

**Run:** `.\.venv\Scripts\python.exe -m pytest -q`

> "257 tests. No API key needed. No money spent.
>
> We also solve all ten official sample cases. Our cost matches the official cost exactly, all ten.
>
> On the notes, we are correct on all 18 public notes, and 20 more that I wrote myself.
>
> The live server answers in 1.4 seconds. And there is a Docker image you can pull as a backup.
>
> Thank you."

---

## Numbers (all measured)

10/10 official costs matched exactly · 38/38 notes correct · 257 tests pass · 1.4 s p95 · 0.15 s to
ready

## Do not

Do not talk about hidden test cases. Do not say the plan is "always best" — say it matches all ten
official costs. Do not show `.env`, `.pem`, or any key.

## Say it like

SciPy = *sigh-pie* · Pydantic = *pie-DAN-tic* · kWh = "kilowatt-hours" · p95 = "p ninety-five"

## After

Upload MP4, or Drive/YouTube **unlisted**. Open the link in a **private window** to check judges can
see it. Length must be 3:00 or less.
