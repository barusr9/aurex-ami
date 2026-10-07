1. Make it cheaper and faster: same quality, at under half the cost. Show cost and response time before and after.
2. Catch it when it breaks: a simple monitor that notices when answers get worse. Break it on purpose and show the monitor catches it.
3. Learn from complaints: turn 10 real complaints or bad answers into test cases, fix them, and show the before and after on those 10.
4. Fail gracefully: switch off each piece it depends on (the model, the search, a tool) and show what the user sees. No crashes, no confident wrong answers.
5. Make it trustworthy to users: have 3 people use it, note where each stopped trusting it, redesign that moment, and test again.
6. Use the right model for each job: send easy questions to a cheaper model and hard ones to a stronger one. Show the cost against the quality.



OUTPUT EXPECTED:

1. READ https://study.modernaipro.com/learn/lessons/l4-readout 1, 2, 3, 4 POINTS AND UPDATE WHAT IS EXPECTED. --

## L4 Readout — what's expected (from the lesson)

The project closes as a **production-readiness review, not a demo**. A demo
says "look what it can do"; a readout says "here is what changed" — the same
frozen cases, measured before and after, with the numbers that got worse
shown next to the ones that got better, and a witness who watched it run.
It must include the change that did *not* work.

**The three rules (no exceptions):**

1. **Same suite.** Report on the golden set you froze *before* Friday — not a
   new or better one. Cases added this weekend (from complaints, from drift)
   are reported separately, each with the date it was frozen.
2. **All four numbers.** Cost, p50, p95, and score — before and after. A cost
   cut that dropped the score is reported as exactly that. Hiding the number
   that got worse is the one thing that fails a readout outright.
3. **Witnessed.** Your pair watches the after-run happen and signs the report
   — a witness that the numbers came from the system, today.

> An honest negative passes: "Routing to the small tier cut cost by half and
> broke the refund cases, so I reverted it" is a *finding* — exactly the
> judgement L4 exists to train. Section 5 (What did NOT work) is not optional:
> a weekend in which every change worked is a weekend in which somebody
> stopped measuring.

**The report — `READOUT.md`, one page a reviewer can act on:**

1. The system, on the eight layers — one line per layer; mark the layers
   changed this weekend.
2. The project — `S<n> · <title>` — the gap it closes, in one sentence.
3. Before and after — same frozen suite (`<N>` cases, frozen `<date>`), a
   table of: cost per run (¢), p50 latency (ms), p95 latency (ms),
   golden-set score, users at SLO break, failure screenshot (before/after
   links).
4. What moved, by kind of case — which case types got better, which worse,
   which did not move.
5. What did NOT work — at least one change you tried and reverted, with its
   numbers.
6. What you would watch in production — the metric, the threshold, and who
   gets paged.

**The five-minute presentation (in this order):**

1. The gap (30s) — the before number that worried you, and why it matters to
   whoever runs this system.
2. The change (1m) — what you did, on which layer; one sentence per change
   you kept.
3. The table (2m) — before and after, same suite; read the row that got
   *worse* out loud.
4. The failure (1m) — the before/after screenshot of what the user sees when
   it breaks.
5. The watch (30s) — the one metric you would alert on in production, and its
   threshold.

> Level 4 starts nothing new. It ends with the same system, measured, and a
> reason to trust it.
