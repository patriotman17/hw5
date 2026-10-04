"""Campus Customs FastAPI backend (Problem 7).

Run from the backend/ folder:
    uvicorn main:app --reload --port 8000

All shop facts and every payment go through the campus-customs MCP server
(mcp_client.ShopMCP); ticket runs use the Problem 5 agent team (agents.py);
payments use the human-approval flow in approve_payment.py, which is the only
caller of the record_payment MCP tool. This file contains no SQL.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware

import audit
import events
from agents import ALL_TICKETS, run_ticket_detailed
from approve_payment import ApprovalRefused, check_human_approver, execute_payment, prepare_payment
from config import MODEL_NAME
from db_reset import reset_db
from mcp_client import MCPToolError, ShopMCP
from models import HumanSignoff, PaymentApprovalCreate, PaymentApprovalRequest, PaymentApprove, PaymentDecline

APPROVAL_TTL = timedelta(minutes=15)
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp = ShopMCP()
    await app.state.mcp.start()
    app.state.running: set[int] = set()
    app.state.run_lock = asyncio.Lock()
    app.state.approvals: dict[str, PaymentApprovalRequest] = {}
    app.state.approval_lock = asyncio.Lock()
    try:
        yield
    finally:
        await app.state.mcp.stop()


app = FastAPI(title="Campus Customs Desk API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if o.strip()],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _mcp(request: Request, tool: str, args: dict | None = None) -> dict:
    try:
        return await request.app.state.mcp.call(tool, args)
    except MCPToolError as exc:
        status = 404 if "does not exist" in exc.message else 400
        raise HTTPException(status, detail=exc.message)


async def _ticket_view(request: Request, ticket_id: int) -> dict:
    data = await _mcp(request, "get_ticket", {"ticket_id": ticket_id})
    ticket = data["ticket"]
    st = events.ticket_statuses([ticket_id])[ticket_id]
    return {
        **ticket,
        "db_status": ticket["status"],
        "status": st["status"],
        "status_reason": st["reason"],
        "pending_payments": st["payments"],
        "outstanding_actions": st["outstanding_actions"],
        "signed_off_actions": st["signed_off_actions"],
        "waiting_actions": st["waiting_actions"],
        "running": ticket_id in request.app.state.running,
        "desk_date": data["desk_date"],
        "latest_run": st["latest_run"],
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health(request: Request):
    desk = await _mcp(request, "get_desk_date")
    return {"ok": True, "model": MODEL_NAME, "desk_date": desk["date_today"]}


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@app.get("/api/tickets")
async def list_tickets(request: Request):
    """Tickets 101, 102, 103 with open / pending / resolved status."""
    return {"tickets": [await _ticket_view(request, t) for t in ALL_TICKETS]}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(request: Request, ticket_id: int = Path(gt=0)):
    return await _ticket_view(request, ticket_id)


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket_route(request: Request, ticket_id: int = Path(gt=0)):
    """Run the agent team on one ticket and wait for the Boss's decision (~30-90 s)."""
    await _mcp(request, "get_ticket", {"ticket_id": ticket_id})  # 404 for unknown tickets
    state = request.app.state
    async with state.run_lock:
        if ticket_id in state.running:
            raise HTTPException(409, detail=f"Ticket {ticket_id} is already being worked.")
        state.running.add(ticket_id)
    try:
        outcome = await run_ticket_detailed(ticket_id)
    except Exception as exc:
        raise HTTPException(502, detail=f"Agent run failed: {type(exc).__name__}: {exc}")
    finally:
        state.running.discard(ticket_id)
    st = events.ticket_statuses([ticket_id])[ticket_id]
    return {**outcome.model_dump(), "status": st["status"], "status_reason": st["reason"]}


@app.post("/api/tickets/{ticket_id}/signoffs", status_code=201)
async def sign_off_action(request: Request, body: HumanSignoff, ticket_id: int = Path(gt=0)):
    """A named human signs off one outstanding non-payment action. Nothing is sent, paid, or written to the DB."""
    await _mcp(request, "get_ticket", {"ticket_id": ticket_id})  # 404 for unknown tickets
    if body.confirm != "SIGN OFF":
        raise HTTPException(422, detail='confirm must be exactly "SIGN OFF".')
    try:
        human = check_human_approver(body.signed_off_by)
    except ApprovalRefused:
        raise HTTPException(403, detail="signed_off_by must name a human, not an agent.")
    if ticket_id in request.app.state.running:
        raise HTTPException(409, detail=f"Ticket {ticket_id} is being worked; wait for the run to finish.")
    st = events.ticket_statuses([ticket_id])[ticket_id]
    if not st["latest_run"] or st["latest_run"]["run_id"] != body.run_id:
        raise HTTPException(409, detail="That run is not the ticket's current run.")
    if body.action not in st["outstanding_actions"]:
        raise HTTPException(409, detail="That action is not outstanding (already signed off or not in the decision).")
    audit.record(
        "human_signoff", run_id=body.run_id, ticket_id=ticket_id, agent=None,
        action=body.action, signed_off_by=human, note=body.note.strip(),
    )
    return await _ticket_view(request, ticket_id)


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------


@app.get("/api/events")
async def recent_events(
    limit: int = Query(100, ge=1, le=500),
    ticket_id: int | None = Query(None),
    run_id: str | None = Query(None),
    since_seq: int | None = Query(None, ge=0),
    include_results: bool = Query(False),
):
    """Recent audit events plus what each agent said and which MCP tools it used."""
    return events.recent_events(
        limit=limit, ticket_id=ticket_id, run_id=run_id, since_seq=since_seq, include_results=include_results
    )


# ---------------------------------------------------------------------------
# Cash
# ---------------------------------------------------------------------------


@app.get("/api/cash")
async def cash(request: Request):
    """Current checking balance (from the MCP get_cash_position tool)."""
    data = await _mcp(request, "get_cash_position")
    checking = next((a for a in data["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, detail="No checking account in cash_accounts.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "desk_date": data["desk_date"],
        "open_invoice_total": data["open_invoice_total"],
        "upcoming_rent": data["upcoming_rent"],
    }


# ---------------------------------------------------------------------------
# Payments: human approval requests -> MCP record_payment
# ---------------------------------------------------------------------------


def _expire(approvals: dict[str, PaymentApprovalRequest]) -> None:
    now = _now().isoformat()
    for req in approvals.values():
        if req.status == "pending" and req.expires_at < now:
            req.status = "expired"


@app.post("/api/payments/requests", status_code=201)
async def create_payment_request(request: Request, body: PaymentApprovalCreate):
    """Prepare a payment (MCP prepare_payment_plan) and open a human approval request. Pays nothing."""
    if body.run_id is not None:
        decision = events.run_decision(body.run_id)
        if decision is None:
            raise HTTPException(404, detail=f"No completed agent run {body.run_id}.")
        proposed = {(p["kind"], p["ref_id"]) for p in decision.get("payment_requests", [])}
        if (body.kind, body.ref_id) not in proposed:
            raise HTTPException(422, detail=f"Run {body.run_id} did not propose a {body.kind} payment for #{body.ref_id}.")

    try:
        item = await prepare_payment(request.app.state.mcp.call, body.kind, body.ref_id, body.account)
    except MCPToolError as exc:
        raise HTTPException(404 if "does not exist" in exc.message else 400, detail=exc.message)
    if not item.get("feasible"):
        status = 404 if "does not exist" in (item.get("reason") or "") else 409
        raise HTTPException(status, detail={"message": f"Not payable: {item.get('reason')}", "plan": item})

    now = _now()
    req = PaymentApprovalRequest(
        id=uuid.uuid4().hex[:10], kind=body.kind, ref_id=body.ref_id, account=body.account,
        payee=item["payee"], amount=item["amount"], description=item.get("description"),
        due_date=item.get("due_date"), cash_before=item["cash_before"], cash_after=item["cash_after"],
        ticket_id=body.ticket_id, run_id=body.run_id,
        requested_by=f"agent team (run {body.run_id})" if body.run_id else body.requested_by,
        created_at=now.isoformat(), expires_at=(now + APPROVAL_TTL).isoformat(),
    )
    async with request.app.state.approval_lock:
        request.app.state.approvals[req.id] = req
    audit.record(
        "payment_approval_requested", run_id="human_approval", ticket_id=body.ticket_id or 0,
        request_id=req.id, kind=req.kind, ref_id=req.ref_id, amount=req.amount, payee=req.payee,
        requested_by=req.requested_by, source_run_id=body.run_id,
    )
    return req


@app.get("/api/payments/requests")
async def list_payment_requests(request: Request):
    async with request.app.state.approval_lock:
        _expire(request.app.state.approvals)
        reqs = sorted(request.app.state.approvals.values(), key=lambda r: r.created_at, reverse=True)
    return {"requests": reqs}


async def _pending(request: Request, request_id: str) -> PaymentApprovalRequest:
    approvals = request.app.state.approvals
    _expire(approvals)
    req = approvals.get(request_id)
    if req is None:
        raise HTTPException(404, detail=f"No approval request {request_id}.")
    if req.status == "expired":
        raise HTTPException(410, detail="Approval request expired; prepare it again.")
    if req.status != "pending":
        raise HTTPException(409, detail=f"Approval request is already {req.status}.")
    return req


@app.post("/api/payments/requests/{request_id}/approve")
async def approve_payment(request: Request, request_id: str, body: PaymentApprove):
    """A human approves a prepared payment; MCP record_payment executes it (or refuses)."""
    if body.confirm != "APPROVE":
        raise HTTPException(422, detail='confirm must be exactly "APPROVE".')
    try:
        approver = check_human_approver(body.approved_by)
    except ApprovalRefused as exc:
        raise HTTPException(403, detail=str(exc))

    async with request.app.state.approval_lock:
        req = await _pending(request, request_id)
        try:
            result = await execute_payment(
                request.app.state.mcp.call, req.kind, req.ref_id, approver, req.account,
                context={"via": "api", "request_id": req.id},
            )
        except ApprovalRefused as exc:
            req.status, req.refusal_reason = "refused", str(exc)
            req.decided_by, req.decided_at = approver, _now().isoformat()
            raise HTTPException(409, detail={"message": str(exc), "request": req.model_dump()})
        req.status, req.result = "approved", result
        req.decided_by, req.decided_at = approver, _now().isoformat()
    return {"request": req, "payment": result["payment"], "cash": result["cash_accounts"]}


@app.post("/api/payments/requests/{request_id}/decline")
async def decline_payment(request: Request, request_id: str, body: PaymentDecline):
    async with request.app.state.approval_lock:
        req = await _pending(request, request_id)
        req.status, req.decided_by, req.decided_at = "declined", body.declined_by, _now().isoformat()
    audit.record(
        "payment_declined_by_human", run_id="human_approval", ticket_id=req.ticket_id or 0,
        request_id=req.id, kind=req.kind, ref_id=req.ref_id, approved_by=body.declined_by, via="api",
    )
    return {"request": req}


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


@app.post("/api/reset")
async def reset(request: Request):
    """Restore data/campus_customs_new.db to the original values and re-open all tickets."""
    state = request.app.state
    async with state.run_lock, state.approval_lock:  # no reset mid-run or mid-payment
        if state.running:
            raise HTTPException(409, detail=f"Cannot reset while tickets {sorted(state.running)} are running.")
        sha1 = reset_db(reason="api reset")
        for req in state.approvals.values():
            if req.status == "pending":
                req.status = "cancelled_by_reset"
    cash_now = await cash(request)
    statuses = events.ticket_statuses(ALL_TICKETS)
    return {"ok": True, "sha1": sha1, "checking_balance": cash_now["balance"],
            "tickets": {t: s["status"] for t, s in statuses.items()}}
