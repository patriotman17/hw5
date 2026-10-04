# Campus Customs: Multi-Agent Shop Operations (HW 5)

A five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service) works the Campus Customs desk tickets.

- **Model:** every agent runs on **gpt-6-luna through Portkey**.
- **Shop data:** agents get shop facts only through a **FastMCP server** over the SQLite database.
- **Payments:** money moves only after a **human approves** in the React dashboard.

Full reference: [`output/harness.md`](output/harness.md). Dashboard design notes: [`output/design.md`](output/design.md).

```
data/            campus_customs.db (original, never modified) · campus_customs_new.db (working copy the app uses)
mcp_server/      server.py — the MCP tools (the only code that reads or writes the shop DB)
backend/         main.py (FastAPI) · agents.py (PydanticAI team) · models.py · prompts/*.md
frontend/        React + Vite + TypeScript dashboard
output/          harness.md · mcp_smoke.json · desk_tickets.html · design.md · resolved_tickets.json ·
                 resolved_board.html (+ resolved_board_images/) · audit_trail.json · github_url.txt
```

## 1. Setup (once)

Requires Python 3.11+ and Node 20+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env        # then put your real PORTKEY_API_KEY in .env
```

`.env` is git-ignored; never commit it. The backend reads `./.env` first, then falls back to a `.env` one folder up.

## 2. Get a clean database (copy the original over the working copy)

`data/campus_customs.db` is the untouched original. The app only uses `data/campus_customs_new.db`, which the final run changed (two payments, $3,400 → $160). For a clean run, copy the original over it:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

`.venv/bin/python backend/db_reset.py` does the same copy, verifies the files are byte-identical (SHA-1), and logs the reset in the audit trail. The dashboard's **Reset shop** button and `POST /api/reset` do exactly the same thing.

## 3. Start the MCP server

The server speaks MCP over **stdio**, so a client launches it as a subprocess:

- **The backend starts it automatically**, once for its own routes and once per agent run. You don't need a separate terminal.
- To run it by hand, or to check that it starts:

  ```bash
  .venv/bin/python mcp_server/server.py
  ```

  It waits for an MCP client on stdin; press Ctrl-C to stop.
- **Claude Code** picks it up from `.mcp.json` when opened in this folder.

## 4. Start the FastAPI backend

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

Check it's up: http://localhost:8000/api/health. Interactive API docs are at http://localhost:8000/docs.

## 5. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The backend allows this origin through CORS.

## 6. Full three-ticket run

1. **Reset the database first:** click **Reset shop** in the dashboard (it asks you to click twice), or run step 2. Checking goes back to **$3,400**, and all three tickets show **Open**.
2. Type your name in **Human operator** (agent names are refused).
3. For each ticket (101, 102, 103):
   - select it and click **Dispatch the agent team**;
   - watch the delegation graph and the live event feed while it runs.
4. Finish what the backend says is still needed:
   - **Payments:** in **Human approval**, click **Open approval request**, tick the confirm box, then **Approve & pay** (or **Decline**). The MCP `record_payment` tool executes the payment and refuses anything that would make cash negative.
   - **Other decisions** (drafts, pricing): click **Sign off** with a note on each item under **Boss decision → Human actions**. Drafts are approved for the owner to send; the system never sends anything.
5. A ticket shows **Resolved** only when the backend confirms every payment and sign-off is done.

The final run recorded in `output/` ended with checking at **$160.00**: invoice 501 ($840) and rent ($2,400) were paid. The agents can also run from the command line: `.venv/bin/python backend/agents.py`. With no ticket ids, it resets the DB and runs 101, 102, and 103.

## Safety rules (enforced in code)

- Dates come from `desk.date_today` (2026-08-31). Vendor lead times come from the `vendors` table.
- A vendor with an unpaid invoice can't ship new product.
- Every payment needs a named human's approval. Agents have no payment tool.
- Cash never goes negative, and cash only goes out.
- Customer, vendor, and landlord messages are drafts only.
- Agents must cite the MCP tool behind every fact, and they never invent data.
- Limits per ticket: 90k tokens, 25 model calls, 35 tool calls, 6 delegations, delegation depth 2.
- Every step is appended to `output/audit_trail.json`.
