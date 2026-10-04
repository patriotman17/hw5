"""Human-approval path for payments. The ONLY caller of the record_payment MCP tool.

Two steps, shared by the CLI below and the FastAPI routes in main.py:
  prepare_payment()  -> MCP prepare_payment_plan (read-only): payee, amount, cash before/after
  execute_payment()  -> MCP record_payment: updates payments, cash_accounts, and invoices/leases

There is no database code here. The MCP tool re-reads the amount from the DB and
refuses if cash would go negative or the approver is empty or an agent name.

CLI:  .venv/bin/python backend/approve_payment.py invoice 501 --approved-by "Your Name"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Awaitable, Callable

import audit
from mcp_client import MCPToolError, call_tool, new_client

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service", "agent", "ai", "system"}

CallTool = Callable[[str, dict[str, Any]], Awaitable[dict]]


class ApprovalRefused(Exception):
    """The payment was not executed (refused by the MCP tool or invalid approver)."""


def check_human_approver(approved_by: str) -> str:
    approver = approved_by.strip()
    if not approver or approver.lower() in AGENT_NAMES:
        raise ApprovalRefused("approved_by must name the human who approved this payment, not an agent.")
    return approver


async def prepare_payment(call: CallTool, kind: str, ref_id: int, account: str = "checking") -> dict:
    """Ask MCP prepare_payment_plan about one payment. Returns the plan line (feasible or not)."""
    plan = await call("prepare_payment_plan", {"items": [{"kind": kind, "ref_id": ref_id}], "account": account})
    return plan["items"][0]


async def execute_payment(
    call: CallTool, kind: str, ref_id: int, approved_by: str, account: str = "checking", *, context: dict | None = None
) -> dict:
    """Run MCP record_payment for a human-approved payment and audit the outcome."""
    approver = check_human_approver(approved_by)
    try:
        result = await call(
            "record_payment", {"kind": kind, "ref_id": ref_id, "approved_by": approver, "account": account}
        )
    except MCPToolError as exc:
        audit.record(
            "payment_refused", run_id="human_approval", ticket_id=0,
            kind=kind, ref_id=ref_id, approved_by=approver, error=exc.message, **(context or {}),
        )
        raise ApprovalRefused(exc.message) from exc
    audit.record(
        "payment_recorded", run_id="human_approval", ticket_id=0,
        kind=kind, ref_id=ref_id, approved_by=approver, result=result, **(context or {}),
    )
    return result


async def _cli(kind: str, ref_id: int, approved_by: str, account: str) -> None:
    check_human_approver(approved_by)
    async with new_client() as client:
        call = lambda name, args: call_tool(client, name, args)  # noqa: E731
        item = await prepare_payment(call, kind, ref_id, account)
        print(json.dumps(item, indent=2))
        if not item.get("feasible"):
            print(f"Not payable: {item.get('reason')}")
            return

        if not sys.stdin.isatty():
            raise SystemExit("Refused: payment approval requires a human at an interactive terminal.")
        try:
            answer = input(
                f"\nPay ${item['amount']:,.2f} to {item['payee']} from {account} "
                f"(cash ${item['cash_before']:,.2f} -> ${item['cash_after']:,.2f})? Type APPROVE to confirm: "
            )
        except EOFError:
            answer = ""
        if answer.strip() != "APPROVE":
            audit.record(
                "payment_declined_by_human", run_id="human_approval", ticket_id=0,
                kind=kind, ref_id=ref_id, approved_by=approved_by,
            )
            print("Not approved. Nothing was paid.")
            return

        try:
            result = await execute_payment(call, kind, ref_id, approved_by, account, context={"via": "cli"})
        except ApprovalRefused as exc:
            raise SystemExit(f"Refused: {exc}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Approve and record one payment (human only).")
    parser.add_argument("kind", choices=["rent", "invoice"])
    parser.add_argument("ref_id", type=int, help="lease id for rent, invoice id for invoices")
    parser.add_argument("--approved-by", required=True, help="the human approving this payment")
    parser.add_argument("--account", default="checking")
    args = parser.parse_args()
    try:
        asyncio.run(_cli(args.kind, args.ref_id, args.approved_by, args.account))
    except ApprovalRefused as exc:
        raise SystemExit(f"Refused: {exc}")
