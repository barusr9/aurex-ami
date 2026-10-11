# S5 User Trust Study — Facilitator Sheet

Print one copy per participant (P1, P2, P3, plus P4 for the re-test). About 30 minutes each.

## Before each participant

1. In a terminal, from `Project-Shree-Bhargava/`, run `tools/s5_reset.sh P1` (use P2, P3, P4 for later participants). This restarts Ami with fresh orders, so the hub can be cancelled and the AirPods returned again.
2. Open `http://localhost:4000` and log in as **demo1@cofy.ai / demo123**. Everyone uses demo1, because only demo1 has the three orders the tasks need.
3. Open `http://localhost:4000/logs` in a second tab. Note each turn's latency and cost there.
4. Read the consent blurb aloud and get a verbal yes:

> "This is a 20-minute test of a customer-support chatbot, not a test of you. I'll give you a few tasks. Please think out loud, especially at the moment you feel unsure, annoyed, or like you don't trust the answer. There are no wrong reactions. I'm looking for where the bot loses you. I'll take notes, and nothing is recorded unless you're okay with it. You can stop anytime."

Give the tasks one at a time, in plain words. **Don't tell them what to type.**

---

**Participant:** P&#95;&#95;&#95;&#95; &nbsp;&nbsp; **Date/time:** &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95; &nbsp;&nbsp; **Facilitator:** &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;

| # | Say this | Done? Y / N / gave up | Trust-break moment (their exact words) | Cause* | Latency ms / cost $ | Severity 1–5 |
|---|---|---|---|---|---|---|
| 1 | "Find out when your AirPods order arrived." | | | | | |
| 2 | "You changed your mind. Return those AirPods." | | | | | |
| 3 | "Cancel the USB-C hub that hasn't shipped yet." | | | | | |
| 4 | "Ask where your MacBook case is right now." | | | | | |
| 5 | "Ask it something it can't do, e.g. 'phone the driver and tell them to hurry.'" | | | | | |
| 6 | "Ask a general question: 'what's your return policy?'" | | | | | |

\*Cause: **L** latency · **W** wrong or vague answer · **R** unexpected refusal · **C** confirmation friction · **G** login wall · **T** tone or wording · **O** other

Severity: 1 = barely noticed · 5 = would abandon the bot.

**Watch for:** the login prompt (wall or reassurance?), the "are you sure?" confirmation (safe or friction?), a vague ETA on the MacBook case, whether an honest "I can't" keeps their trust, and pauses of 5–7 s with only "thinking…" on screen.

**Other notes:**

&nbsp;

&nbsp;

&nbsp;

---

## After all 3 sessions

Send Claude a photo of the sheets or type the rows in. Claude groups the trust-breaks by cause, redesigns the top 1–2 moments, and ships the change. Then P4 re-tests the task that broke trust.
