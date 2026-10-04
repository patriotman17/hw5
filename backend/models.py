"""Shared Pydantic models and types for the Campus Customs agent team (Problem 5).

Safety rules are encoded in the types where possible:
- DraftMessage.status / sent are Literals, so a message can only ever be a draft.
- PaymentRequest.approval_status / requires_human_approval are Literals, so an
  agent can only ever *request* a payment; nothing in the team can execute one.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")


# ---------------------------------------------------------------------------
# Building blocks used in every agent's output
# ---------------------------------------------------------------------------


class Fact(BaseModel):
    """One shop fact the agent relied on, with where it came from."""

    statement: str = Field(description="The fact, with exact numbers/dates as returned.")
    source: str = Field(
        description="The MCP tool name that returned it (e.g. 'get_inventory'), "
        "or 'delegation:<agent>' if another agent reported it."
    )


class DraftMessage(BaseModel):
    """A customer/vendor/landlord communication. Drafts only; never sent by an agent."""

    audience: Literal["customer", "vendor", "landlord", "internal"]
    recipient: str
    subject: str
    body: str
    status: Literal["draft"] = "draft"
    sent: Literal[False] = False


class PaymentRequest(BaseModel):
    """A payment the team proposes. Always pending human approval."""

    kind: Literal["rent", "invoice"]
    ref_id: int = Field(description="Lease id for rent, invoice id for invoices.")
    payee: str
    amount: float
    account: str = "checking"
    reason: str
    approval_status: Literal["pending_human_approval"] = "pending_human_approval"
    requires_human_approval: Literal[True] = True


class ProposedAction(BaseModel):
    """A next step for the shop. Nothing here is executed by the agents."""

    description: str
    kind: Literal[
        "fulfill_from_stock",
        "vendor_restock",
        "payment",
        "pricing_decision",
        "customer_communication",
        "vendor_communication",
        "other",
    ]
    owner: AgentName | Literal["human"]
    vendor_id: int | None = Field(default=None, description="Required for vendor_restock actions.")
    blocked_by: str | None = Field(
        default=None, description="What must happen first (e.g. an unpaid invoice), if anything."
    )
    requires_human_approval: bool
    satisfied_by_payment_approval: bool = Field(
        default=False,
        description="True only for a check the human does as part of approving one of this decision's "
        "payment_requests (e.g. confirming the notice amount matches the lease before approving rent). "
        "Never true for drafts to send, pricing decisions, restocks, or anything that happens after approval.",
    )
    conditional_on: str | None = Field(
        default=None,
        description="Set ONLY for a step that cannot happen yet because it waits on something outside the shop's "
        "control, e.g. 'Tauhid's reply choosing size S' or 'vendor confirming supply'. Such steps are tracked as "
        "waiting, not as decisions a human must make now. Never set it for a pricing decision.",
    )


# Kinds that are always real follow-up work for a human, never part of approving a payment.
HUMAN_WORK_KINDS = {
    "customer_communication", "vendor_communication", "pricing_decision", "vendor_restock", "fulfill_from_stock",
}


COMM_KIND_FOR_AUDIENCE = {"customer": "customer_communication", "vendor": "vendor_communication"}


def classify_human_actions(decision: dict) -> tuple[list[str], list[dict]]:
    """Split a decision's human work into (needed now, waiting on someone else).

    - Needed now: decisions a human must make before the ticket can close (sign-offs).
    - Waiting: steps marked `conditional_on` an outside event (customer reply, vendor confirmation).
      Pricing decisions can never be deferred this way.
    - Each draft needs exactly one sign-off: the Boss's own action to send it if there is one,
      otherwise an automatic "Send or discard draft" item (no double counting).
    Shared by the Boss's output validator and the API's ticket status, so both apply the same rule.
    """
    has_payments = bool(decision.get("payment_requests"))
    needed: list[str] = []
    waiting: list[dict] = []
    open_now: list[dict] = []
    for a in decision.get("proposed_actions", []):
        if not (a.get("requires_human_approval") or a.get("blocked_by")):
            continue
        kind = a.get("kind")
        if kind == "payment" and has_payments:
            continue  # the payment itself is tracked through payment_requests
        if a.get("satisfied_by_payment_approval") and has_payments and kind not in HUMAN_WORK_KINDS:
            continue  # a check the approver performs while approving
        if (a.get("conditional_on") or "").strip() and kind != "pricing_decision":
            waiting.append({"action": a.get("description", kind), "waiting_on": a["conditional_on"].strip()})
            continue
        open_now.append(a)
        needed.append(a.get("description", kind))

    def covered(d: dict) -> bool:
        recipient = (d.get("recipient") or "").lower()
        for a in open_now:
            desc = (a.get("description") or "").lower()
            if a.get("kind") == COMM_KIND_FOR_AUDIENCE.get(d.get("audience")) or ("draft" in desc and recipient and recipient in desc):
                return True
        return False

    drafts = [f"Send or discard draft to {d.get('recipient')}: {d.get('subject')}" for d in decision.get("drafts", []) if not covered(d)]
    return drafts + needed, waiting


def outstanding_human_actions(decision: dict) -> list[str]:
    """Human decisions still needed now (see classify_human_actions). Empty -> nothing else needed."""
    return classify_human_actions(decision)[0]


class RuleCheck(BaseModel):
    rule: str
    status: Literal["pass", "blocked", "not_applicable"]
    note: str


# ---------------------------------------------------------------------------
# Agent outputs
# ---------------------------------------------------------------------------


class SpecialistReport(BaseModel):
    """Output of Inventory, Accounting, Facilities, and Customer Service."""

    agent: AgentName
    ticket_id: int
    summary: str
    facts: list[Fact] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(
        default_factory=list, description="Business data that was needed but is not in the database."
    )
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    drafts: list[DraftMessage] = Field(default_factory=list)
    payment_requests: list[PaymentRequest] = Field(default_factory=list)


class TicketDecision(BaseModel):
    """The Boss's final recommendation for a ticket. A recommendation, not an execution."""

    ticket_id: int
    desk_date: str
    recommendation: str
    rationale: str
    agents_consulted: list[AgentName] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    drafts: list[DraftMessage] = Field(default_factory=list)
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    rule_checks: list[RuleCheck] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    other_human_action_required: bool = Field(
        default=False,
        description="Set by the system from proposed_actions and drafts (see outstanding_human_actions).",
    )
    awaiting_payment_approval: bool = Field(
        default=False, description="Set by the system: true when payment_requests is non-empty."
    )
    status: Literal["recommendation_pending_human_review"] = "recommendation_pending_human_review"


class TicketRunOutcome(BaseModel):
    """A completed ticket run: the Boss's decision plus run metadata."""

    run_id: str
    ticket_id: int
    decision: TicketDecision
    usage: dict[str, int]
    agents_run: list[AgentName]
    delegations_used: int


class DelegationResult(BaseModel):
    """What the delegate tool hands back to the calling agent."""

    from_agent: AgentName
    to_agent: AgentName
    task: str
    depth: int
    ok: bool
    cached: bool = False
    report: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Run-time dependencies (not sent to the model)
# ---------------------------------------------------------------------------


@dataclass
class TicketRunState:
    """Shared by every agent working one ticket run."""

    run_id: str
    ticket_id: int
    delegations_used: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    delegation_cache: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    agents_run: list[AgentName] = field(default_factory=list)
    # Captured from MCP results so output validators can check rules deterministically.
    desk_date: str | None = None
    vendor_status: dict[int, dict[str, Any]] = field(default_factory=dict)
    payment_plans: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentDeps:
    """Per-agent-run dependencies. A fresh one is built for each delegation."""

    agent: AgentName
    state: TicketRunState
    depth: int = 0
    chain: tuple[AgentName, ...] = ()
    tools_called: set[str] = field(default_factory=set)
    delegated_to: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# API types (FastAPI routes in main.py)
# ---------------------------------------------------------------------------


class PaymentApprovalCreate(BaseModel):
    """Ask a human to approve one payment. The amount is never sent; MCP reads it from the DB."""

    kind: Literal["rent", "invoice"]
    ref_id: int = Field(description="Lease id for rent, invoice id for invoices.")
    account: str = "checking"
    ticket_id: int | None = None
    run_id: str | None = Field(
        default=None, description="If set, the payment must be one the agent team proposed in this run."
    )
    requested_by: str = "dashboard"


class PaymentApprove(BaseModel):
    approved_by: str = Field(description="Name of the human approving. Agent names are refused.")
    confirm: str = Field(description='Must be exactly "APPROVE".')


class PaymentDecline(BaseModel):
    declined_by: str


class PaymentApprovalRequest(BaseModel):
    """A pending/decided human approval request held by the API."""

    id: str
    kind: Literal["rent", "invoice"]
    ref_id: int
    account: str
    payee: str
    amount: float
    description: str | None = None
    due_date: str | None = None
    cash_before: float
    cash_after: float
    ticket_id: int | None = None
    run_id: str | None = None
    requested_by: str
    created_at: str
    expires_at: str
    status: Literal["pending", "approved", "refused", "declined", "expired", "cancelled_by_reset"] = "pending"
    decided_by: str | None = None
    decided_at: str | None = None
    result: dict[str, Any] | None = None
    refusal_reason: str | None = None


class HumanSignoff(BaseModel):
    """A named human confirms they handled one outstanding non-payment action (nothing is sent or paid)."""

    run_id: str = Field(description="The ticket's current run (latest_run.run_id).")
    action: str = Field(description="Exactly one entry from the ticket's outstanding_actions.")
    signed_off_by: str = Field(description="Name of the human. Agent names are refused.")
    confirm: str = Field(description='Must be exactly "SIGN OFF".')
    note: str = Field(default="", description="What the human decided or did, e.g. 'Approved draft for owner to send'.")
