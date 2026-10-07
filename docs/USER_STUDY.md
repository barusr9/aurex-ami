# S5 — User Trust Study (turnkey kit)

**Goal (BRD #5):** 3 people use Ami, note where each *stopped trusting it*,
redesign that moment, test again.

This kit is everything you need to run the study. The agent cannot run it —
a human facilitator does. Budget ~30 min per participant.

---

## Before you start (5 min setup)

1. Start the app: `PORT=4000 python3 web.py`
2. Confirm it's up: open `http://localhost:4000`, log in once with
   `demo1@cofy.ai` / `demo123`, send "hi", then log out.
3. Open `http://localhost:4000/logs` in a second tab (stay logged in there) —
   you'll glance at it to see latency/cost per turn as the participant works.
4. Assign each participant their own account so sessions don't collide:

   | Participant | Account | Password |
   |---|---|---|
   | P1 | `demo1@cofy.ai` | `demo123` |
   | P2 | `demo2@cofy.ai` | `demo123` |
   | P3 | `demo3@cofy.ai` | `demo123` |

   (demo1's orders: `111-1111111` AirPods — *delivered*; `111-2222222`
   MacBook case — *shipped*; `111-3333333` USB-C hub — *preparing*.)

## Consent blurb (read aloud)

> "This is a 20-minute test of a customer-support chatbot, not a test of you.
> I'll give you a few tasks. Please think out loud — especially say the moment
> you feel unsure, annoyed, or like you don't trust the answer. There are no
> wrong reactions; I'm looking for where the bot loses you. I'll take notes;
> nothing is recorded unless you're okay with it. You can stop anytime."

Get a verbal yes before continuing.

---

## The tasks (give one at a time; don't explain how)

Hand the participant the goal in plain words. Do **not** tell them what to
type — watch how they phrase it and where they hesitate.

| # | Task (say this) | What it exercises | Trust-fragile moment to watch |
|---|---|---|---|
| 1 | "Find out when your AirPods order arrived." | auth + order lookup | Does the **login requirement** feel like a wall or a reassurance? |
| 2 | "You changed your mind — return those AirPods." | confirmation guardrail | The **"are you sure?" confirmation** — does it feel safe or like friction? |
| 3 | "Cancel the USB-C hub that hasn't shipped yet." | cancel flow | Same confirmation, different action — consistency of trust |
| 4 | "Ask where your MacBook case is right now." | tracking | Does the agent sound **confident or vague** about the ETA? |
| 5 | "Ask something it can't do — e.g. 'phone the driver and tell them to hurry.'" | honest refusal | Does an honest **"I can't do that"** keep or lose trust? |
| 6 | "Ask a general question: 'what's your return policy?'" | RAG, no auth | Does citing a **policy document** read as credible or robotic? |

## While they work — the facilitator sheet

For **each task**, jot:

```
Participant: ___   Task #: ___
Did they complete it?           Y / N / gave up
Trust-break moment (verbatim):  "______________________"
  (the sentence where they hesitated, frowned, or doubted the answer)
Cause (circle):  latency  |  wrong/vague answer  |  unexpected refusal  |
                 confirmation friction  |  login wall  |  tone/wording  |  other
Turn latency from /logs:  ____ ms     Cost: $____
Severity (1-5, 5 = would abandon): ___
```

One row per task per participant = up to 18 rows. The **trust-break moments**
are the deliverable.

---

## After all 3 sessions — analyze & redesign

1. **Cluster** the trust-break moments by cause. The one that recurs across
   participants is the one to fix first.
2. For the top 1–2 moments, write the **redesign**:

   | Trust-break moment | Why it broke trust | Redesign | Where to change it |
   |---|---|---|---|
   | e.g. "it asked me to confirm twice" | felt distrusted | one clear confirm, echo the exact action | `policy.py` / prompt |
   | e.g. "it took 5s, I thought it froze" | no feedback | a "working…" indicator | `ui/chat.html` |
   | e.g. "login felt like a brush-off" | wall, not reassurance | reword the login prompt as protective | `query_classifier.get_login_prompt` |

3. **Re-test:** run the one task that triggered the fixed moment with a 4th
   person (`demo4@cofy.ai`) and confirm the moment no longer breaks trust.

## Known trust-fragile spots (from engineering — watch these)

These are places we already suspect, from building the agent. Don't lead the
participant to them, but watch:

- **Latency:** turns take ~5s (p50 ~4.9s). Without a "working…" cue, people
  read the pause as a freeze. Strong redesign candidate.
- **Double confirmation:** destructive actions ask to confirm; if the wording
  varies or repeats, it reads as the bot not listening.
- **Login wall on the first account question** — necessary for security, but
  the *wording* decides whether it feels protective or dismissive.
- **Honest "I can't":** the agent is built to refuse rather than fake. Whether
  that *earns* or *loses* trust is exactly what this study measures.

## Satisfied when (S5 acceptance)

- [ ] 3 participants ran the tasks; trust-break moments logged (sheet above)
- [ ] Top 1–2 moments redesigned (table filled, change shipped)
- [ ] Re-tested with a 4th person; the moment no longer breaks trust
- [ ] Findings written up below

---

## Results (fill in after running)

_Date: ____  Facilitator: _____

**Trust-break moments observed:**
_(paste the clustered verbatim moments here)_

**Redesigned:**
_(what changed, where, and the before/after)_

**Re-test outcome:**
_(did the fixed moment hold for participant 4?)_
