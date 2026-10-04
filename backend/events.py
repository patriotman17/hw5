"""Read-side views over output/audit_trail.json for the API.

This module only reads the audit trail (agent workflow history). It never
touches the shop database; shop facts come from MCP tools.

- Ticket status (open / pending / resolved), from the latest completed agent run
  since the last database reset plus the human payment decisions recorded after it:
    open      no run since the reset, or a payment the run proposed was declined or
              refused (the ticket needs to be re-worked)
    pending   the run left human work: other_human_action_required, or a proposed
              payment still waiting for approval
    resolved  every proposed payment was approved via MCP record_payment and every other
              required human action was signed off by a named human (POST /signoffs),
              or the Boss concluded no further action is needed
  A finished run alone never resolves a ticket.
- Recent events: compact versions of audit entries, plus a per-run breakdown of
  what each agent said and which MCP tools it used.
"""

from __future__ import annotations

from typing import Any

import audit
from models import classify_human_actions

NOISE_EVENTS = {"audit_selftest"}


def _entries() -> list[dict]:
    return [e for e in audit.read_entries() if e.get("event") not in NOISE_EVENTS]


def last_reset_seq(entries: list[dict] | None = None) -> int:
    entries = entries if entries is not None else _entries()
    return max((e["seq"] for e in entries if e["event"] == "db_reset"), default=0)


PAYMENT_EVENTS = {"payment_recorded": "approved", "payment_declined_by_human": "declined", "payment_refused": "refused"}


def _payment_key(e: dict) -> tuple[str, int] | None:
    kind, ref_id = e.get("kind"), e.get("ref_id")
    if kind is None and isinstance(e.get("result"), dict):  # older payment_recorded entries
        payment = e["result"].get("payment", {})
        kind, ref_id = payment.get("kind"), payment.get("ref_id")
    return (kind, ref_id) if kind is not None else None


def ticket_statuses(ticket_ids: list[int]) -> dict[int, dict]:
    entries = _entries()
    since = last_reset_seq(entries)
    after_reset = [e for e in entries if e["seq"] > since]
    latest_run: dict[int, dict] = {}
    for e in after_reset:
        if e["event"] == "ticket_run_completed":
            latest_run[e["ticket_id"]] = e

    out: dict[int, dict] = {}
    for tid in ticket_ids:
        run = latest_run.get(tid)
        if run is None:
            out[tid] = {"status": "open", "reason": "Not worked by the agent team since the last reset.",
                        "latest_run": None, "payments": [], "outstanding_actions": [], "signed_off_actions": [],
                        "waiting_actions": []}
            continue
        decision = run.get("decision") if isinstance(run.get("decision"), dict) else {}

        # Latest human decision per proposed payment, after this run.
        payments = []
        for p in decision.get("payment_requests", []):
            key, state, by = (p["kind"], p["ref_id"]), "awaiting_approval", None
            for e in after_reset:
                if e["seq"] > run["seq"] and e["event"] in PAYMENT_EVENTS and _payment_key(e) == key:
                    state, by = PAYMENT_EVENTS[e["event"]], e.get("approved_by")
            payments.append({"kind": p["kind"], "ref_id": p["ref_id"], "payee": p.get("payee"),
                             "amount": p.get("amount"), "state": state, "decided_by": by})

        required, waiting_on_others = classify_human_actions(decision)
        signoffs = {
            e["action"]: e for e in after_reset
            if e["event"] == "human_signoff" and e["run_id"] == run["run_id"] and e.get("action") in required
        }
        outstanding = [a for a in required if a not in signoffs]
        failed = [p for p in payments if p["state"] in ("declined", "refused")]
        waiting = [p for p in payments if p["state"] == "awaiting_approval"]
        if failed:
            status = "open"
            reason = "; ".join(f"{p['kind']} #{p['ref_id']} was {p['state']}" for p in failed) + \
                " — the ticket needs to be re-worked."
        elif outstanding or waiting:
            status, parts = "pending", []
            if waiting:
                parts.append("awaiting human approval of " + ", ".join(f"{p['kind']} #{p['ref_id']}" for p in waiting))
            if outstanding:
                parts.append(f"{len(outstanding)} other human action(s) outstanding")
            reason = "; ".join(parts) + "."
        elif payments or signoffs:
            done = []
            if payments:
                done.append("all proposed payments were approved and recorded")
            if signoffs:
                done.append(f"{len(signoffs)} human action(s) signed off")
            status, reason = "resolved", ("; ".join(done) + "; nothing else remains.").capitalize()
            if waiting_on_others:
                reason += f" {len(waiting_on_others)} follow-up(s) wait on the customer or vendor."
        else:
            status, reason = "resolved", "The Boss concluded no further action is needed."
            if waiting_on_others:
                reason += f" {len(waiting_on_others)} follow-up(s) wait on the customer or vendor."

        out[tid] = {
            "status": status, "reason": reason, "payments": payments, "outstanding_actions": outstanding,
            "waiting_actions": waiting_on_others,
            "signed_off_actions": [
                {"action": a, "signed_off_by": e.get("signed_off_by"), "note": e.get("note"), "at": e["timestamp"]}
                for a, e in signoffs.items()
            ],
            "latest_run": {"run_id": run["run_id"], "completed_at": run["timestamp"],
                           "recommendation": decision.get("recommendation")},
        }
    return out


def run_decision(run_id: str) -> dict | None:
    for e in reversed(_entries()):
        if e["run_id"] == run_id and e["event"] == "ticket_run_completed":
            return e["decision"] if isinstance(e.get("decision"), dict) else None
    return None


def _compact(e: dict, include_results: bool) -> dict:
    keep = {k: e[k] for k in ("seq", "timestamp", "run_id", "ticket_id", "agent", "event") if k in e}
    for k in (
        "tool", "args", "to_agent", "task", "depth", "summary", "tools_called", "delegated_to",
        "reason", "error", "usage", "agents_run", "delegations_used", "approved_by", "kind", "ref_id",
        "request_id", "via", "action", "note", "signed_off_by",
    ):
        if k in e:
            keep[k] = e[k]
    if e["event"] == "ticket_run_completed" and isinstance(e.get("decision"), dict):
        keep["recommendation"] = e["decision"].get("recommendation")
        keep["decision"] = e["decision"]
    if include_results and "result" in e:
        keep["result"] = e["result"]
    return keep


def _agent_activity(run_entries: list[dict]) -> list[dict]:
    """What each agent said and which MCP tools it used, one item per agent invocation."""
    if not run_entries:
        return []
    run_id, ticket_id = run_entries[0]["run_id"], run_entries[0]["ticket_id"]
    activity: list[dict[str, Any]] = []

    boss_tools = sorted({e["tool"] for e in run_entries if e["event"] == "mcp_tool_call" and e["agent"] == "boss"})
    boss_delegated = sorted({e["to_agent"] for e in run_entries if e["event"] == "delegation_started" and e["agent"] == "boss"})
    done = next((e for e in run_entries if e["event"] == "ticket_run_completed"), None)
    failed = next((e for e in run_entries if e["event"] == "ticket_run_failed"), None)
    activity.append({
        "run_id": run_id, "ticket_id": ticket_id, "agent": "boss", "requested_by": None,
        "status": "completed" if done else ("failed" if failed else "running"),
        # Early audit entries stored a truncated decision string instead of a dict.
        "said": (done.get("decision") if isinstance(done.get("decision"), dict) else {}).get("recommendation")
        if done else (failed or {}).get("error"),
        "tools_used": boss_tools, "delegated_to": boss_delegated,
    })
    for e in run_entries:
        if e["event"] == "delegation_completed":
            report = e.get("report") if isinstance(e.get("report"), dict) else {}
            activity.append({
                "run_id": run_id, "ticket_id": ticket_id, "agent": e["to_agent"], "requested_by": e["agent"],
                "status": "completed", "task": e.get("task"),
                "said": e.get("summary"), "recommendations": report.get("recommendations", []),
                "tools_used": e.get("tools_called", []), "delegated_to": e.get("delegated_to", []),
            })
        elif e["event"] in ("delegation_failed", "delegation_blocked"):
            activity.append({
                "run_id": run_id, "ticket_id": ticket_id, "agent": e["to_agent"], "requested_by": e["agent"],
                "status": "failed" if e["event"] == "delegation_failed" else "blocked", "task": e.get("task"),
                "said": e.get("error") or e.get("reason"), "tools_used": [], "delegated_to": [],
            })
    return activity


def recent_events(
    *, limit: int = 100, ticket_id: int | None = None, run_id: str | None = None,
    since_seq: int | None = None, include_results: bool = False,
) -> dict:
    entries = _entries()
    if ticket_id is not None:
        entries = [e for e in entries if e.get("ticket_id") == ticket_id]
    if run_id is not None:
        entries = [e for e in entries if e.get("run_id") == run_id]
    if since_seq is not None:
        entries = [e for e in entries if e["seq"] > since_seq]
    recent = entries[-limit:]

    # Agent breakdown for every ticket run that appears in the window (using the run's full history).
    run_ids = list(dict.fromkeys(e["run_id"] for e in recent if e.get("ticket_id") and e["event"] != "db_reset"))
    by_run: dict[str, list[dict]] = {}
    for e in _entries():
        if e["run_id"] in run_ids:
            by_run.setdefault(e["run_id"], []).append(e)
    activity = [a for rid in run_ids if rid not in ("human_approval",) for a in _agent_activity(by_run.get(rid, []))]

    return {
        "latest_seq": entries[-1]["seq"] if entries else 0,
        "count": len(recent),
        "events": [_compact(e, include_results) for e in recent],
        "agent_activity": activity,
    }
