# Campus Customs MCP Server

## What it's for

This MCP server is the **only** way the Campus Customs agents (Boss, Inventory, Accounting, Facilities, Customer Service) get shop facts. They do not write raw SQL. Each tool runs a fixed set of queries and returns only real database facts: stock levels, prices, lease terms, cash, invoices, vendors, and payments.

## Database

- Connects **only** to `data/campus_customs_new.db` (the working copy). The original `data/campus_customs.db` is never opened by the server. It is only the source for `backend/db_reset.py`, which restores the working copy before a full run.
- Every tool opens the database read-only (`mode=ro`), **except `record_payment`**, the single write tool.
- "Today" for all date math comes from `desk.date_today` (`2026-08-31`), not the system clock. Vendor lead times come only from `vendors.lead_days`.
- No tool adds cash; cash only goes out.

## Tools

### Ticket tools (Problem 4)

| Tool | Reads | Returns |
|---|---|---|
| `check_order_fulfillment(ticket_id=101)` | tickets, inventory, pricing, invoices, vendors, desk | On-hand quantity for the requested SKU/size, whether stock can fill it, other sizes, list price, and the linked vendor invoice (amount, due date, days overdue, lead time) |
| `verify_rent_notice(ticket_id=102)` | tickets, leases, cash_accounts, invoices, desk | The lease, whether the requester matches the landlord, days until due, cash, cash after rent, cash after rent plus open invoices |
| `evaluate_bulk_discount(ticket_id=103, discount_pct=None)` | tickets, inventory, pricing, vendors | Shortfall, stock across sizes, cost vs. list, totals, maximum discount before a loss, vendors, and optional discount math (unit price, total, margin) |

### Team building blocks (Problem 5)

| Tool | Reads | Returns |
|---|---|---|
| `get_desk_date()` | desk | The operating date |
| `get_ticket(ticket_id)` | tickets, desk | One ticket (any type) |
| `list_open_tickets()` | tickets, desk | All open tickets |
| `get_inventory(sku, size=None)` | inventory | Rows for one size or all sizes, plus total quantity |
| `get_pricing(sku)` | pricing | Unit cost, list price, unit margin, maximum discount before a loss |
| `check_vendor_status(vendor_id=None)` | vendors, invoices, desk | Per vendor: unpaid invoices (days overdue), `can_ship_new_product` (false while any invoice is open), blocked reason, earliest arrival = desk date + `lead_days` |
| `get_restock_options(sku, size, qty_needed)` | inventory, vendors, invoices, desk | On hand, shortfall, every vendor's status and lead time, past invoices mentioning the SKU, and `data_gaps` (no SKU-to-vendor map, no reprint cost or minimum order quantity) |
| `get_invoices(status=None, vendor_id=None, invoice_id=None)` | invoices, vendors, desk | Invoices with vendor name and days overdue, open total |
| `get_cash_position()` | cash_accounts, invoices, leases, desk | Balances, open invoices, upcoming rent, cash after invoices, after rent, and after both |
| `get_lease(lease_id)` | leases, desk | Lease record and days until rent is due |
| `get_payments(kind=None, ref_id=None)` | payments | Payments already recorded |
| `prepare_payment_plan(items, account="checking")` | leases, invoices, vendors, cash_accounts, payments, desk | **Read-only.** Applies `[{kind: "rent"\|"invoice", ref_id}]` in order to a running balance. Amounts come from the DB. Each item is feasible or not (overdraft, already paid, not open, missing), and every item is `pending_human_approval`. `executed: false` |

### Human-only write tool

| Tool | Reads / writes | Behavior |
|---|---|---|
| `record_payment(kind, ref_id, approved_by, account="checking")` | reads desk; **writes** payments, cash_accounts, invoices / leases | Executes one human-approved payment in a single transaction: inserts into `payments` (`paid_at` = desk date, `approved_by`), lowers the cash balance, and sets the invoice `status='paid'` or advances the lease `next_due` by one month. **Refuses** if `approved_by` is empty or an agent name, the invoice isn't open, the record is missing, or cash would go negative. It is excluded from every agent's toolset and blocked in the agent MCP hook. It is called only by `backend/approve_payment.py` after a human types `APPROVE`. |

Every tool raises an error rather than guessing when a referenced record is missing.

## Which agent can call what

| Agent | Tools |
|---|---|
| boss | `get_desk_date`, `get_ticket`, `list_open_tickets` |
| inventory | + `get_inventory`, `get_restock_options`, `check_vendor_status`, `check_order_fulfillment`, `evaluate_bulk_discount` |
| accounting | + `get_cash_position`, `get_invoices`, `get_pricing`, `get_payments`, `check_vendor_status`, `prepare_payment_plan`, `evaluate_bulk_discount` |
| facilities | + `get_lease`, `verify_rent_notice`, `get_cash_position` |
| customer_service | + `get_inventory`, `get_pricing` |

("+" means in addition to `get_desk_date` and `get_ticket`.) This is enforced in `backend/agents.py` (`TOOL_ACCESS`), both by filtering each agent's toolset and in the MCP call hook.

## Setup

From the `HW 5` folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run (stdio transport). The Claude Code session connects through `.mcp.json`, and the agent team (`backend/agents.py`) launches it as a subprocess:

```bash
.venv/bin/python mcp_server/server.py
```
