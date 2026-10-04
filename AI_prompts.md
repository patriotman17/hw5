# AI Prompts Log — HW 5

Running log of the prompts used for each problem. Entries are added as each problem is completed.

---

## Problem 2: 

**Prompt:**

alright bro, we will now be doing problem 2

We need to study the Campus Customs database.

Inspect @HW 5/data/campus_customs.db  and look through every table and all of its fields.

Make an untouched working copy at:

data/campus_customs_new.db

Use campus_customs_new.db for later problems. DO NOT modify the original database.

Inspect these tables:
- desk
- tickets
- inventory
- pricing
- vendors
- leases
- cash_accounts
- payments
- invoices

Also study the three open tickets and understand how each one connects to the other tables.

Create output/harness.md. For each table, include:
- table name
- every field/column
- a short explanation of what the table contains
- one short explanation of why that table matters to the agents

Do not invent any schema or fields AND use the actual database.

At the end, briefly summarize the three open tickets and which tables appear relevant to each.

**Follow-up (if needed):**

> _[to be added, or "None"]_

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

---

## Problem 3: 

**Prompt:**

alright bro, now for problem 3 we we will need to build the MCP server

Create:
 mcp_server/server.py
mcp_server/README.md
Use FastMCP and connect only to @HW 5/data/campus_customs_new.db 

DO NOT use or modify the original @HW 5/data/campus_customs.db .

Create exactly 3 MCP tools based on the three open tickets in the database. Each tool should:
- have a clear name
- use only real database data
- directly help unlock ticket 101, 102, or 103
- NOT invent any information

DO NOT connect or run the MCP server yet. 

Update @HW 5/output/harness.md . For each of the 3 tools, include:
- tool name
- which table(s) it reads
- which ticket it helps unlock: 101, 102, or 103
- one sentence explaining why that tool is the right one for that ticket

Create mcp_server/README.md explaining:
- what the MCP server is for
- that it uses data/campus_customs_new.db
- the 3 tools it provides

**Follow-up (if needed):**

> _[to be added, or "None"]_

**What was missing from the first attempt:** _[one sentence, or "N/A"]_


## Problem 4: 

**Prompt:**

ok time for problem 4. We need to connect the MCP server to Claude Code and test all 3 tools.

Create .mcp.json in the HW 5 project root and configure the local MCP server using the project’s .venv Python and mcp_server/server.py.

Connect Claude Code to the MCP server and test each existing tool:

- check_order_fulfillment
- verify_rent_notice
- evaluate_bulk_discount

Actually call each tool through the MCP connection, not by importing the Python functions directly.

Create output/mcp_smoke.json. For each tool include:
- the prompt used to test it
- the tool name
- the actual tool output

Verify every output matches data/campus_customs_new.db.

Do not change the 3 MCP tools unless something is required to make the connection work.

**Follow-up (if needed):**

ok now complete Problem 4 using the campus-customs MCP server loaded in this session.

Call:
- check_order_fulfillment
- verify_rent_notice
- evaluate_bulk_discount

For each tool, record the test prompt, tool name, and actual output, and verify the output against @data/campus_customs_new.db .

Create output/mcp_smoke.json with the three tests.

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

Claude code needed me to restart the app and start a new chat session in order to connect to the MCP server.

## Problem 5: 

**Prompt:**

@"/Users/macmax/Documents/Mine/MAIN/RAHUL/MBA/Yale/1Y MBA/AI Foundations/" ok bro now moving onto problem 5. We need to build the Campus Customs multi-agent team and expand the MCP tools.

Create these 5 PydanticAI agents:
- Boss
- Inventory
- Accounting
- Facilities
- Customer Service

Use only gpt-6-luna through Portkey for every agent, with PORTKEY_API_KEY from .env in the ai foundation project root

Create one prompt file per agent in backend/prompts/:
- boss.md
- inventory.md
- accounting.md
- facilities.md
- customer_service.md

Put shared Pydantic models/types in backend/models.py.

Give the agents full connectivity: any agent must be able to delegate work to any other agent through async delegation tools, wait for the result, and continue its own reasoning.

Agent roles:
- Boss: owns the ticket, decides which agents to involve, coordinates work, and makes the final recommendation
- Inventory: checks stock, shortages, SKUs/sizes, and vendor restocking options
- Accounting: checks invoices, cash, margins, payments, and purchase/payment implications
- Facilities: handles leases, rent, landlord, and shop-space issues
- Customer Service: drafts customer-facing messages and summarizes customer impact

All shop facts must come through the MCP server using data/campus_customs_new.db. Do not build a second direct-database tool layer for the agents.

Expand mcp_server/server.py with any additional MCP tools needed for tickets 101, 102, and 103.

Enforce these rules:
- use desk.date_today for date decisions
- vendors cannot ship new product while they have an unpaid invoice
- every payment requires human approval
- cash cannot go negative
- customer/vendor communications are drafts only
- never invent missing business data

Create append-only output/audit_trail.json and record meaningful agent/delegation steps. DO NOT wipe old entries.

Update @output/harness.md  with:
- all 5 agents and their roles
- every MCP tool and the table(s) it uses
- safety rules
- token/loop/delegation limits

Update @mcp_server/README.md  so the tool list is current.

DO NOT build the FastAPI backend routes or frontend dashboard yet.

**Follow-up (if needed):**

> _[to be added, or "None"]_

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

---

## Problem 6: 

**Prompt:**

time for problem 6. 

Create output/desk_tickets.html with tabs for:
- Ticket 101
- Ticket 102
- Ticket 103
- Cash
- Reflection

Cash and Reflection should just say “Coming later” for now.

For each ticket, create an Expected section and leave an empty Actual section for a future problem we will do.

Use these expected plans:

Ticket 101:
- Boss calls Inventory first to check fulfillment and size-S stock.
- Inventory delegates to Accounting to investigate the unpaid vendor invoice and financial implications.
- Boss then uses Customer Service to draft the appropriate customer response.
- No payment occurs without human approval.

Ticket 102:
- Boss calls Facilities first to verify the rent notice against the lease.
- Facilities delegates to Accounting to check cash, rent affordability, and other open obligations.
- Do not involve unnecessary agents.

Ticket 103:
- Boss calls Inventory first to check the 20-unit size-M request and shortage.
- Inventory delegates to Accounting to evaluate pricing, cost, and margin implications.
- Boss then uses Customer Service to draft the customer response.
- Do not invent a discount percentage.

For each ticket, list the actual MCP tools from the current MCP server that you expect the agents to use. Use the real tool names; do not invent tool names.

DO NOT run the agents or fill the Actual sections.

**Follow-up (if needed):**

32 expected MCP-tool rows sounds excessive.
The point of the Expected section is to predict the likely agent/delegation path and tools actually needed, not document every tool each agent could potentially call. Since the assignment rewards sensible delegation, I’d keep the core tools and only a small number of genuinely plausible optional ones. Otherwise it may look like we expect the agents to do far more work than necessary.

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

Claude over thought and wrote way too much detail from what i gave it to put into the expected section of the HTML.

## Problem 7: 

**Prompt:**

Nice yo. so we move to problem 7 where we need build the FastAPI backend routes.

Create/update backend/main.py so the backend can support the dashboard.

Add routes to:

- return tickets 101, 102, and 103 with open/resolved status
- run the agent team for a given ticket id
- return recent agent events, including what each agent said and which tools it used
- approve a prepared payment or purchase only after a human approval request
- return the current checking balance
- reset @data/campus_customs_new.db  back to the original campus_customs.db values

Use the existing agent system and MCP tools from Problem 5. Do not create a second direct-database business-logic layer.

For payment approval, the route should trigger the existing human-approved MCP payment flow. Agents must not be able to approve their own payments, cash cannot go negative, and successful payments must update the database.

Make sure the backend runs from the backend/ folder with uvicorn main:app --reload --port 8000

Configure CORS so the React frontend in the next problem we will do (DONT DO THIS YET PLEASSSE) can call it.

Test every route, including:
- valid and invalid ticket ids
- ticket run
- recent events
- payment approval
- insufficient-cash rejection
- checking balance
- reset

Update @output/harness.md  with one line per route showing the URL/method and what it does.

**Follow-up (if needed):**

> _[to be added, or "None"]_

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

---

## Problem 8: 

**Prompt:**

alright bro now for some fun. we will buikld the front end for problem 8 now.

Scaffold the frontend/ folder with React + Vite + TypeScript first.

Build a frontend dashboard in `frontend/` that talks to the backend routes from Problem 7 at `http://localhost:8000`.

Requirements:
- list all three tickets
- show each ticket’s current status from the backend (`open`, `pending`, or `resolved`). do not assume “resolved when a run finishes”; use the backend status
- let the user pick a ticket and start the agent team on it
- while a ticket is running, show live agent activity and recent events
- show what each agent said/did and which tools were used
- show a short summary of what each agent did for that ticket
- show the current checking balance
- when a payment approval is needed, show an approval UI so a human can approve or decline
- after an approval, refresh cash and ticket status
- include a reset control that calls the reset route and refreshes the board

Design / UX:
- make it a polished Sith-themed operations dashboard
- dark interface, black/charcoal panels, deep red glow accents, subtle metallic feel
- Vader / Sith-inspired aesthetic, but do not use copyrighted images or official franchise assets; use CSS, shapes, icons, and/or inline SVG only. i pasted an image for you
- include tasteful animations and transitions
- visually show delegation flow between agents, with animated connectors or movement so the chain of delegation feels alive
- make each agent visually distinct
- make ticket cards/status chips look sharp and modern
- make payment approval panels clear and prominent
- keep it responsive and readable

Suggested layout:
- top header with title and current cash balance
- left column: ticket list / ticket cards
- main panel: selected ticket details, run button, status, decision, pending payments
- right panel or lower panel: live event feed / agent activity timeline
- clear section for agent summaries
- clear section for approval requests

Implementation notes:
- use React + Vite + TypeScript
- create reusable components
- use clean typed API helpers
- handle loading, error, and empty states
- refresh data cleanly after runs, approvals, declines, and reset
- do not break the backend API contracts
- use the backend status as the source of truth

Also create `output/design.md` explaining:
- what frontend structure/components you built
- what visual design choices you made
- how the Sith theme was implemented without relying on copied franchise assets
- what animations/interactions were added
- why the dashboard should feel engaging and easy to use

Verify the app runs with:
- backend: `uvicorn main:app --reload --port 8000` from `backend/`
- frontend: `npm run dev` from `frontend/`


DONT OVERTHINK THIS PLEASE

**Follow-up (if needed):**

> _[to be added, or "None"]_

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

---

## Problem 9: 

**Prompt:**

now for problem we'll need to resolve all 3 tickets. 

BUt before the full run:

1. Reset @data/campus_customs_new.db  back to the original @data/campus_customs.db  values.
2. Record the starting checking balance from cash_accounts.

Then use the actual dashboard/backend to run tickets 101, 102, and 103 until each ticket is resolved.

Use the real agent team, MCP tools, and human approval flow. DO NOT manually fake resolutions or edit database values.

For any payment that requires approval, complete the human approval through the dashboard/API before considering the ticket resolved.

Fill the Cash tab with:
- starting checking balance after reset
- each cash change caused by resolving each ticket, including what was paid and the amount
- ending checking balance

Verify the ending balance exactly matches cash_accounts in campus_customs_new.db.

Create output/resolved_tickets.json. For each ticket include:
- ticket id
- final status
- short outcome
- what each agent contributed
- human approvals

Create output/resolved_board.html with one screenshot of the React dashboard for each resolved ticket: 101, 102, and 103. Store the screenshot files in output/resolved_board_images/ and use relative paths in the HTML.

Make sure the real runs are appended to output/audit_trail.json. Do not wipe existing audit entries.

Finish @output/harness.md  so it clearly covers:
- database tables
- MCP tools
- all five agents
- API routes
- dashboard
- safety/business rules
- limits and approval flow


**Follow-up (if needed):**

ok now update only the Actual sections in output/desk_tickets.html using the results from the final Problem 9 run. Keep every Expected section unchanged.

For Ticket 101, write that:
- Boss, Inventory, Accounting, and Customer Service worked on the ticket.
- Boss delegated first to Inventory, then Accounting and Customer Service were also involved.
- Inventory confirmed size S was out of stock and that M, L, and XL were available.
- Accounting checked the vendor/invoice situation and confirmed the restock was blocked by the unpaid invoice.
- Customer Service drafted a response offering available sizes.
- No payment was made and cash did not change.
- The ticket was resolved after the human operator signed off on the remaining actions.
- Compared with Expected, Accounting was called directly by Boss instead of only through Inventory.

For Ticket 102, write that:
- Boss, Facilities, and Accounting worked on the ticket.
- Boss delegated directly to Facilities and Accounting.
- Facilities verified the rent notice matched the lease.
- Accounting checked cash and prepared the two payments.
- Human approval was given for invoice 501 ($840) and then rent ($2,400).
- Cash moved from $3,400 to $2,560 after invoice 501, then to $160 after rent.
- The ticket was resolved after both payments were approved.
- Compared with Expected, Boss delegated to Facilities and Accounting directly instead of Facilities handing off to Accounting.

For Ticket 103, write that:
- Boss, Inventory, Accounting, and Customer Service worked on the ticket.
- Inventory confirmed only 8 of 20 size-M hoodies were in stock, leaving a shortage of 12.
- Accounting checked pricing/margin and did not invent a discount.
- Customer Service drafted the customer response.
- No payment was made and cash did not change.
- The ticket was resolved after the human operator signed off on the remaining actions and kept the $58 list price.
- Compared with Expected, Accounting used evaluate_bulk_discount instead of get_pricing, and Customer Service did not need a separate inventory check.

For each ticket, also include:
- the actual delegation path
- the MCP tools actually used
- any human approvals/sign-offs
- the final outcome
- a short Actual vs Expected comparison

Use only facts from the recorded final run and audit trail. Do not invent anything.

DO NOT change the expected sections or the cash tab and dont overthink this.

**What was missing from the first attempt:** _[one sentence, or "N/A"]_

I added my reflections on what actually occured when I was testing the agents.

## Problem 10: 

**Prompt:**

ok lets do problem 10 by replacing the “Coming later” content in the Reflection tab of output/desk_tickets.html with the reflection below.

Format it cleanly to match the existing HTML design. Do not change the Ticket 101, Ticket 102, Ticket 103, or Cash tabs.

REFLECTION

1. How did the agents perform on each ticket?

Overall, the agents were accurate and followed the business rules, but their efficiency varied.

Ticket 102 was the strongest use of the multi-agent setup. Facilities verified the landlord, lease, rent amount, and due date, while Accounting checked cash and prepared the payment sequence. Both payments correctly required human approval. After approval, cash moved from $3,400 to $2,560 and then to $160, exactly matching the database. My main concern was that ending with only $160 in checking is financially tight, so the final judgment still benefited from human review.

Ticket 103 was accurate and disciplined. Inventory found that only 8 of the requested 20 medium hoodies were available, leaving a shortage of 12. Accounting used the $22 cost floor and $58 list price without inventing a discount percentage, and Customer Service drafted a response without promising price, quantity, or arrival date. The team was safe, but somewhat conservative because it could have explored options such as alternative sizes or asking the customer what discount they had in mind.

Ticket 101 reached the correct result but was inefficient. Inventory correctly found size S out of stock while M, L, and XL were available. Accounting identified that Bulldog Print Co could not ship while invoice 501 remained unpaid, and Customer Service drafted an appropriate response. However, Accounting ran twice, and the ticket used 59,174 tokens, 16 model calls, and 24 tool calls for a simple $28 order.

2. How did Actual compare with Expected?

The biggest difference was that I expected more agent-to-agent chains, while the Boss often delegated directly to multiple specialists.

For Ticket 101, the expected flow was Boss → Inventory → Accounting, then Boss → Customer Service. The actual run mostly matched, but Boss also called Accounting directly, causing duplicate work.

For Ticket 102, I expected Facilities to hand off to Accounting. Instead, Boss delegated directly to both Facilities and Accounting. The result was still correct and unnecessary agents were not involved.

For Ticket 103, I expected Inventory to hand off to Accounting and expected Accounting to use get_pricing. Instead, Boss called Accounting directly, Accounting used evaluate_bulk_discount, and Customer Service did not need its own inventory lookup.

The main lesson was that flatter, parallel delegation can work well, but only when the Boss passes enough context to avoid repeated tool calls.

3. What would have been simpler as one agent with tools, and why?

All three tickets could technically have been handled by one well-equipped agent.

Ticket 102 is the clearest example: one agent could verify the lease, check cash, prepare the payment plan, and wait for human approval. Ticket 103 already had a tool that returned most of the inventory and pricing information in one call. Ticket 101 could also have been handled with the fulfillment tool, a vendor-status check, and a customer draft.

The most important safety controls came from deterministic tools and rules rather than from the number of agents: payments required human approval, cash could not go negative, customer messages stayed drafts, and business facts came from MCP tools.

The multi-agent structure still added value through clearer role separation and a more readable audit trail, which would matter more as the business and tasks became more complex.

4. What are three new problems the current team could solve?

- Another product goes out of stock and the shop needs to determine whether a vendor can restock it and whether an unpaid invoice blocks shipment.
- Several bills become due at once and the shop needs to prioritize payments without allowing checking to go negative.
- A customer places a large order across multiple sizes and the shop needs to check inventory, shortages, pricing, margin, and draft a response.

The current tools already cover the inventory, vendor, invoice, pricing, cash, payment, and customer-draft information needed for these problems.

5. What are three new problems the current team could not solve?

- Shipment tracking: the system has no carrier or tracking data. It would need a Shipping or Logistics agent with carrier API tools.
- Employee scheduling and payroll: the database has no employee, shift, timecard, wage, or payroll data. It would need a Workforce or HR agent with scheduling and payroll tools.
- Marketing and demand forecasting: the system has no historical sales, web traffic, campaign-performance, or forecasting data. It would need a Marketing or Demand Planning agent with analytics and forecasting tools.

A broader limitation is cash planning. In the final run, the shop started with $3,400, paid $840 for invoice 501 and $2,400 for rent, and ended with $160. Tickets 101 and 103 had no cash impact. A more realistic system would eventually need revenue, receivables, scheduled payments, and cash-flow forecasting.



After adding the reflection, verify the Reflection tab renders correctly and that all five required parts are clearly answered.
**Follow-up (if needed):**

> _[to be added, or "None"]_

**What was missing from the first attempt:** _[one sentence, or "N/A"]_
