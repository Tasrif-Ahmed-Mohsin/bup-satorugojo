# GridWise — 3-minute video script (simple English)

**Target 2:45.** The hard limit is 3:00. Short sentences, easy words. Read slowly and clearly.
Production quality is not judged. One clean take is enough.

## Before you record

1. Open `assets/architecture.html` in your browser. Press **F11** for full screen.
2. Open a second tab at **http://20.193.131.121/**
3. Open PowerShell in `E:\bup prili`. Make the font big.
4. Start your screen recorder.

---

# SCENE 1 — The problem
### Screen: architecture slide · 0:00 to 0:22

> "Hello. This is GridWise.
>
> A campus can get power from three places. The grid, its solar panels, and a battery.
>
> Every hour the grid price is different. So the cheapest plan is not easy to find.
>
> There is one more problem. Staff do not write maths. They write simple notes. Like: *panel cleaning
> from 11 to 1, solar will be about 30 percent.*
>
> GridWise reads those notes. Then it makes the cheapest 24-hour plan."

---

# SCENE 2 — The architecture
### Screen: same slide. Point at each box as you speak · 0:22 to 0:58

> "There are six steps.
>
> Step one. The request comes in. It has 24 hours of demand, solar and price. It also has the battery
> limits and up to three notes.
>
> Step two. We check the shape of the data. If anything is wrong, we return 400.
>
> Step three. The language model. This is DeepSeek. This is the only part that reads human language.
> We send the notes as data, not as commands. So a note cannot change our instructions. It gives back
> one directive for each note.
>
> Step four. We do not trust that answer. Our own code checks it. Is the type allowed? Is the shape
> correct? One entry for each note? Are the hours from 0 to 23, in order? Is the solar factor between
> zero and one? Is the reserve inside the battery size?"

---

# SCENE 3 — Solver and final check
### Screen: same slide. Point at the equation box · 0:58 to 1:22

> "Only after those checks pass, the directives become real constraints.
>
> Step five is the solver. It is a linear program. 96 variables for 24 hours. It finds the lowest
> grid cost. We use SciPy with HiGHS.
>
> Step six is the most important part. We do not trust the solver either.
>
> We turn the plan into JSON. We read it back. Then different code checks everything again. The
> energy balance. The battery level. Every directive. All the totals.
>
> Only a plan that passes this check is sent back."

---

# SCENE 4 — Live demo
### Screen: switch to `http://20.193.131.121/` · 1:22 to 2:10

> "Here it is running live. This is on an Azure server. Anyone can open it."

**Click "Run optimization".** While it loads, about 1.3 seconds:

> "There are three notes here.
>
> First note. Cleaning from 11 AM to 1 PM, about 30 percent solar. The model returned
> `solar_reduction`. Hours 11 and 12. Factor 0.3.
>
> Please see the hours. The start hour is inside. The end hour is not. This is the rule in the
> problem statement.
>
> Second note. Keep 150 kilowatt-hours from 6 to 9 PM. It returned `minimum_battery_reserve` on hours
> 18, 19 and 20.
>
> Third note is about the library. It does not change power. So it is `no_op`. It is ignored."

**Now change a note.** Change `30%` to `10%`. Or add: `Do not charge the battery between 2 PM and 4
PM`. Click **Run optimization** again.

> "Now I change the note. And you can see the directive changes. The plan changes. The cost changes.
>
> This is not keyword matching. This is a real model reading real language."

---

# SCENE 5 — How to run and test it
### Screen: PowerShell · 2:10 to 2:45

**Run:** `.\.venv\Scripts\python.exe -m pytest -q`

> "This is how we test it. 257 tests. They need no API key. They spend no money. The model part is
> replaced by a fake one in tests.
>
> We also solve all ten official sample cases. Our cost is the same as the official cost. All ten,
> exactly.
>
> For the notes, we are correct on all 18 public notes. And on 20 more notes that I wrote myself.
>
> The live server answers in about 1.4 seconds. And there is a Docker image you can pull, as a backup.
>
> Thank you."

---

## Numbers you can say (all measured)

| Thing | Number |
|---|---|
| Official sample costs matched | 10 out of 10, exactly |
| Notes understood correctly | 38 out of 38 |
| Tests passing | 257 |
| Live speed (p95) | 1.4 seconds |
| Time until `/health` is ready | 0.15 seconds |

## Please do not say

- Do not say anything about the hidden test cases. We have not seen them.
- Do not say the plan is "always the best". Say it matches all ten official costs.
- Do not show `.env`, the `.pem` file, or any key on the screen.

## Hard words — how to say them

| Word | Say it like |
|---|---|
| SciPy | *sigh-pie* |
| HiGHS | *highs* |
| Pydantic | *pie-DAN-tic* |
| DeepSeek | *deep-seek* |
| kWh | say "kilowatt-hours" |
| p95 | say "p ninety-five" |

## After recording

Upload as MP4, or to Google Drive or YouTube as **unlisted**. Then open the link in a **private
window** to be sure the judges can open it. Check the length is 3:00 or less.
