"""Campus Customs MCP server.

Read-only tools backed by data/campus_customs_new.db. The original
data/campus_customs.db is never touched.

- Problem 4 ticket tools: check_order_fulfillment (101), verify_rent_notice (102),
  evaluate_bulk_discount (103).
- Problem 5 building blocks for the multi-agent team: desk/ticket lookups,
  inventory, pricing, vendors, invoices, cash, leases, payments, restock options,
  and a payment-plan check (prepare_payment_plan, read-only).
- record_payment is the ONLY write tool. It executes one human-approved payment
  and updates payments, cash_accounts, and invoices/leases. It is excluded from
  every agent's toolset and is called only by backend/approve_payment.py.
- There is no tool that adds cash: in this homework cash only goes out.
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")


def _connect() -> sqlite3.Connection:
    """Open the working copy read-only. Only record_payment opens a writable connection."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _desk_date(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _ticket(conn: sqlite3.Connection, ticket_id: int, expected_type: str) -> dict:
    ticket = _row(conn, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} does not exist.")
    if ticket["type"] != expected_type:
        raise ValueError(
            f"Ticket {ticket_id} is type '{ticket['type']}', not '{expected_type}'."
        )
    return ticket


@mcp.tool
def check_order_fulfillment(ticket_id: int = 101) -> dict:
    """Ticket 101: check whether a customer order can be filled from stock.

    Reads tickets, inventory, pricing, invoices, vendors, and desk. Returns
    on-hand stock for the requested SKU/size, the list price, and any linked
    vendor invoice (amount, due date, days overdue, vendor lead time).
    """
    with _connect() as conn:
        ticket = _ticket(conn, ticket_id, "customer_order")
        today = _desk_date(conn)

        stock = _row(
            conn,
            "SELECT name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (ticket["sku"], ticket["size"]),
        )
        price = _row(
            conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (ticket["sku"],)
        )
        other_sizes = _rows(
            conn,
            "SELECT size, qty FROM inventory WHERE sku = ? AND size != ?",
            (ticket["sku"], ticket["size"]),
        )

        invoice = None
        if ticket["invoice_id"] is not None:
            invoice = _row(
                conn,
                """SELECT i.id, i.amount, i.due_date, i.status, i.description,
                          v.id AS vendor_id, v.name AS vendor_name,
                          v.specialty AS vendor_specialty, v.lead_days AS vendor_lead_days
                   FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                   WHERE i.id = ?""",
                (ticket["invoice_id"],),
            )
            if invoice:
                invoice["days_overdue"] = max(0, _days_between(invoice["due_date"], today))

    on_hand = stock["qty"] if stock else 0
    return {
        "desk_date": today,
        "ticket": ticket,
        "requested": {"sku": ticket["sku"], "size": ticket["size"], "qty": ticket["qty"]},
        "inventory": stock,
        "on_hand": on_hand,
        "can_fill_from_stock": on_hand >= ticket["qty"],
        "other_sizes_in_stock": other_sizes,
        "pricing": price,
        "linked_invoice": invoice,
    }


@mcp.tool
def verify_rent_notice(ticket_id: int = 102) -> dict:
    """Ticket 102: verify a rent notice against the lease and check cash.

    Reads tickets, leases, cash_accounts, invoices, and desk. Compares the
    ticket's requester to the lease landlord, reports rent amount and due date,
    and shows the cash balance before/after rent and other open invoices.
    """
    with _connect() as conn:
        ticket = _ticket(conn, ticket_id, "rent_notice")
        today = _desk_date(conn)

        lease = _row(conn, "SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],))
        if lease is None:
            raise ValueError(f"Ticket {ticket_id} references missing lease {ticket['lease_id']}.")

        accounts = _rows(conn, "SELECT name, balance, date FROM cash_accounts")
        open_invoices = _rows(
            conn,
            """SELECT i.id, i.amount, i.due_date, i.description, v.name AS vendor_name
               FROM invoices i JOIN vendors v ON v.id = i.vendor_id
               WHERE i.status = 'open'""",
        )

    total_cash = sum(a["balance"] for a in accounts)
    open_invoice_total = sum(i["amount"] for i in open_invoices)
    rent = lease["monthly_rent"]
    return {
        "desk_date": today,
        "ticket": ticket,
        "lease": lease,
        "requester_matches_landlord": ticket["requester"] == lease["landlord"],
        "days_until_due": _days_between(today, lease["next_due"]),
        "cash_accounts": accounts,
        "total_cash": total_cash,
        "cash_after_rent": total_cash - rent,
        "can_cover_rent": total_cash >= rent,
        "open_invoices": open_invoices,
        "cash_after_rent_and_open_invoices": total_cash - rent - open_invoice_total,
    }


@mcp.tool
def evaluate_bulk_discount(ticket_id: int = 103, discount_pct: float | None = None) -> dict:
    """Ticket 103: evaluate a bulk price-override request.

    Reads tickets, inventory, pricing, and vendors. Reports stock for the
    requested SKU/size and other sizes, the shortfall, unit cost vs. list price,
    the maximum discount before selling below cost, and, if discount_pct is
    given (e.g. 15 for 15%), the resulting unit price, total, and margin.
    """
    with _connect() as conn:
        ticket = _ticket(conn, ticket_id, "price_override")

        stock = _row(
            conn,
            "SELECT name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (ticket["sku"], ticket["size"]),
        )
        all_sizes = _rows(
            conn, "SELECT size, qty FROM inventory WHERE sku = ?", (ticket["sku"],)
        )
        price = _row(
            conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (ticket["sku"],)
        )
        vendors = _rows(conn, "SELECT id, name, specialty, lead_days FROM vendors")

    if price is None:
        raise ValueError(f"No pricing row for SKU {ticket['sku']}.")

    qty = ticket["qty"]
    on_hand = stock["qty"] if stock else 0
    cost, list_price = price["unit_cost"], price["list_price"]

    result = {
        "ticket": ticket,
        "requested": {"sku": ticket["sku"], "size": ticket["size"], "qty": qty},
        "inventory": stock,
        "on_hand": on_hand,
        "shortfall": max(0, qty - on_hand),
        "all_sizes": all_sizes,
        "pricing": price,
        "total_at_list": round(qty * list_price, 2),
        "total_at_cost": round(qty * cost, 2),
        "max_discount_pct_before_loss": round((1 - cost / list_price) * 100, 2),
        "vendors": vendors,
    }

    if discount_pct is not None:
        unit_price = round(list_price * (1 - discount_pct / 100), 2)
        result["proposed"] = {
            "discount_pct": discount_pct,
            "unit_price": unit_price,
            "total": round(unit_price * qty, 2),
            "margin_per_unit": round(unit_price - cost, 2),
            "total_margin": round((unit_price - cost) * qty, 2),
            "below_cost": unit_price < cost,
        }

    return result


# ---------------------------------------------------------------------------
# Problem 5: general-purpose tools for the multi-agent team
# ---------------------------------------------------------------------------


def _open_invoices_by_vendor(conn: sqlite3.Connection, today: str) -> dict[int, list[dict]]:
    """Open (unpaid) invoices grouped by vendor, with days overdue vs. desk date."""
    grouped: dict[int, list[dict]] = {}
    for inv in _rows(
        conn,
        "SELECT id, vendor_id, amount, due_date, status, description FROM invoices "
        "WHERE status = 'open' ORDER BY id",
    ):
        inv["days_overdue"] = max(0, _days_between(inv["due_date"], today))
        grouped.setdefault(inv["vendor_id"], []).append(inv)
    return grouped


def _vendor_status(vendor: dict, open_invoices: list[dict], today: str) -> dict:
    """Apply the shop rule: a vendor with any unpaid invoice cannot ship new product."""
    unpaid_total = round(sum(i["amount"] for i in open_invoices), 2)
    can_ship = not open_invoices
    eta = (date.fromisoformat(today) + timedelta(days=vendor["lead_days"])).isoformat()
    return {
        **vendor,
        "unpaid_invoices": open_invoices,
        "unpaid_total": unpaid_total,
        "can_ship_new_product": can_ship,
        "blocked_reason": None
        if can_ship
        else f"Vendor has {len(open_invoices)} unpaid invoice(s) totalling ${unpaid_total:,.2f}; "
        "no new product can ship until paid.",
        "earliest_arrival_if_ordered_today": eta if can_ship else None,
        "earliest_arrival_if_cleared_and_ordered_today": eta,
    }


@mcp.tool
def get_desk_date() -> dict:
    """Return the shop's operating date (desk.date_today).

    Reads desk. All due-date, overdue, and lead-time decisions must use this
    date, never the real-world clock.
    """
    with _connect() as conn:
        desk = _row(conn, "SELECT date_today, notes FROM desk")
    if desk is None:
        raise ValueError("desk table has no row; operating date is unknown.")
    return desk


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Return one ticket by id (any type), plus the desk date.

    Reads tickets and desk.
    """
    with _connect() as conn:
        ticket = _row(conn, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        today = _desk_date(conn)
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} does not exist.")
    return {"desk_date": today, "ticket": ticket}


@mcp.tool
def list_open_tickets() -> dict:
    """List all tickets with status 'open'.

    Reads tickets and desk.
    """
    with _connect() as conn:
        tickets = _rows(conn, "SELECT * FROM tickets WHERE status = 'open' ORDER BY id")
        today = _desk_date(conn)
    return {"desk_date": today, "open_tickets": tickets}


@mcp.tool
def get_inventory(sku: str, size: str | None = None) -> dict:
    """Return on-hand stock for a SKU (one size, or all sizes if size is omitted).

    Reads inventory. Raises an error if the SKU/size is not in inventory.
    """
    with _connect() as conn:
        if size is None:
            rows = _rows(
                conn,
                "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? ORDER BY size",
                (sku,),
            )
        else:
            rows = _rows(
                conn,
                "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
                (sku, size),
            )
    if not rows:
        raise ValueError(f"No inventory rows for SKU {sku!r}" + (f" size {size!r}." if size else "."))
    return {"sku": sku, "rows": rows, "total_qty": sum(r["qty"] for r in rows)}


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Return unit cost, list price, and unit margin for a SKU.

    Reads pricing. Raises an error if the SKU has no pricing row.
    """
    with _connect() as conn:
        price = _row(conn, "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
    if price is None:
        raise ValueError(f"No pricing row for SKU {sku!r}.")
    cost, list_price = price["unit_cost"], price["list_price"]
    return {
        **price,
        "unit_margin_at_list": round(list_price - cost, 2),
        "max_discount_pct_before_loss": round((1 - cost / list_price) * 100, 2),
    }


@mcp.tool
def check_vendor_status(vendor_id: int | None = None) -> dict:
    """Check whether a vendor (or every vendor) is allowed to ship new product.

    Reads vendors, invoices, and desk. Shop rule: a vendor with ANY unpaid
    (status 'open') invoice cannot ship new product until it is paid. Returns
    each vendor's unpaid invoices, days overdue, can_ship_new_product, and the
    earliest arrival date (desk date + lead_days).
    """
    with _connect() as conn:
        today = _desk_date(conn)
        if vendor_id is None:
            vendors = _rows(conn, "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id")
        else:
            vendors = _rows(
                conn, "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
            )
            if not vendors:
                raise ValueError(f"Vendor {vendor_id} does not exist.")
        open_by_vendor = _open_invoices_by_vendor(conn, today)
    return {
        "desk_date": today,
        "rule": "Vendors cannot ship new product while they have an unpaid invoice.",
        "vendors": [_vendor_status(v, open_by_vendor.get(v["id"], []), today) for v in vendors],
    }


@mcp.tool
def get_restock_options(sku: str, size: str, qty_needed: int) -> dict:
    """Show how a stock shortfall could be covered, without inventing supply data.

    Reads inventory, vendors, invoices, and desk. Returns on-hand qty, the
    shortfall, every vendor with specialty/lead time/can-ship status, and any
    past invoices whose description mentions this SKU. The database has NO
    SKU-to-vendor mapping, so matching a vendor to the product is a judgment
    the agent must label as such.
    """
    with _connect() as conn:
        today = _desk_date(conn)
        stock = _row(
            conn,
            "SELECT name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        )
        if stock is None:
            raise ValueError(f"No inventory row for SKU {sku!r} size {size!r}.")
        vendors = _rows(conn, "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id")
        open_by_vendor = _open_invoices_by_vendor(conn, today)
        sku_invoices = _rows(
            conn,
            """SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date,
                      i.status, i.description
               FROM invoices i JOIN vendors v ON v.id = i.vendor_id
               WHERE i.description LIKE ?""",
            (f"%{sku}%",),
        )
    return {
        "desk_date": today,
        "sku": sku,
        "size": size,
        "on_hand": stock["qty"],
        "qty_needed": qty_needed,
        "shortfall": max(0, qty_needed - stock["qty"]),
        "vendors": [_vendor_status(v, open_by_vendor.get(v["id"], []), today) for v in vendors],
        "invoices_mentioning_sku": sku_invoices,
        "data_gaps": [
            "No SKU-to-vendor mapping table exists; vendor fit is inferred from specialty or invoice history.",
            "No reprint unit cost or minimum order quantity is stored for any vendor.",
        ],
    }


@mcp.tool
def get_invoices(
    status: str | None = None, vendor_id: int | None = None, invoice_id: int | None = None
) -> dict:
    """Return invoices (optionally filtered) with vendor name and days overdue.

    Reads invoices, vendors, and desk. days_overdue is measured against
    desk.date_today.
    """
    clauses, params = [], []
    if status is not None:
        clauses.append("i.status = ?")
        params.append(status)
    if vendor_id is not None:
        clauses.append("i.vendor_id = ?")
        params.append(vendor_id)
    if invoice_id is not None:
        clauses.append("i.id = ?")
        params.append(invoice_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as conn:
        today = _desk_date(conn)
        invoices = _rows(
            conn,
            f"""SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date,
                       i.status, i.description
                FROM invoices i JOIN vendors v ON v.id = i.vendor_id {where} ORDER BY i.id""",
            tuple(params),
        )
    if invoice_id is not None and not invoices:
        raise ValueError(f"Invoice {invoice_id} does not exist.")
    for inv in invoices:
        inv["days_overdue"] = (
            max(0, _days_between(inv["due_date"], today)) if inv["status"] == "open" else 0
        )
    return {
        "desk_date": today,
        "invoices": invoices,
        "open_total": round(sum(i["amount"] for i in invoices if i["status"] == "open"), 2),
    }


@mcp.tool
def get_cash_position() -> dict:
    """Return cash balances plus known upcoming obligations (open invoices, rent).

    Reads cash_accounts, invoices, leases, and desk. Shows what cash would be
    left after each obligation; cash may never go negative.
    """
    with _connect() as conn:
        today = _desk_date(conn)
        accounts = _rows(conn, "SELECT name, balance, date FROM cash_accounts ORDER BY name")
        open_invoices = _rows(
            conn,
            """SELECT i.id, v.name AS vendor_name, i.amount, i.due_date, i.description
               FROM invoices i JOIN vendors v ON v.id = i.vendor_id
               WHERE i.status = 'open' ORDER BY i.due_date""",
        )
        leases = _rows(
            conn, "SELECT id, space_name, landlord, monthly_rent, next_due FROM leases ORDER BY next_due"
        )
    total_cash = round(sum(a["balance"] for a in accounts), 2)
    invoice_total = round(sum(i["amount"] for i in open_invoices), 2)
    rent_total = round(sum(l["monthly_rent"] for l in leases), 2)
    return {
        "desk_date": today,
        "accounts": accounts,
        "total_cash": total_cash,
        "open_invoices": open_invoices,
        "open_invoice_total": invoice_total,
        "upcoming_rent": [
            {**l, "days_until_due": _days_between(today, l["next_due"])} for l in leases
        ],
        "cash_after_open_invoices": round(total_cash - invoice_total, 2),
        "cash_after_rent": round(total_cash - rent_total, 2),
        "cash_after_all_obligations": round(total_cash - invoice_total - rent_total, 2),
    }


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """Return a lease (landlord, rent, next due date) and days until due.

    Reads leases and desk.
    """
    with _connect() as conn:
        today = _desk_date(conn)
        lease = _row(conn, "SELECT * FROM leases WHERE id = ?", (lease_id,))
    if lease is None:
        raise ValueError(f"Lease {lease_id} does not exist.")
    return {
        "desk_date": today,
        "lease": lease,
        "days_until_due": _days_between(today, lease["next_due"]),
    }


@mcp.tool
def get_payments(kind: str | None = None, ref_id: int | None = None) -> dict:
    """Return recorded payments (optionally filtered by kind and/or ref_id).

    Reads payments. Use this to avoid proposing a payment that was already made.
    """
    clauses, params = [], []
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if ref_id is not None:
        clauses.append("ref_id = ?")
        params.append(ref_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as conn:
        payments = _rows(conn, f"SELECT * FROM payments {where} ORDER BY id", tuple(params))
    return {"payments": payments, "count": len(payments)}


class PaymentItem(BaseModel):
    """One obligation to include in a payment plan. The amount is always read
    from the database (lease rent or invoice amount), never supplied by the agent."""

    kind: Literal["rent", "invoice"]
    ref_id: int


@mcp.tool
def prepare_payment_plan(items: list[PaymentItem], account: str = "checking") -> dict:
    """Check a set of proposed payments against cash. NEVER pays anything.

    Reads leases, invoices, vendors, cash_accounts, payments, and desk. Each item
    is kind 'rent' (ref_id = lease id) or 'invoice' (ref_id = invoice id); the
    amount comes from the database. Items are applied in the given order to a
    running balance. Any item that would make cash negative, is already paid,
    or references a missing record is marked not feasible. Every feasible item
    is returned as pending human approval; agents cannot execute payments.
    """
    with _connect() as conn:
        today = _desk_date(conn)
        acct = _row(conn, "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,))
        if acct is None:
            raise ValueError(f"Cash account {account!r} does not exist.")

        balance = acct["balance"]
        lines = []
        for item in items:
            line: dict = {"kind": item.kind, "ref_id": item.ref_id, "account": account}
            if item.kind == "rent":
                rec = _row(conn, "SELECT * FROM leases WHERE id = ?", (item.ref_id,))
                if rec is None:
                    line.update(feasible=False, reason=f"Lease {item.ref_id} does not exist.")
                    lines.append(line)
                    continue
                line.update(
                    payee=rec["landlord"],
                    amount=rec["monthly_rent"],
                    due_date=rec["next_due"],
                    description=f"Rent for {rec['space_name']}",
                )
            else:
                rec = _row(
                    conn,
                    """SELECT i.*, v.name AS vendor_name FROM invoices i
                       JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?""",
                    (item.ref_id,),
                )
                if rec is None:
                    line.update(feasible=False, reason=f"Invoice {item.ref_id} does not exist.")
                    lines.append(line)
                    continue
                line.update(
                    payee=rec["vendor_name"],
                    amount=rec["amount"],
                    due_date=rec["due_date"],
                    description=rec["description"],
                )
                if rec["status"] != "open":
                    line.update(feasible=False, reason=f"Invoice status is {rec['status']!r}, not open.")
                    lines.append(line)
                    continue

            already = _rows(
                conn, "SELECT * FROM payments WHERE kind = ? AND ref_id = ?", (item.kind, item.ref_id)
            )
            if item.kind == "invoice" and already:
                line.update(feasible=False, reason="A payment for this invoice is already recorded.")
                lines.append(line)
                continue

            after = round(balance - line["amount"], 2)
            line["days_until_due"] = _days_between(today, line["due_date"])
            line["prior_payments_same_ref"] = already
            line["cash_before"] = round(balance, 2)
            line["cash_after"] = after
            if after < 0:
                line.update(feasible=False, reason="Would make cash negative.")
            else:
                line.update(feasible=True, reason=None)
                balance = after
            line["approval_status"] = "pending_human_approval"
            line["requires_human_approval"] = True
            lines.append(line)

    feasible = [l for l in lines if l.get("feasible")]
    return {
        "desk_date": today,
        "account": account,
        "starting_balance": acct["balance"],
        "items": lines,
        "feasible_total": round(sum(l["amount"] for l in feasible), 2),
        "ending_balance_if_all_feasible_paid": round(balance, 2),
        "executed": False,
        "note": "Nothing was paid. Every payment needs explicit human approval outside the agent team.",
    }


AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service", "agent", "ai", "system"}


def _add_one_month(iso: str) -> str:
    d = date.fromisoformat(iso)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    # Clamp to the last day of the next month (e.g. Jan 31 -> Feb 28).
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Cannot advance {iso} by one month.")


@mcp.tool
def record_payment(
    kind: Literal["rent", "invoice"], ref_id: int, approved_by: str, account: str = "checking"
) -> dict:
    """Execute ONE human-approved payment and update the database. NOT for agents.

    Writes payments, cash_accounts, and invoices (invoice -> status 'paid') or
    leases (rent -> next_due advanced one month); reads desk. The amount comes
    from the database. Refuses if approved_by is empty or names an agent, if the
    invoice is not open, or if cash would go negative. paid_at = desk.date_today.
    The agent team never has access to this tool; it is called only by the
    human-approval path (backend/approve_payment.py).
    """
    approver = approved_by.strip()
    if not approver or approver.lower() in AGENT_NAMES:
        raise ValueError("Refused: approved_by must name the human who approved this payment.")

    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        today = _desk_date(conn)
        acct = _row(conn, "SELECT name, balance FROM cash_accounts WHERE name = ?", (account,))
        if acct is None:
            raise ValueError(f"Refused: cash account {account!r} does not exist.")

        if kind == "invoice":
            rec = _row(conn, "SELECT * FROM invoices WHERE id = ?", (ref_id,))
            if rec is None:
                raise ValueError(f"Refused: invoice {ref_id} does not exist.")
            if rec["status"] != "open":
                raise ValueError(f"Refused: invoice {ref_id} status is {rec['status']!r}, not open.")
            amount = rec["amount"]
        else:
            rec = _row(conn, "SELECT * FROM leases WHERE id = ?", (ref_id,))
            if rec is None:
                raise ValueError(f"Refused: lease {ref_id} does not exist.")
            amount = rec["monthly_rent"]

        new_balance = round(acct["balance"] - amount, 2)
        if new_balance < 0:
            raise ValueError(
                f"Refused: not enough cash. {account} has ${acct['balance']:,.2f}, "
                f"payment is ${amount:,.2f}; balance cannot go negative."
            )

        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today, approver),
        )
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
            updated = {"invoices": {"id": ref_id, "status": "paid"}}
        else:
            next_due = _add_one_month(rec["next_due"])
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
            updated = {"leases": {"id": ref_id, "next_due": {"from": rec["next_due"], "to": next_due}}}
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return {
        "executed": True,
        "payment": {
            "id": cur.lastrowid, "kind": kind, "ref_id": ref_id, "amount": amount,
            "account": account, "paid_at": today, "approved_by": approver,
        },
        "cash_accounts": {"name": account, "balance_before": acct["balance"], "balance_after": new_balance},
        **updated,
    }


if __name__ == "__main__":
    mcp.run()
