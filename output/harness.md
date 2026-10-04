# Campus Customs — Harness

This is the full reference for the Campus Customs agent system. Its sections are:
1. Database tables
2. MCP tools
3. The five agents
4. Safety and business rules
5. Approval flow (payments and human sign-off)
6. Limits
7. API routes
8. React dashboard
9. Audit trail
10. Final run (Problem 9)

Source: `data/campus_customs.db` (original, untouched)
Working copy for later problems: `data/campus_customs_new.db` (byte-identical copy, SHA-1 `f447ca6a…109ea4c`)

All schema and values below were read directly from the database. The database contains exactly nine tables.

---

## desk

**Fields:** `date_today` (TEXT, NOT NULL), `notes` (TEXT)

**Contents:** A single row holding the shop's current operating date (`2026-08-31`); `notes` is empty.

**Why it matters to the agents:** It is the agents' "clock" — every due-date, overdue, and lead-time judgment (rent due, invoice past due, vendor delivery timing) should be measured against `date_today`, not the real-world date.

---

## tickets

**Fields:** `id` (INTEGER, PK), `type` (TEXT, NOT NULL), `requester` (TEXT, NOT NULL), `subject` (TEXT, NOT NULL), `sku` (TEXT), `size` (TEXT), `qty` (INTEGER), `lease_id` (INTEGER, FK → `leases.id`), `invoice_id` (INTEGER, FK → `invoices.id`), `status` (TEXT, NOT NULL), `notes` (TEXT), `created_at` (TEXT, NOT NULL)

**Contents:** The work queue — 3 rows, all `status = open`: a customer order (101), a rent notice (102), and a price-override request (103). Optional columns (`sku`, `size`, `qty`, `lease_id`, `invoice_id`) link each ticket to the relevant records in other tables.

**Why it matters to the agents:** This is the agents' input — each ticket is a task to triage and resolve, and its foreign-key-style columns tell the agent which other tables to look up.

---

## inventory

**Fields:** `sku` (TEXT, NOT NULL), `name` (TEXT, NOT NULL), `size` (TEXT, NOT NULL), `qty` (INTEGER, NOT NULL), `location` (TEXT, NOT NULL); PK = (`sku`, `size`)

**Contents:** 10 rows of on-hand stock by SKU and size, with aisle location. Four products: Basic Hoodie Big Yale (`CC-HOOD-NAVY`, S/M/L/XL = 4/8/14/6), Classic Bulldog Tee (`CC-TEE-WHITE`, S/M/L/XL = 0/5/3/2), Yale Cap (`CC-HAT-BLUE`, OS = 40), Crest Mug (`CC-MUG-CREST`, OS = 0).

**Why it matters to the agents:** Agents must check stock before promising or fulfilling any order — e.g., whether a size is available or must be reprinted/sourced from a vendor.

---

## pricing

**Fields:** `sku` (TEXT, PK), `unit_cost` (REAL, NOT NULL), `list_price` (REAL, NOT NULL)

**Contents:** 4 rows of cost and retail price per SKU: hoodie $22 / $58, tee $8 / $28, cap $6 / $22, mug $3.50 / $14.

**Why it matters to the agents:** Provides the margin floor for any discount or price-override decision — an agent can compute how deep a discount can go before selling below cost.

---

## vendors

**Fields:** `id` (INTEGER, PK), `name` (TEXT, NOT NULL), `specialty` (TEXT, NOT NULL), `lead_days` (INTEGER, NOT NULL)

**Contents:** 3 suppliers: (1) Bulldog Print Co — apparel reprint, 5 lead days; (2) Elm City Gifts — mugs and small goods, 3 days; (3) QuickShip CT — local courier, 1 day.

**Why it matters to the agents:** Tells agents who can restock or deliver an item and how long it will take, which determines realistic fulfillment dates for out-of-stock orders.

---

## leases

**Fields:** `id` (INTEGER, PK), `space_name` (TEXT, NOT NULL), `landlord` (TEXT, NOT NULL), `monthly_rent` (REAL, NOT NULL), `next_due` (TEXT, NOT NULL), `notes` (TEXT)

**Contents:** 1 row — the Chapel Street shop, landlord Elm City Properties, $2,400/month, next due `2026-09-02`; `notes` empty.

**Why it matters to the agents:** The authoritative record for verifying rent requests — agents should confirm landlord, amount, and due date here rather than trusting the ticket/email text.

---

## cash_accounts

**Fields:** `name` (TEXT, PK), `balance` (REAL, NOT NULL), `date` (TEXT, NOT NULL)

**Contents:** 1 row — `checking`, balance $3,400.00 as of `2026-08-31`.

**Why it matters to the agents:** Constrains what can actually be paid; agents must check available cash before committing to any payment and consider competing obligations.

---

## payments

**Fields:** `id` (INTEGER, PK), `kind` (TEXT, NOT NULL), `ref_id` (INTEGER), `amount` (REAL, NOT NULL), `account` (TEXT, NOT NULL), `paid_at` (TEXT, NOT NULL), `approved_by` (TEXT, NOT NULL)

**Contents:** Empty (0 rows). Its structure is a payment ledger: what kind of obligation was paid, the referenced record (`ref_id`), amount, source account, timestamp, and who approved it.

**Why it matters to the agents:** This is where any payment an agent makes gets recorded; `approved_by` (NOT NULL) implies every payment needs an accountable approver, making it a key control/audit point.

---

## invoices

**Fields:** `id` (INTEGER, PK), `vendor_id` (INTEGER, NOT NULL, FK → `vendors.id`), `amount` (REAL, NOT NULL), `due_date` (TEXT, NOT NULL), `status` (TEXT, NOT NULL), `description` (TEXT)

**Contents:** 1 row — invoice 501 from vendor 1 (Bulldog Print Co), $840.00, due `2026-08-28`, `status = open`, "Rush reprint CC-TEE-WHITE S".

**Why it matters to the agents:** Shows outstanding vendor bills; agents need it to see which obligations are owed (and overdue) and how vendor work ties back to inventory and customer orders.

---

## Relationships

- `tickets.lease_id` → `leases.id`
- `tickets.invoice_id` → `invoices.id`
- `invoices.vendor_id` → `vendors.id`
- `tickets.sku` / `tickets.size` → `inventory (sku, size)` and `pricing.sku` (by value; not declared FKs)
- `payments.ref_id` / `payments.account` → presumably the paid record and `cash_accounts.name` (by value; not declared FKs)

---

## MCP Tools

Server: `mcp_server/server.py` (FastMCP, stdio). It connects only to `data/campus_customs_new.db`. Every tool opens the database read-only except `record_payment`, which is the only write tool and is human-only. "Today" is always `desk.date_today`.

| Tool | Tables | Purpose | Used by |
|---|---|---|---|
| `check_order_fulfillment(ticket_id=101)` | tickets, inventory, pricing, invoices, vendors, desk | Ticket 101 view: stock for the requested SKU/size, list price, linked invoice with days overdue and vendor lead time | inventory |
| `verify_rent_notice(ticket_id=102)` | tickets, leases, cash_accounts, invoices, desk | Ticket 102 view: requester vs. lease landlord, rent, days until due, cash before/after rent and open invoices | facilities |
| `evaluate_bulk_discount(ticket_id=103, discount_pct=None)` | tickets, inventory, pricing, vendors | Ticket 103 view: shortfall, all sizes, cost vs. list, maximum discount before a loss, optional discount math | inventory, accounting |
| `get_desk_date()` | desk | Shop's operating date | all agents |
| `get_ticket(ticket_id)` | tickets, desk | One ticket of any type | all agents |
| `list_open_tickets()` | tickets, desk | All open tickets (competing obligations) | boss |
| `get_inventory(sku, size=None)` | inventory | On-hand quantity and location by SKU/size | inventory, customer_service |
| `get_pricing(sku)` | pricing | Unit cost, list price, unit margin, maximum discount before a loss | accounting, customer_service |
| `check_vendor_status(vendor_id=None)` | vendors, invoices, desk | Unpaid invoices per vendor, `can_ship_new_product`, earliest arrival (desk date + `vendors.lead_days`) | inventory, accounting |
| `get_restock_options(sku, size, qty_needed)` | inventory, vendors, invoices, desk | Shortfall, every vendor with lead time and can-ship status, past invoices mentioning the SKU, explicit `data_gaps` | inventory |
| `get_invoices(status, vendor_id, invoice_id)` | invoices, vendors, desk | Invoices with days overdue | accounting |
| `get_cash_position()` | cash_accounts, invoices, leases, desk | Balances, open invoices, upcoming rent, cash left after each | accounting, facilities |
| `get_lease(lease_id)` | leases, desk | Landlord, rent, next due, days until due | facilities |
| `get_payments(kind, ref_id)` | payments | Payments already recorded (prevents double payment) | accounting |
| `prepare_payment_plan(items, account)` | leases, invoices, vendors, cash_accounts, payments, desk | Read-only check of rent/invoice payments in order against a running balance. Amounts come from the DB; flags overdrafts and already-paid items; everything is `pending_human_approval` | accounting |
| `record_payment(kind, ref_id, approved_by, account)` | **writes** payments, cash_accounts, invoices (status → `paid`) or leases (`next_due` + 1 month); reads desk | Executes one human-approved payment. Refuses if the approver is empty or an agent name, the invoice is not open, or cash would go negative. `paid_at` = desk date | **human only** (`backend/approve_payment.py`, via its CLI or the API approve route) |

There is no tool that adds cash.

---

## Agent Team (Problem 5)

Code: `backend/agents.py` (team, delegation, validators, CLI), `backend/models.py` (shared Pydantic types), `backend/config.py` (model, MCP, limits), `backend/audit.py`, `backend/db_reset.py`, `backend/approve_payment.py`. Prompts: `backend/prompts/{boss,inventory,accounting,facilities,customer_service}.md`.

Every agent is a PydanticAI `Agent` on **gpt-6-luna through Portkey**, using the OpenAI Responses API with `PORTKEY_API_KEY` from the AI Foundations root `.env`. `build_model()` refuses any other model. All five agents share one stdio connection to the MCP server per ticket run, and each sees only its own role's tools. No agent has direct database access.

| Agent | Role | Output |
|---|---|---|
| **Boss** | Owns the ticket, decides which agents to involve, coordinates, reconciles their reports, and makes the final recommendation | `TicketDecision` (recommendation, rationale, cited facts, proposed actions, drafts, payment requests, one check per shop rule, missing data; status `recommendation_pending_human_review`) |
| **Inventory** | Stock by SKU/size, shortages, alternative sizes, vendor restock options and lead times | `SpecialistReport` |
| **Accounting** | Invoices, cash, margins and discounts, payments already made, payment plans and their cash implications | `SpecialistReport` |
| **Facilities** | Leases, rent, landlord verification, shop-space issues | `SpecialistReport` |
| **Customer Service** | Customer-facing drafts and customer-impact summaries | `SpecialistReport` |

**Full connectivity.** Every agent has an async `delegate(agent, task)` tool that can target any other agent. The tool runs that agent, awaits its report, and returns it so the caller can keep reasoning. Several `delegate` calls in one model turn run in parallel. Sub-agents can delegate onward; for example, Inventory → Accounting happened in the ticket 101 runs.

**Run it from the CLI** (the API in Problem 7 wraps the same functions):

```bash
.venv/bin/python backend/agents.py          # full run: reset DB, then tickets 101, 102, 103
.venv/bin/python backend/agents.py 102      # one ticket, no reset
.venv/bin/python backend/approve_payment.py invoice 501 --approved-by "Your Name"   # human approval
.venv/bin/python backend/db_reset.py        # manual reset to original values
```

---

## Safety Rules and Enforcement

| # | Rule | How it is enforced |
|---|---|---|
| 1 | Use `desk.date_today` as the shop's current date for overdue/due-date decisions | All MCP date math uses `desk.date_today`, never the system clock. Boss's output validator requires the desk date to have been read and stamps it on the decision. Prompts. |
| 2 | Vendor lead times come from the `vendors` table | Lead times reach agents only as `vendors.lead_days` (and desk date + `lead_days` arrival dates) from MCP tools. Prompts forbid estimating. |
| 3 | A vendor with an open, unpaid invoice cannot ship new product | `check_vendor_status` and `get_restock_options` return `can_ship_new_product=false` with a reason. The validator rejects any `vendor_restock` action whose vendor status wasn't checked in this run, or whose vendor is blocked but has no `blocked_by`. |
| 4 | Every payment requires human approval | `PaymentRequest.approval_status` is the literal `pending_human_approval`. `record_payment` is in no agent's toolset, and the MCP call hook hard-blocks it (and any tool outside the agent's role). Only `approve_payment.py` triggers it, and only after a human types `APPROVE` at an interactive terminal. See **Payment Architecture**. |
| 5 | If a payment is made, update the relevant tables | `record_payment` does it in one transaction: inserts into `payments` (with `approved_by` and `paid_at` = desk date), decrements `cash_accounts.balance`, and sets `invoices.status='paid'` or advances `leases.next_due` by one month. |
| 6 | Not enough cash → the payment tool refuses; never a negative balance | `record_payment` raises "Refused: not enough cash…" and rolls back. `prepare_payment_plan` marks overdrafts not feasible. The validator rejects payment requests not confirmed feasible, with amounts that differ from the DB, or whose total exceeds cash. |
| 7 | Cash only goes out; never invent incoming revenue | No MCP tool adds cash. Prompts forbid counting order value, expected sales, or deposits toward available cash. |
| 8 | Communications are drafts only | `DraftMessage.status` is the literal `draft` and `sent` the literal `False`. No send/email tool exists. Prompts forbid implying anything was sent. |
| 9 | Never invent missing business data | Every `Fact` must cite an MCP tool the agent actually called in this run, an agent it delegated to, or the agent that requested the work. Otherwise the validator rejects the output. Gaps go to `missing_data`, and `get_restock_options` lists known DB gaps. |
| 10 | Reset `campus_customs_new.db` before a full run | `run_all_tickets()` (the default CLI) calls `reset_db()` first. It copies `campus_customs.db` over the working copy, verifies byte-identical SHA-1, and audits it. |
| 11 | Only gpt-6-luna through Portkey | `MODEL_NAME` is hard-coded (not env-overridable), and `build_model()` raises if it changes. One model object is shared by all five agents. |

| 12 | Tickets resolve only when the required human work is done | Ticket status is computed by the backend (see **API Routes → Ticket status**). Payments must be approved, and every other outstanding human action must be signed off by a named human through `POST /api/tickets/{id}/signoffs`. A finished run alone never resolves a ticket. |

Rejected outputs are sent back to the model as `ModelRetry` with the reason, and logged as `output_rejected`.

---

## Payment Architecture

There is exactly **one** code path that changes shop data: the MCP tool `record_payment` in `mcp_server/server.py`. Nothing in `backend/` opens the shop database or contains SQL. `grep` finds no `sqlite3` import or query anywhere in `backend/`.

```
agents (Accounting)                         human (shop owner)
   │ prepare_payment_plan  (MCP, read-only)    │ backend/approve_payment.py <kind> <ref_id> --approved-by "<name>"
   ▼                                           │   1. MCP prepare_payment_plan → shows payee, amount, cash before/after
 TicketDecision.payment_requests               │   2. requires an interactive TTY and the typed word APPROVE
 (pending_human_approval; nothing paid)        │   3. MCP record_payment(kind, ref_id, approved_by)
                                               ▼
                         mcp_server/server.py · record_payment   ← the only DB write in the system
                           one SQLite transaction (BEGIN IMMEDIATE … COMMIT / ROLLBACK):
                           • re-reads the amount from invoices / leases (never taken from the caller)
                           • refuses: empty or agent-name approver, invoice not open, missing record, cash < amount
                           • INSERT payments (paid_at = desk.date_today, approved_by)
                           • UPDATE cash_accounts.balance
                           • UPDATE invoices.status = 'paid'  |  UPDATE leases.next_due = next_due + 1 month
```

- **Agents cannot reach it.** `record_payment` is in no agent's `TOOL_ACCESS` list. The agent-side MCP hook also hard-blocks it (`HUMAN_ONLY_TOOLS`), and a module-level assertion fails if it is ever added to a role.
- **`approve_payment.py` is only a trigger.** It defines two functions that call MCP tools: `prepare_payment()` (→ `prepare_payment_plan`) and `execute_payment()` (→ `record_payment`). Both the terminal CLI and the API approve route (Problem 7) use them, so there is one human-approval flow. It has no database access and contains no SQL; it only appends audit entries.
  - **CLI:** needs an interactive terminal and the typed word `APPROVE`. Non-interactive stdin, end-of-input, or any other reply → nothing is paid.
  - **API:** needs a prepared approval request, a human `approved_by`, and `confirm: "APPROVE"`.
- **Verified 2026-10-03** by driving the CLI through a real pseudo-terminal:
  - reply `no` → declined;
  - `APPROVE` invoice 501 → paid, cash $3,400 → $2,560, invoice `paid`;
  - `APPROVE` 501 again → refused (not open);
  - `APPROVE` rent → paid, cash → $160, `next_due` 2026-09-02 → 2026-10-02;
  - `APPROVE` rent again → refused (cash would go negative).
  - Afterwards the DB was reset to the original.
- **`db_reset.py`** is not a shop tool. It's an admin file copy (original DB → working copy, SHA-1 verified) run before a full run. It does not read or write individual records.

---

## Approval Flow (payments and human sign-off)

The agents only ever **propose**. Two human steps close a ticket.

**1. Payment approval** (the only path that changes shop data)
1. Accounting runs MCP `prepare_payment_plan` (read-only). The Boss's decision lists the feasible items as `payment_requests`, all `pending_human_approval`.
2. The human opens an approval request: `POST /api/payments/requests` with the `run_id`, so it must match a payment the run proposed. The amount is never sent by the client.
3. The human approves: `POST /api/payments/requests/{id}/approve` with a human name and `confirm: "APPROVE"`. In the dashboard the button stays disabled until a name is entered and the confirm box is checked.
4. `approve_payment.execute_payment()` calls MCP `record_payment`, which re-reads the amount, refuses an overdraft or an agent-name approver, and in one transaction writes `payments`, `cash_accounts`, and `invoices`/`leases`.
5. Decline (`…/decline`) pays nothing, and the ticket goes back to `open` for re-work.

**2. Human sign-off** (for non-payment follow-ups; writes nothing to the shop DB)
- `POST /api/tickets/{id}/signoffs` with `run_id`, the exact `action` text from `outstanding_actions`, a human `signed_off_by`, a `note`, and `confirm: "SIGN OFF"`.
- It is refused for agent names, for a run that isn't the ticket's current one, for an action that isn't outstanding, or while the ticket is running.
- It is recorded as a `human_signoff` audit event. Ticket status subtracts signed-off actions.
- **Only decisions needed now count** (`models.classify_human_actions`, shared by the Boss validator and the API):
  - **One sign-off per draft:** the automatic "Send or discard draft" item is added only when the Boss didn't already list an action to send that draft.
  - **Conditional steps don't need sign-off:** an action with `conditional_on` (e.g. "Tauhid's reply asking to wait for size S") is shown as *waiting on others*.
  - **Guardrails:** a pricing decision can never be conditional, and a draft whose send action is marked conditional still needs its own sign-off.
- Signing off a draft means a human approved it for the owner to send. **The system never sends anything**: there is no send tool, and `DraftMessage.sent` is the literal `false`.

A ticket is **resolved** when every payment its current run proposed was approved and recorded, and every other required human action was signed off, or when the Boss's decision needs nothing further.

---

## Token / Loop / Delegation Limits

Set in `backend/config.py`. The limits are sized at about 1.5× the peak usage seen across six successful runs before tightening (peak: 61.2k tokens, 8.1k output tokens, 17 requests, 24 tool calls, 4 delegations, depth 2, 30 s per delegation). They replace the original 400k-token / 60-request / 80-tool-call / 10-delegation / depth-3 / 240 s limits.

| Limit | Value | Behavior when hit |
|---|---|---|
| Total tokens per ticket | **90,000** | `UsageLimitExceeded`; the ticket run fails and is audited (`ticket_run_failed`) |
| Output tokens per ticket | **14,000** | Same |
| Model requests per ticket | **25** | Same |
| Tool calls per ticket | **35** | Same |
| Output tokens per model response | **4,000** (reasoning included) | Response is cut off at the cap |
| Sub-agent cutoff (same shared counter) | **75,000** tokens / **11,000** output / **21** requests / **31** tool calls | The sub-agent stops early and `delegate` returns `ok=false` to its caller. The Boss keeps a reserve of 15k tokens, 3k output, 4 requests, and 4 tool calls to finish its decision |
| Max delegation depth | **2** (boss = 0) | `delegate` is hidden from depth-2 agents; calls past it are refused |
| Max delegations per ticket | **6** | `delegate` is hidden once the budget is spent; extra calls return a blocked result |
| Delegation timeout | **90 s** per sub-agent run | Returns a failed result to the caller, which finishes with what it has |
| Self-delegation | not allowed | Returns a blocked result |
| Repeated delegation (same agent + same task) | served from cache | Not re-run; doesn't consume budget (`delegation_cache_hit`) |
| Retries per agent run | 2 | Tool-error and output-validation retries |

One `RunUsage` object is shared by the Boss and every sub-agent (`usage=ctx.usage`), so all of these limits are per **ticket**, not per agent.

**Runaway test (offline, scripted models).** A sub-agent that called tools forever was stopped at the 21-request sub-agent cutoff, and `delegate` returned `UsageLimitExceeded` to the Boss. The Boss then finished its decision at 22 of 25 requests. This test is the audit run `57bc195dadb1`, logged under ticket 101.

**Verified live runs with the final limits:**

Final full run (DB reset first, Portkey cache bypassed) on 2026-10-03:

| Ticket | Run id | Total tokens (limit 90k) | Output tokens (14k) | Requests (25) | Tool calls (35) | Delegations (6) | Outcome |
|---|---|---|---|---|---|---|---|
| 101 | `e51869ee7156` | 54,728 | 7,239 | 15 | 14 | 3 | No payment request. Ask Tauhid Zaman about another size. Size S restock is blocked by invoice 501 |
| 102 | `76eede182bc5` | 26,493 | 3,401 | 8 | 12 | 2 | Pay invoice 501 ($840), then rent ($2,400), both pending human approval; leaves $160 |
| 103 | `e90bbb7d2970` | 42,535 | 5,207 | 12 | 14 | 3 | 8 of 20 in stock. $22 floor. No discount quoted; a human decides the price |

The highest-usage run under the final limits peaked at 58.1k tokens, 7.5k output tokens, 16 requests, 24 tool calls, and 4 delegations, all inside the limits. No run hit a limit, a delegation block, or a validator rejection.

Note: Portkey caches identical requests. Repeat runs with the same prompts can return identical, cached results (identical token counts are the giveaway). The final verification therefore sent `x-portkey-cache-force-refresh: true` through a one-off script. The app itself is unchanged.

The Boss and Accounting prompts now also state two policies that pin the outcomes:
1. Payment requests appear only on tickets about paying something; on payment tickets the plan covers every due or overdue obligation, in due-date order.
2. No agent picks a discount percentage that neither the ticket nor a human gave.

The final outcomes match the original Problem 5 baseline:
- **101:** no payment; ask about M/L/XL; size S restock blocked by invoice 501.
- **102:** pay invoice 501, then rent, both pending human approval, leaving $160.
- **103:** only 8 of 20 in stock; $22 floor; no discount committed; the decision goes to a human.

---

## API Routes (Problem 7)

`backend/main.py` (FastAPI). Run it from `backend/` with the venv active: `uvicorn main:app --reload --port 8000`.
- **Shop facts and payments:** every route reads shop facts through one shared MCP connection (`backend/mcp_client.py`).
- **Ticket runs:** use the Problem 5 agent team (`agents.run_ticket_detailed`).
- **Payments:** use the `approve_payment.py` flow, so MCP `record_payment` is the only DB write and there is no SQL in `backend/`.
- **CORS:** allows `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, and `http://127.0.0.1:3000`; override with the `CORS_ORIGINS` env var. Other origins are rejected.

- `GET /api/health`: API status, model name, and desk date (MCP `get_desk_date`).
- `GET /api/tickets`: tickets 101, 102, 103 (MCP `get_ticket`), each with `status` (open/pending/resolved), `status_reason`, `pending_payments`, `outstanding_actions`, `signed_off_actions`, `running`, and its latest run's recommendation.
- `GET /api/tickets/{ticket_id}`: one ticket with the same fields. Unknown id → 404; non-integer or ≤0 → 422.
- `POST /api/tickets/{ticket_id}/run`: runs the agent team on the ticket and waits for the Boss's decision, run id, usage, agents run, and the ticket's resulting status. A finished run alone never resolves a ticket. Unknown ticket → 404 (no agents start); already running → 409; agent failure → 502.
- `POST /api/tickets/{ticket_id}/signoffs`: body `{run_id, action, signed_off_by, note, confirm: "SIGN OFF"}`. A named human signs off one outstanding non-payment action of the ticket's current run (recorded as audit `human_signoff`; nothing is sent, paid, or written to the DB). Returns the updated ticket.
  - Agent name → 403; bad confirm → 422; not the current run, not outstanding, or ticket running → 409; unknown ticket → 404.
- `GET /api/events?limit=&ticket_id=&run_id=&since_seq=&include_results=`: recent audit events, plus `agent_activity` showing what each agent said, who asked it, and which MCP tools it used.
- `GET /api/cash`: current checking balance and as-of date, open invoice total, and upcoming rent (MCP `get_cash_position`).
- `POST /api/payments/requests`: body `{kind, ref_id, account?, ticket_id?, run_id?}`. Prepares a payment with MCP `prepare_payment_plan` and opens a 15-minute human approval request; nothing is paid.
  - Not payable (would overdraw, already paid) → 409; missing record → 404.
  - With a `run_id`, the payment must be one that run proposed, otherwise 422.
- `GET /api/payments/requests`: all approval requests with status (pending, approved, refused, declined, expired, cancelled_by_reset).
- `POST /api/payments/requests/{id}/approve`: body `{approved_by, confirm: "APPROVE"}`. Executes the payment through MCP `record_payment`, which updates `payments`, `cash_accounts`, and `invoices`/`leases`.
  - Agent-name approver → 403; missing confirm → 422; already decided → 409; expired → 410; unknown → 404.
  - Not enough cash → 409, refused by MCP and nothing written.
- `POST /api/payments/requests/{id}/decline`: body `{declined_by}`. A human declines a pending request; nothing is paid.
- `POST /api/reset`: restores `data/campus_customs_new.db` to the original `campus_customs.db` values (SHA-1 verified), cancels pending approval requests, and re-opens all tickets. Blocked with 409 while a ticket is running.

**Ticket status.** Status is computed in `backend/events.py` from the latest completed agent run since the last DB reset, plus the human payment decisions recorded after that run. Finishing an agent run never resolves a ticket by itself.

| Status | When |
|---|---|
| `open` | No agent run since the last reset, **or** a payment the run proposed was declined or refused (insufficient cash), so the ticket needs re-work |
| `pending` | The run proposed payments still awaiting human approval, **and/or** its recommendation leaves other human work |
| `resolved` | Every payment the run proposed was approved and recorded via MCP `record_payment`, and every other required human action was signed off (`POST /signoffs`), **or** the Boss's decision has no payments and no outstanding human action |

- **What counts as "other human work":** `models.outstanding_human_actions()` is one rule shared by the Boss's output validator and the API.
  - These always count: every draft (it still has to be sent or discarded); any action that needs approval or is blocked, of kind customer/vendor communication, pricing decision, vendor restock, or fulfill from stock; and a conditional payment action with no actual payment request.
  - The only thing that doesn't count: an action the Boss marks `satisfied_by_payment_approval`, meaning a check the approver does as part of approving a listed payment (e.g. "confirm the notice amount matches the lease before approving rent"). The mark is ignored for the kinds above and when the decision lists no payments.
  - `other_human_action_required` and `awaiting_payment_approval` on the decision are set by code, not by the model.
- **Matching payments:** decisions are matched by `(kind, ref_id)` against `payment_recorded`, `payment_declined_by_human`, and `payment_refused` audit entries after the run; the latest one wins. So a declined payment that a human later approves still resolves the ticket.
- **Other fields:** a reset re-opens all three tickets. The raw `tickets.status` column is still returned as `db_status`; the shop DB is never written outside `record_payment`.
- **Non-payment follow-ups** (drafts to send, pricing decisions, conditional restocks) are completed by human sign-off (added in Problem 9; see **Approval Flow**). Before that route existed, tickets 101 and 103 could only stay `pending`.

**Status scenarios tested 2026-10-03** (live server):

| Scenario | Result |
|---|---|
| Agent run with no approval needed | `resolved` immediately: "The Boss concluded no further action is needed." This used a scripted Boss through the real `run_ticket` path (run `e1236a14d4c7`, ticket 103), because no real ticket produces a no-action decision |
| Agent run with payments waiting (102, live run `279f343725c4`) | `pending`: awaiting approval of invoice #501 and rent #1. The Boss marked "confirm the notice amount" as `satisfied_by_payment_approval`, so no other actions were outstanding |
| Agent run with other human action (101, live run `5d8433d4b027`) | `pending`: 5 outstanding actions (customer draft, conditional payment, restock) |
| Approve invoice 501 | 102 stays `pending` (rent still awaiting approval) |
| Decline rent | 102 → `open`: "rent #1 was declined — the ticket needs to be re-worked" |
| Human later approves rent | 102 → `resolved`: all proposed payments approved, no other action remains |
| Database reset | All three → `open`; `latest_run` is null |

A live re-run of 102 after both payments were made correctly stayed `pending`. The Boss spotted that the "due in 2 days" email no longer matched the lease (rent paid, next due 2026-10-02) and drafted a clarification request to the landlord. The full route suite was re-run after this change: 39/39.

**Tested 2026-10-03** against the live server (`uvicorn main:app --reload --port 8000`): 39/39 scripted checks passed, plus decline and unknown-request checks. Covered:
- **Tickets:** valid id (101) and invalid ids (999 → 404; 0, -5, abc → 422).
- **Runs:**
  - a live run of 102: Boss → Facilities → Accounting, with both payments proposed and the ticket shown `pending` (after the status change; it was `resolved` under the original rule);
  - a concurrent duplicate run → 409, and reset during a run → 409.
- **Events:** each agent's statement and tools.
- **Payments:**
  - preparing pays nothing;
  - agent approver → 403;
  - human approval of invoice 501: $3,400 → $2,560 and the invoice is marked paid;
  - double approval → 409;
  - two rent requests prepared at $2,560: the first is approved (→ $160) and the second is refused by MCP for insufficient cash (409, balance stays $160);
  - preparing rent at $160 → 409.
- **CORS:** allowed from localhost:5173, rejected for other origins.
- **Reset:** back to $3,400, all tickets open, invoice 501 open.

The DB was then reset to the original. The ticket-102 run returned in 4 s because Portkey served cached model responses for an identical prompt; the MCP tool calls still ran live.

---

## Dashboard (Problem 8)

`frontend/` is a React 19 + Vite + TypeScript app (`npm run dev` → http://localhost:5173). It only calls the API routes above (`VITE_API_BASE`, default `http://localhost:8000`). Design notes are in `output/design.md`.

- **Header:**
  - a *Human operator* name field, used for every approval and sign-off;
  - the live checking balance (animated, amber below $500);
  - a two-step **Reset shop**, disabled while a ticket runs.
- **Left:** ticket cards with the backend's `open` / `pending` / `resolved` chip, a running scan line, and a "payments awaiting approval" alert.
- **Center:**
  - the ticket hero with the run button and the backend status reason;
  - the **delegation flow** SVG: five agent nodes, animated connectors and a moving particle for in-flight delegations, solid when done;
  - the **human approval** panel: open request → confirm → approve or decline, with a cash before/after bar;
  - the **Boss decision**: recommendation, a sign-off control for each outstanding action, drafts stamped "not sent", rule checks, rationale and facts;
  - **agent summaries**: what each agent said, who asked it, who it delegated to, and its MCP tools.
- **Right:** the live **event feed** (tool calls, delegations, reports, rejections, decision).
- **Polling:** every 1.2 s while the selected ticket runs, otherwise slower. Everything refreshes after runs, approvals, declines, sign-offs, and reset.
- **Source of truth:** the backend's status is never inferred from "the run finished". Runs from before a reset are hidden from the run panels.

---

## Audit Trail

`output/audit_trail.json` is an append-only JSON array. Each write takes a cross-process `fcntl` lock, reads, appends, and atomically replaces the file. It refuses to write if the file isn't a valid array, so old entries are never wiped. Each entry has `seq`, `timestamp`, `run_id`, `ticket_id`, `agent`, and `event`.

Events:
- `ticket_run_started`, `ticket_run_completed` (with usage and the full decision), `ticket_run_failed`
- `mcp_tool_call` (args and result; the result is truncated past 1,500 characters), `mcp_tool_error`, `mcp_tool_blocked`
- `delegation_started`, `delegation_completed`, `delegation_blocked`, `delegation_failed`, `delegation_cache_hit`
- `output_rejected`
- `db_reset`
- `payment_approval_requested` (API), `payment_recorded`, `payment_refused`, `payment_declined_by_human` (with `via: cli` or `via: api`)
- `human_signoff` (ticket, run, action, signed_off_by, note)
- `delegation_completed` also stores the sub-agent's full report (used by `GET /api/events`)

Development entries are kept too:
- 100 `audit_selftest` entries from the cross-process lock test
- one `ticket_run_failed` from the first Chat Completions attempt
- the scripted runaway-limit test run (`57bc195dadb1`, logged under ticket 101)
- the human-approval test entries (`run_id: human_approval`, approver "Test Human")
- the full runs made while tuning the limits

---

## Final Run (Problem 9) — all three tickets resolved

Run on 2026-10-04 through the React dashboard and API, by the human operator "Test Human".

**Steps:**
1. Reset the DB with **Reset shop** (audit seq 1171). The working DB was byte-identical to the original, and the starting checking balance was **$3,400.00**.
2. Ran 101, 102, and 103 in order with the real agent team. All three were fresh model runs, not cache replays.
3. Approved payments and signed off decisions in the dashboard.

Every ticket's run had zero validator rejections, blocked delegations, or tool errors.

| Ticket | Run | Tokens / model calls / tool calls | Delegation path | Human approvals | Cash |
|---|---|---|---|---|---|
| 101 | `946022311ab6` | 48,899 / 13 / 18 | Boss → Inventory → Accounting; Boss → Customer Service (matches Expected exactly) | 1 sign-off: draft to Tauhid approved for the owner to send | no change |
| 102 | `bc4dbef543fe` | 27,769 / 8 / 9 | Boss → Facilities; Boss → Accounting | 2 payment approvals: invoice 501 ($840, payment #1), then rent for lease 1 ($2,400, payment #2) | $3,400 → $2,560 → $160 |
| 103 | `5002818301a0` | 42,711 / 12 / 14 | Boss → Inventory; Boss → Accounting; Boss → Customer Service | 2 sign-offs: **no discount**, $58 list price kept; draft to Yale AI Club approved | no change |

**Ending balance: $160.00** ($3,400 − $840 − $2,400). This exactly matches `cash_accounts` in `campus_customs_new.db`.

**Database after the run:**
- `payments` has 2 rows, both approved by "Test Human";
- invoice 501 is `paid`;
- lease 1 `next_due` is 2026-10-02.

The raw `tickets.status` column still says `open`, because no tool writes it; the resolved status comes from the backend.

**Deliverables:**
- `output/desk_tickets.html`: Actual sections and the Cash tab;
- `output/resolved_tickets.json`;
- `output/resolved_board.html` with `output/resolved_board_images/ticket_10{1,2,3}.jpg`.


---

## Open Tickets Summary (starting state)

Desk date: **2026-08-31**. Cash available: **$3,400** (checking). All three were resolved in the final run (see above).

**Ticket 101 — Customer order (Tauhid Zaman, "Bulldog tee")**
Wants 1 × `CC-TEE-WHITE` size S. Inventory shows **0** in size S. The ticket links to invoice 501: an open $840 rush reprint of that exact tee/size from Bulldog Print Co (5 lead days), which was due 2026-08-28 and is **3 days overdue**. List price is $28.
*Relevant tables:* `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `cash_accounts`, `payments`, `desk`.

**Ticket 102 — Rent notice (Elm City Properties, "Rent due")**
Email says shop rent is due in 2 days. Links to lease 1: Chapel Street shop, $2,400, next due 2026-09-02 — which matches 2 days from the desk date and the landlord name. Paying rent leaves $1,000; paying rent *and* invoice 501 ($3,240 total) would leave only $160.
*Relevant tables:* `tickets`, `leases`, `cash_accounts`, `payments`, `invoices` (competing obligation), `desk`.

**Ticket 103 — Price override (Yale AI Club, "Bulk hoodie discount")**
Wants 20 × `CC-HOOD-NAVY` size M with a bulk discount. Inventory has only **8** in size M (32 across all sizes). Pricing: $22 cost vs. $58 list, so any discount must stay above the $22 floor (20 units: $1,160 at list, $440 at cost). Fulfilling the remaining 12 would likely need a reprint from Bulldog Print Co (5 lead days).
*Relevant tables:* `tickets`, `inventory`, `pricing`, `vendors`, `desk`.
