# Running the n8n automation pipeline (for the demo / screen recording)

This is the Path A "Working Build" deliverable: an n8n workflow that
ingests a simulated bank-credit SMS, calls ShopBot's real decision engine,
and autonomously confirms or escalates the payment.

## One-time setup

```bash
# Node.js (needed for n8n) via nvm, if you don't already have node:
#   https://github.com/nvm-sh/nvm
nvm install --lts
npm install -g n8n
```

## Start everything

**Terminal 1 — ShopBot** (the decision engine + order data):
```bash
cd /Users/arshukla/Documents/Projects/small_scale_payment
source .venv/bin/activate
python -m shopbot run
```

**Terminal 2 — n8n** (the automation pipeline):
```bash
cd /Users/arshukla/Documents/Projects/small_scale_payment
export N8N_USER_FOLDER="$PWD/.n8n"
export N8N_SECURE_COOKIE=false
n8n start
```
First time only, import the workflow (already done once for this repo's
`.n8n/` data folder, but here's the command if you're setting up fresh):
```bash
n8n import:workflow --input=docs/assignment/n8n_workflow.json --userId=<your n8n user id>
n8n publish:workflow --id=mohandas-payment-decision-wf
# restart n8n for the published/active workflow to take effect
```
Or simply open http://localhost:5678, import
`docs/assignment/n8n_workflow.json` via the UI ("Import from File"), and
click **Active** in the top-right toggle.

**Before running it**, open node "2. Analyze + Decide (ShopBot matcher)" and
replace the `key` query parameter's placeholder value
(`REPLACE_WITH_YOUR_SMS_WEBHOOK_SECRET`) with your own `.env`'s
`SMS_WEBHOOK_SECRET` value — the real secret is never committed to the repo.

## Create a test order (so there's something to pay)

Open http://127.0.0.1:8000/sim and, as a demo customer, type:
```
1 poha
takeout
yes
```
Note the order code and amount shown in the pay message (e.g. "Pay ₹50.00
here... Order L691" — the code is also visible on the /admin board).

## Fire a simulated bank SMS at the n8n webhook

```bash
curl -X POST http://localhost:5678/webhook/mohandas-payment-decision \
  -H "Content-Type: application/json" \
  -d '{"from":"VM-DEMOBK","text":"Rs 50.00 credited to A/c XXXXXX1234 UPI Ref No 100000000001. -DEMO BANK","receivedStamp":"1789900000000"}'
```
Replace `Rs 50.00` with the exact amount of the order you created. You
should get back `{"decision":"AUTO_CONFIRMED", ...}` and see the order flip
to PAID on the `/admin` board and the simulator chat in real time.

To see the escalation path, send an SMS with the *wrong* amount instead —
you'll get `{"decision":"ESCALATED_TO_OWNER", ...}` and the order stays
unpaid, visible in `/admin/needs-attention`.

## Where to look while recording

- **n8n editor** (http://localhost:5678) — open the workflow, click into an
  execution from the list to show the actual data flowing through each
  node (ingest → decide → branch → act).
- **ShopBot `/sim`** — the simulated customer's chat, showing the order
  and then "✅ Payment received" arriving live.
- **ShopBot `/admin`** — the live board (order appears under PAID) and, for
  the escalation case, `/admin/needs-attention`.
