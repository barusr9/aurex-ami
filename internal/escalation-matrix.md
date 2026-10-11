# Escalation matrix (internal)

Who handles a human hand-off, by issue type. Ami reads this table when it opens
a ticket: it picks the row, routes the ticket to that department, and copies the
next steps into the ticket. **Internal only.** This file lives outside
`knowledge/`, so it is never indexed for customer answers.

Contacts below are placeholders for the L4 project, not real people.

Columns: `Category` is the stable id used in code and as a Jira label.
`Triggers` are words in the agent's summary that select the row (first match
wins, top to bottom; order status can also select a row, see `ami/routing.py`).
`Next steps` are separated by `;`.

| Category | Triggers | Department | Contact | Priority | SLA | Next steps |
|---|---|---|---|---|---|---|
| damaged_or_wrong_item | damaged, broken, defective, wrong item, missing item, missing part | Returns & Quality | Priya Nair, returns-quality@ami.example | High | 4 business hours | Ask the customer for photos of the item and packaging; Check the order's carrier and warehouse; Offer a replacement or a prepaid return label; Log the defect against the item SKU |
| delivery_delay | late, delayed, delay, not arrived, never arrived, hasn't arrived, stuck, lost, tracking, where is | Logistics & Fulfilment | Marco Diaz, logistics@ami.example | High | 4 business hours | Check the latest carrier scan for the order; If no scan in 48 h, open a trace with the carrier; Confirm a revised ETA with the customer; If lost, offer a reshipment or a refund per the Shipping policy |
| returns_refunds | refund, return, money back, reimburse | Returns & Refunds | Aisha Khan, refunds@ami.example | Normal | 1 business day | Confirm the order is inside the 30-day return window; Check whether a return or RMA already exists; Issue the RMA or explain the refund timeline (3-5 business days) |
| cancellation | cancel, cancellation | Order Management | Tom Becker, orders@ami.example | High | 2 business hours | Check whether the order has shipped; If not shipped, cancel and confirm the refund; If shipped, explain the return route instead |
| account_access | log in, login, password, locked, account, sign in | Customer Accounts | Lena Park, accounts@ami.example | Normal | 1 business day | Verify identity through the account's registered email; Reset access; Check the audit log for suspicious activity |
| payment_billing | charge, charged, billing, payment, card, invoice, double | Billing | Raj Patel, billing@ami.example | High | 4 business hours | Compare the charge with the order total; Check for duplicate or pending authorisations; Refund any overcharge and confirm by email |
| general_complaint | (default) | Customer Care | Sam Ortiz, care@ami.example | Normal | 1 business day | Read the conversation and the agent's summary; Reply to the customer within the SLA; Re-route to the right team if the issue fits a row above |

## Escalate further when

- The customer has escalated twice in 7 days, or mentions legal action or a regulator: copy **Customer Care Lead** (Dana White, care-lead@ami.example).
- Any security concern (account takeover, data exposure): page **Security on-call** (security@ami.example) and set priority High.
