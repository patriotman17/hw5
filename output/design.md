# Campus Customs · Sith Ops — Dashboard Design (Problem 8)

React 19 + Vite + TypeScript app in `frontend/`. It talks only to the Problem 7 FastAPI routes at `http://localhost:8000` (set `VITE_API_BASE` to change it).

**Run:**

```bash
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev   # http://localhost:5173
```

## Structure

```
frontend/src/
  api.ts                  typed API client: one function per backend route, response types, ApiError with the backend's message
  agents.ts               agent metadata (name, role, color, glyph) + buildRunView(): turns a ticket's audit events into the
                          current run (delegation edges and their state, active agents, decision, usage)
  App.tsx                 state, polling, run / approve / decline / reset handlers, toasts
  components/
    Header.tsx            title, helmet logo, animated checking balance, two-step reset
    TicketList.tsx        ticket cards with backend status chips, running scan line, "payments awaiting" alert
    TicketDetail.tsx      selected ticket: notes, backend status + reason, lightsaber run button, usage
    DelegationFlow.tsx    SVG graph of the five agents with animated delegation edges
    ApprovalPanel.tsx     human approval: open request → confirm → approve / decline
    DecisionPanel.tsx     Boss recommendation, outstanding human actions, drafts (marked "not sent"), rule checks, facts
    AgentSummaries.tsx    one card per involved agent: what it said, who asked it, who it delegated to, MCP tools used
    EventFeed.tsx         live timeline of audit events (tool calls, delegations, reports, rejections, decision)
    Primitives.tsx        HelmetLogo, AgentBadge, AgentName, StatusChip, AnimatedNumber, Spinner, EmptyState
  index.css               theme tokens, layout, components, animations, responsive breakpoints, reduced-motion
```

### Data flow

- **The backend is the source of truth for status.**
  - The `open` / `pending` / `resolved` chips, `status_reason`, `pending_payments`, and `outstanding_actions` come directly from `GET /api/tickets`.
  - The UI never marks a ticket resolved because a run finished. After a run, the toast reports the status the backend returned, e.g. "status is now pending".
- **Running a ticket:** `POST /api/tickets/{id}/run` is awaited (about 20–60 s).
  - Meanwhile the app polls `GET /api/events?ticket_id=…` every 1.2 s and the board (tickets, cash, approval requests) every 3 s, so agent activity streams in live while the request is still open.
  - When idle, polling slows to 6 s and 8 s.
- **Payments:** the dashboard never sends an amount.
  - It opens an approval request (`POST /api/payments/requests` with the run id the agents proposed it in).
  - Then it calls approve (`confirm: "APPROVE"` plus a human name) or decline. The MCP `record_payment` tool does the actual write.
  - Errors from the backend, such as insufficient cash (409) or an agent-name approver (403), are shown on the payment card and as a toast.
- **Refresh:** after every run, approval, decline, and reset, the app re-fetches tickets, cash, approval requests, and the selected ticket's events together.
- **Which run is shown:** the run panels (flow, decision, summaries) only show the run the backend counts (`latest_run`, i.e. since the last reset) or one in progress. Runs from before a reset stay in the event history only, so a freshly reset ticket doesn't look half-worked.
- **States handled:** loading, error, and empty states for tickets, events, cash, and the selected ticket. "Backend unreachable" names the URL.

## Visual design

- **Palette:** near-black void (`#050506`), charcoal panels (`#121217`/`#18181f`), steel lines, and a single deep-red accent (`#e0182d` → `#ff3346`) used for glow, focus, and the selection state.
  - Status colors are kept separate from the red so they stay readable: grey open, amber pending, green resolved, red running.
- **Metal feel:** every panel has a faint top-lit gradient overlay plus an inset highlight, so surfaces read as brushed metal rather than flat boxes.
- **Agent identity:** each agent has its own hue and glyph, used everywhere it appears (graph node, badge, summary card stripe, feed marker):
  - Boss: crimson crown
  - Inventory: ember crate
  - Accounting: gold coin
  - Facilities: violet building
  - Customer Service: cyan speech bubble
- **Type:** system sans for UI. Uppercase, widely tracked headings echo console readouts. Monospace for money, ids, tool names, and timestamps.
- **Hierarchy:**
  - left: ticket queue
  - center: ticket hero → delegation flow → human approval → Boss decision → agent summaries
  - right: event feed
- **Approvals:** when a payment is awaiting approval, the panel gets an amber border and glow plus a blinking count. It sits directly under the flow, above the decision, so it can't be missed.

## Sith theme without franchise assets

- **The helmet logo is drawn from scratch** as inline SVG paths: dome, ridge, brow, angular lenses, triangular grille, flared skirt.
  - The reference image you shared only guided the general silhouette. No image file, trace, logo, or font from the franchise is used, and nothing was image-generated.
- **The "lightsaber" is pure CSS gradients and box-shadow glow:** the header's sweeping red line, the run button's blade that ignites on hover and while running, and the spinner.
- **No external fonts, icon packs, or images are loaded.** Agent glyphs are hand-written 24×24 SVG paths, and the starfield is layered radial gradients.

## Animations & interactions

| Where | Effect |
|---|---|
| Header | Red "saber" line slowly sweeps; helmet lenses glow and flicker; the cash balance tweens to its new value after payments or reset, and turns amber below $500 |
| Run button | Blade ignites across the bottom on hover; while running, the button hums (pulsing glow) and shows a spinner |
| Delegation flow | Faint lattice of every possible link (full connectivity). Each delegation draws a curved edge in a gradient from caller to callee color. In-flight edges flow fast and carry a glowing particle along the path; finished edges turn solid; failed or blocked edges go grey and dashed. Active agents get an expanding pulse ring; uninvolved agents dim. Repeat delegations bend further so parallel edges stay visible |
| Ticket cards | Staggered rise-in; hover slide; red glow on the selected card; scanning light bar while running; pending/running chips blink |
| Feed | New events slide in; a live pill blinks while a run is active |
| Agent cards | Staggered rise-in; working agents glow in their own color and pulse "Working…" |
| Approvals | Approve is disabled until a human name is entered and the confirm box is checked; cash-impact bar animates; toasts confirm each action |
| Reset | Two-step: the first click arms (pulsing red "Confirm reset?" for 4 s), the second resets. Disabled while any ticket runs |

`prefers-reduced-motion` turns all of this off.

## Why it's engaging and easy to use

- **One screen tells the whole story:** what the ticket is, who is working on it right now, who asked whom, what each agent found and which MCP tools it used, what the Boss recommends, and what still needs a human.
- **The motion means something:** a moving particle is a live delegation, a pulsing ring is an agent at work, amber means a human is needed. Decoration never competes with information.
- **Safety is visible:**
  - Payments need a named human and an explicit confirmation.
  - Drafts are stamped "not sent".
  - Status chips reflect the backend's rules, so the board never claims a ticket is done when a payment or follow-up is outstanding.
- **Responsive:** three columns on wide screens, two (feed below) under 1220 px, one column on phones. Verified at 375 px with no horizontal scrolling.

## Verified (2026-10-04, backend + `npm run dev`)

- **Tickets load:** three cards with backend statuses; cash shows $3,400.
- **Live run (103):** Running chip, Live feed, Boss → Inventory edge in flight with a particle, pulsing active nodes.
- **After the 103 run:**
  - status **Pending** from the backend (3 outstanding human actions);
  - the decision and a draft marked "not sent";
  - four agent summary cards, each with what it said and its MCP tools;
  - all edges marked done.
- **Run 102:** Pending with two payments awaiting approval.
  - Approving invoice 501 took cash to **$2,560**; the ticket stayed Pending.
  - Declining rent left cash unchanged and moved the ticket to **Open** ("needs to be re-worked").
  - A re-run proposed rent only. Approving it took cash to **$160** and the ticket to **Resolved**.
- **Reset:** two-click confirm, cash back to $3,400, all tickets Open, run panels cleared.
- **Other checks:** mobile layout (375 px) has no overflow; `npm run build` passes; the DB is identical to the original afterwards.
- **Backend fix found during testing:** `GET /api/events` returned 500 when the window included early audit entries whose decision had been stored as a truncated string. `backend/events.py` now ignores those (and `run_decision` does too).
- **Additive backend change:** compact `ticket_run_completed` events now include the full `decision`, so the dashboard can show drafts and rationale after a reload. No existing field changed.

## Problem 9 addition: operator name and human sign-off

- **Operator name:** a single *Human operator* field in the header now supplies the name for every payment approval and sign-off. It's saved in `localStorage`, and agent names are rejected, matching the backend's rule.
- **Sign-off:** in the Boss decision panel, each outstanding non-payment action gets a note field and a **Sign off** button, which calls `POST /api/tickets/{id}/signoffs`. Draft actions pre-fill an honest note: "approved for the owner to send; not sent by the system". Signed-off items turn green and show who signed and what they decided.
- **Status:** the ticket chip flips to **Resolved** only when the backend says every payment and sign-off is complete.
