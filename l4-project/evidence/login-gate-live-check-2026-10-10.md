# Goal 5, login gate and isolation: live before/after check, 2026-10-10

Same question, no login, sent to the chat endpoint of two builds on the same machine with the same class proxy key.

## Before: the class build (Balaji's starting point, Aurex commit 15b6b9b, stage2/web.py)

```
POST /chat {"message": "what is the status of order 112-3333333-3333333?"}
reply: Your Kindle Paperwhite 16GB is being prepared for shipment. Its estimated delivery date is October 14, 2026.
steps: get_order({"order_id": "112-3333333-3333333"}) -> full order record

POST /chat {"message": "what is the status of order 112-1111111-1111111?"}
reply: Order 112-1111111-1111111 for Sony WH-1000XM5 Headphones was delivered on October 6, 2026.
```

No login exists in that build. Anyone can read any customer's order (mei's and raj's above) by order number.

## After: aurex-ami master 317632a (web.py)

```
POST /chat {"message": "what is the status of order 112-3333333-3333333?"}
reply: Please log in to access your account information. You can ask me about policies and general questions without logging in.
steps: none, no tool called, no model call for the order

POST /chat {"message": "what is the return window?"}
reply: Under the Returns policy, most items can be returned within 30 days of delivery ...   (general question answered without login)
```

## Isolation at the policy layer (the PR #2 review fix, a77e42d / 317632a)

`tests/test_policy_scope.py` run against both commits with the placeholder key:

| Commit | Result |
|---|---|
| 858e9aa (PR branch before the review fix) | 3 failed, 1 passed: an injected `scope` in the tool arguments read another customer's order |
| 317632a master | 4 passed; plus `tests/test_auth.py`, 23 passed in all |

Related frozen eval case on merged master: `complaint: cannot see another customer's order` PASS (results/evals_merged_master.json).

## What is still open for goal 5

The brief's success test, three people use it and the trust-break is redesigned and re-tested, has not been run. Kit is ready (`docs/S5-facilitator-sheet.md`, `tools/s5_reset.sh`).
