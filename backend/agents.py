"""The Campus Customs agent team: Boss, Inventory, Accounting, Facilities, Customer Service.

- Every agent runs on gpt-6-luna through Portkey (config.build_model).
- Shop facts come only from the campus-customs MCP server (one shared stdio
  connection per ticket run); each agent sees only the MCP tools for its role.
- Every agent has a `delegate` tool that can hand work to any other agent,
  await its report, and continue reasoning. Depth, budget, timeout, and token
  limits from config.py keep the network from looping.
- Output validators enforce the shop rules deterministically using what the
  MCP tools actually returned during the run.
- Meaningful steps are appended to output/audit_trail.json.
- Agents can never execute a payment: record_payment is excluded from every
  toolset AND hard-blocked in the MCP call hook. Payments are executed only by
  a human via backend/approve_payment.py.
- A full run (all open tickets) first resets data/campus_customs_new.db to the
  original values (backend/db_reset.py).

CLI (no web server):
  .venv/bin/python backend/agents.py            # full run: reset DB, then 101, 102, 103
  .venv/bin/python backend/agents.py 102        # single ticket, no reset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from functools import cache
from typing import Any

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, ModelRetry, RunContext, Tool
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.tools import ToolDefinition

import audit
from db_reset import reset_db
from config import (
    AGENT_RETRIES,
    DELEGATION_TIMEOUT_SECONDS,
    HW5_ROOT,
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_OUTPUT_TOKENS_PER_RESPONSE,
    MCP_PYTHON,
    MCP_SERVER_PATH,
    MODEL_NAME,
    PROMPTS_DIR,
    SUBAGENT_USAGE_LIMITS,
    TICKET_USAGE_LIMITS,
    build_model,
)
from models import (
    AGENT_NAMES,
    AgentDeps,
    AgentName,
    DelegationResult,
    SpecialistReport,
    TicketDecision,
    TicketRunOutcome,
    TicketRunState,
    outstanding_human_actions,
)

# ---------------------------------------------------------------------------
# MCP access per role
# ---------------------------------------------------------------------------

_COMMON_TOOLS = {"get_desk_date", "get_ticket"}

TOOL_ACCESS: dict[AgentName, set[str]] = {
    "boss": _COMMON_TOOLS | {"list_open_tickets"},
    "inventory": _COMMON_TOOLS
    | {
        "get_inventory",
        "get_restock_options",
        "check_vendor_status",
        "check_order_fulfillment",
        "evaluate_bulk_discount",
    },
    "accounting": _COMMON_TOOLS
    | {
        "get_cash_position",
        "get_invoices",
        "get_pricing",
        "get_payments",
        "check_vendor_status",
        "prepare_payment_plan",
        "evaluate_bulk_discount",
    },
    "facilities": _COMMON_TOOLS | {"get_lease", "verify_rent_notice", "get_cash_position"},
    "customer_service": _COMMON_TOOLS | {"get_inventory", "get_pricing"},
}

# Tools no agent may call, even if a toolset were misconfigured.
HUMAN_ONLY_TOOLS = {"record_payment"}
assert not any(HUMAN_ONLY_TOOLS & tools for tools in TOOL_ACCESS.values())

ALL_TICKETS = [101, 102, 103]

PROMPT_FILES: dict[AgentName, str] = {name: f"{name}.md" for name in AGENT_NAMES}


def _as_dict(result: Any) -> dict | None:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


async def _audited_mcp_call(ctx: RunContext[AgentDeps], call_tool, name: str, args: dict[str, Any]):
    """Wrap every MCP call: audit it and capture facts the validators need."""
    deps, state = ctx.deps, ctx.deps.state
    if name in HUMAN_ONLY_TOOLS or name not in TOOL_ACCESS[deps.agent]:
        audit.record(
            "mcp_tool_blocked", run_id=state.run_id, ticket_id=state.ticket_id,
            agent=deps.agent, tool=name, args=args,
        )
        raise ModelRetry(f"{name} is not available to the {deps.agent} agent. Payments need human approval.")
    try:
        result = await call_tool(name, args)
    except Exception as exc:
        audit.record(
            "mcp_tool_error", run_id=state.run_id, ticket_id=state.ticket_id,
            agent=deps.agent, tool=name, args=args, error=str(exc),
        )
        raise

    deps.tools_called.add(name)
    data = _as_dict(result) or {}
    if name == "get_desk_date" and data.get("date_today"):
        state.desk_date = data["date_today"]
    elif data.get("desk_date"):
        state.desk_date = data["desk_date"]
    if name in {"check_vendor_status", "get_restock_options"}:
        for vendor in data.get("vendors", []):
            state.vendor_status[vendor["id"]] = vendor
    if name == "prepare_payment_plan":
        state.payment_plans.append(data)

    audit.record(
        "mcp_tool_call", run_id=state.run_id, ticket_id=state.ticket_id,
        agent=deps.agent, tool=name, args=args, result=result,
    )
    return result


mcp_toolset = MCPToolset(
    StdioTransport(command=MCP_PYTHON, args=[str(MCP_SERVER_PATH)], cwd=str(HW5_ROOT)),
    id="campus-customs",
    process_tool_call=_audited_mcp_call,
)


# ---------------------------------------------------------------------------
# Delegation (full connectivity: any agent -> any other agent)
# ---------------------------------------------------------------------------


async def _delegation_available(ctx: RunContext[AgentDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    """Hide the delegate tool once depth or the per-ticket budget is used up."""
    if ctx.deps.depth >= MAX_DELEGATION_DEPTH:
        return None
    if ctx.deps.state.delegations_used >= MAX_DELEGATIONS_PER_TICKET:
        return None
    return tool_def


async def delegate(ctx: RunContext[AgentDeps], agent: AgentName, task: str) -> dict[str, Any]:
    """Hand a sub-task to another Campus Customs agent, wait for its report, then continue.

    Agents you can delegate to (never yourself):
    - boss: owns the ticket, coordinates, makes the final recommendation.
    - inventory: stock by SKU/size, shortages, vendor restock options and lead times.
    - accounting: invoices, cash, margins, discount math, payment plans (pending human approval).
    - facilities: leases, rent, landlord verification, shop-space issues.
    - customer_service: customer-facing draft messages and customer-impact summaries.

    Several delegate calls in the same turn run in parallel.

    Args:
        agent: Which agent should do the work.
        task: A specific, self-contained request including the relevant facts
            you already have (SKU, size, qty, amounts) and what you need back.
    """
    caller = ctx.deps
    state = caller.state
    depth = caller.depth + 1
    key = (agent, " ".join(task.lower().split()))
    base = {"from_agent": caller.agent, "to_agent": agent, "task": task, "depth": depth}

    def blocked(reason: str) -> dict[str, Any]:
        audit.record(
            "delegation_blocked", run_id=state.run_id, ticket_id=state.ticket_id,
            agent=caller.agent, to_agent=agent, task=task, reason=reason,
        )
        return DelegationResult(**base, ok=False, error=reason).model_dump()

    if agent == caller.agent:
        return blocked("An agent cannot delegate to itself.")
    if depth > MAX_DELEGATION_DEPTH:
        return blocked(f"Max delegation depth {MAX_DELEGATION_DEPTH} reached; finish with what you have.")

    async with state.lock:
        if key in state.delegation_cache:
            audit.record(
                "delegation_cache_hit", run_id=state.run_id, ticket_id=state.ticket_id,
                agent=caller.agent, to_agent=agent, task=task,
            )
            caller.delegated_to.add(agent)
            return {**state.delegation_cache[key], "cached": True}
        if state.delegations_used >= MAX_DELEGATIONS_PER_TICKET:
            return blocked(
                f"Delegation budget of {MAX_DELEGATIONS_PER_TICKET} for this ticket is used up; "
                "finish with what you have."
            )
        state.delegations_used += 1

    chain = (*caller.chain, caller.agent)
    child = AgentDeps(agent=agent, state=state, depth=depth, chain=chain)
    audit.record(
        "delegation_started", run_id=state.run_id, ticket_id=state.ticket_id, agent=caller.agent,
        to_agent=agent, task=task, depth=depth, chain=[*chain, agent],
        delegations_used=state.delegations_used,
    )
    prompt = (
        f"Ticket {state.ticket_id}. Request from the {caller.agent} agent:\n{task}\n\n"
        "Use your MCP tools for every shop fact, then return your report."
    )
    try:
        result = await asyncio.wait_for(
            get_team()[agent].run(
                prompt, deps=child, usage=ctx.usage, usage_limits=SUBAGENT_USAGE_LIMITS
            ),
            timeout=DELEGATION_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # timeout, usage limit, model/tool failure
        error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        audit.record(
            "delegation_failed", run_id=state.run_id, ticket_id=state.ticket_id,
            agent=caller.agent, to_agent=agent, task=task, error=error,
        )
        return DelegationResult(**base, ok=False, error=error).model_dump()

    report = result.output.model_dump()
    caller.delegated_to.add(agent)
    state.agents_run.append(agent)
    out = DelegationResult(**base, ok=True, report=report).model_dump()
    state.delegation_cache[key] = out
    audit.record(
        "delegation_completed", run_id=state.run_id, ticket_id=state.ticket_id, agent=caller.agent,
        to_agent=agent, depth=depth, task=task, summary=report.get("summary") or report.get("recommendation"),
        tools_called=sorted(child.tools_called), delegated_to=sorted(child.delegated_to), report=report,
    )
    return out


# ---------------------------------------------------------------------------
# Rule enforcement on every agent's output
# ---------------------------------------------------------------------------


def _reject(ctx: RunContext[AgentDeps], message: str) -> ModelRetry:
    state = ctx.deps.state
    audit.record(
        "output_rejected", run_id=state.run_id, ticket_id=state.ticket_id,
        agent=ctx.deps.agent, reason=message,
    )
    return ModelRetry(message)


def _check_rules(ctx: RunContext[AgentDeps], out: SpecialistReport | TicketDecision) -> None:
    deps, state = ctx.deps, ctx.deps.state

    # Never invent business data: every fact must cite a tool called in this run, an agent this
    # agent delegated to, or the agent that requested this work (facts passed in its task).
    allowed = deps.tools_called | {f"delegation:{a}" for a in (*deps.delegated_to, *deps.chain[-1:])}
    if not out.facts:
        raise _reject(ctx, "List the facts you relied on, each with its source tool or delegation:<agent>.")
    bad = sorted({f.source for f in out.facts if f.source not in allowed})
    if bad:
        raise _reject(
            ctx,
            f"Fact sources {bad} were not used in this run. Valid sources: {sorted(allowed)}. "
            "Call the tool (or delegate) first, or move the item to missing_data. Do not invent data.",
        )

    # Every payment needs human approval and must come from a feasible prepare_payment_plan result.
    feasible: dict[tuple[str, int], dict] = {}
    starting_balance: float | None = None
    for plan in state.payment_plans:
        starting_balance = plan.get("starting_balance", starting_balance)
        for item in plan.get("items", []):
            if item.get("feasible"):
                feasible[(item["kind"], item["ref_id"])] = item
    for p in out.payment_requests:
        item = feasible.get((p.kind, p.ref_id))
        if item is None:
            raise _reject(
                ctx,
                f"Payment request {p.kind} #{p.ref_id} was not confirmed feasible by prepare_payment_plan. "
                "Ask the accounting agent to run it, or drop the request.",
            )
        if abs(p.amount - item["amount"]) > 0.005:
            raise _reject(ctx, f"Payment {p.kind} #{p.ref_id} amount must be {item['amount']} (from the database).")
    if out.payment_requests and starting_balance is not None:
        total = sum(p.amount for p in out.payment_requests)
        if total > starting_balance + 0.005:
            raise _reject(
                ctx,
                f"Requested payments total ${total:,.2f} but cash is ${starting_balance:,.2f}; "
                "cash cannot go negative. Drop or defer payments.",
            )

    for action in out.proposed_actions:
        if action.kind == "payment" and not action.requires_human_approval:
            raise _reject(ctx, "Every payment action must have requires_human_approval=true.")
        if action.kind == "vendor_restock":
            if action.vendor_id is None:
                raise _reject(ctx, "vendor_restock actions need a vendor_id.")
            status = state.vendor_status.get(action.vendor_id)
            if status is None:
                raise _reject(
                    ctx,
                    f"Vendor {action.vendor_id}'s payment status is unknown. Check it with check_vendor_status "
                    "(inventory or accounting) before proposing a restock.",
                )
            if not status["can_ship_new_product"] and not action.blocked_by:
                raise _reject(
                    ctx,
                    f"Vendor {action.vendor_id} ({status['name']}) has unpaid invoices and cannot ship new "
                    "product. Set blocked_by to the unpaid invoice(s).",
                )


def _validate_specialist(ctx: RunContext[AgentDeps], out: SpecialistReport) -> SpecialistReport:
    _check_rules(ctx, out)
    return out.model_copy(update={"agent": ctx.deps.agent, "ticket_id": ctx.deps.state.ticket_id})


def _validate_boss(ctx: RunContext[AgentDeps], out: TicketDecision) -> TicketDecision:
    _check_rules(ctx, out)
    state = ctx.deps.state
    if state.desk_date is None:
        raise _reject(ctx, "Call get_desk_date (or get_ticket): every date decision uses desk.date_today.")
    return out.model_copy(
        update={
            "ticket_id": state.ticket_id,
            "desk_date": state.desk_date,
            "agents_consulted": sorted(ctx.deps.delegated_to),
            "awaiting_payment_approval": bool(out.payment_requests),
            "other_human_action_required": bool(outstanding_human_actions(out.model_dump())),
        }
    )


def _run_context(ctx: RunContext[AgentDeps]) -> str:
    deps, state = ctx.deps, ctx.deps.state
    remaining = MAX_DELEGATIONS_PER_TICKET - state.delegations_used
    can_delegate = deps.depth < MAX_DELEGATION_DEPTH and remaining > 0
    chain = " -> ".join([*deps.chain, deps.agent])
    return (
        f"Run context: ticket {state.ticket_id}; you are the {deps.agent} agent; chain: {chain}; "
        f"depth {deps.depth}/{MAX_DELEGATION_DEPTH}; delegations left for this ticket: {remaining}. "
        + ("You may delegate." if can_delegate else "You cannot delegate further; answer with what you have.")
    )


# ---------------------------------------------------------------------------
# Team construction and ticket runner
# ---------------------------------------------------------------------------


def _build_agent(name: AgentName, model) -> Agent:
    allowed = TOOL_ACCESS[name]
    output_type = TicketDecision if name == "boss" else SpecialistReport
    agent = Agent(
        model,
        name=name,
        output_type=output_type,
        deps_type=AgentDeps,
        instructions=(PROMPTS_DIR / PROMPT_FILES[name]).read_text(encoding="utf-8"),
        toolsets=[mcp_toolset.filtered(lambda ctx, td: td.name in allowed)],
        tools=[Tool(delegate, takes_ctx=True, prepare=_delegation_available)],
        retries=AGENT_RETRIES,
        model_settings={"max_tokens": MAX_OUTPUT_TOKENS_PER_RESPONSE},
    )
    agent.instructions(_run_context)
    agent.output_validator(_validate_boss if name == "boss" else _validate_specialist)
    return agent


@cache
def get_team() -> dict[AgentName, Agent]:
    model = build_model()
    return {name: _build_agent(name, model) for name in AGENT_NAMES}


async def run_ticket(ticket_id: int) -> TicketDecision:
    """Have the Boss work one ticket end to end. Nothing is paid or sent."""
    return (await run_ticket_detailed(ticket_id)).decision


async def run_ticket_detailed(ticket_id: int) -> TicketRunOutcome:
    """Same as run_ticket, but also returns the run id and token usage (used by the API)."""
    state = TicketRunState(run_id=uuid.uuid4().hex[:12], ticket_id=ticket_id)
    deps = AgentDeps(agent="boss", state=state)
    audit.record(
        "ticket_run_started", run_id=state.run_id, ticket_id=ticket_id, agent="boss", model=MODEL_NAME,
        limits={
            "max_delegation_depth": MAX_DELEGATION_DEPTH,
            "max_delegations_per_ticket": MAX_DELEGATIONS_PER_TICKET,
            "delegation_timeout_seconds": DELEGATION_TIMEOUT_SECONDS,
            "max_output_tokens_per_response": MAX_OUTPUT_TOKENS_PER_RESPONSE,
            "ticket": {
                "request_limit": TICKET_USAGE_LIMITS.request_limit,
                "tool_calls_limit": TICKET_USAGE_LIMITS.tool_calls_limit,
                "total_tokens_limit": TICKET_USAGE_LIMITS.total_tokens_limit,
                "output_tokens_limit": TICKET_USAGE_LIMITS.output_tokens_limit,
            },
            "subagent_cutoff": {
                "request_limit": SUBAGENT_USAGE_LIMITS.request_limit,
                "tool_calls_limit": SUBAGENT_USAGE_LIMITS.tool_calls_limit,
                "total_tokens_limit": SUBAGENT_USAGE_LIMITS.total_tokens_limit,
                "output_tokens_limit": SUBAGENT_USAGE_LIMITS.output_tokens_limit,
            },
        },
    )
    try:
        async with mcp_toolset:
            result = await get_team()["boss"].run(
                f"Work ticket {ticket_id} and return your final recommendation.",
                deps=deps,
                usage_limits=TICKET_USAGE_LIMITS,
            )
    except Exception as exc:
        audit.record(
            "ticket_run_failed", run_id=state.run_id, ticket_id=ticket_id, agent="boss",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    usage = {
        "requests": result.usage.requests,
        "tool_calls": result.usage.tool_calls,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
    }
    agents_run = ["boss", *state.agents_run]
    audit.record(
        "ticket_run_completed", run_id=state.run_id, ticket_id=ticket_id, agent="boss",
        agents_run=agents_run, delegations_used=state.delegations_used, usage=usage,
        decision=result.output.model_dump(),
    )
    return TicketRunOutcome(
        run_id=state.run_id, ticket_id=ticket_id, decision=result.output, usage=usage,
        agents_run=agents_run, delegations_used=state.delegations_used,
    )


async def run_all_tickets() -> list[TicketDecision]:
    """Full run: reset the working DB to the original values, then work every ticket in order."""
    reset_db(reason="full run of all tickets")
    return [await run_ticket(ticket_id) for ticket_id in ALL_TICKETS]


async def _main(ticket_ids: list[int]) -> None:
    if not ticket_ids or sorted(ticket_ids) == ALL_TICKETS:
        decisions = await run_all_tickets()
    else:
        decisions = [await run_ticket(ticket_id) for ticket_id in ticket_ids]
    for decision in decisions:
        print(json.dumps(decision.model_dump(), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team on tickets.")
    parser.add_argument("ticket_ids", nargs="*", type=int, help="omit for a full run (resets the DB first)")
    asyncio.run(_main(parser.parse_args().ticket_ids))
