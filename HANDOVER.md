# Carrying this on yourself, with Copilot, on Windows

Everything below assumes VS Code and GitHub Copilot on a Windows laptop. The repository
already briefs Copilot for you: `.github/copilot-instructions.md` is read automatically
on every request in this workspace, so you do not need to paste the architecture or the
methodology rules into the chat. Read that file once yourself — it is the same briefing.

---

## 1. One-time setup

1. **Node.js LTS** — [nodejs.org](https://nodejs.org/), accept the defaults, then open a
   **new** terminal and check `node -v` shows v20 or later.
2. **Git** — [git-scm.com](https://git-scm.com/download/win), defaults are fine.
3. **VS Code** — [code.visualstudio.com](https://code.visualstudio.com/), plus the
   **GitHub Copilot** and **GitHub Copilot Chat** extensions, signed in.
4. Clone and install:

   ```powershell
   cd $HOME\Documents
   git clone https://github.com/jacobykx/Radar.git
   cd Radar
   npm install
   code .
   ```

If Copilot does not seem to be using `.github/copilot-instructions.md`, check that
custom instructions are enabled in Copilot's settings — the file is picked up
automatically in current versions, but the setting exists.

---

## 2. The loop, every time

```powershell
git pull                                  # start from what is on main
git checkout -b change/short-description  # never work on main
npm run dev                               # leave this running in one terminal
```

Edit with Copilot (section 3), then in a **second** terminal:

```powershell
npm test
npm run typecheck
```

Look at the change in the browser at **http://127.0.0.1:3010**, then:

```powershell
git add -A
git commit -m "What changed and why"
git push -u origin change/short-description
```

Open the pull request from the link Git prints, or from VS Code's Source Control panel.

---

## 3. Driving Copilot

Use the mode that matches the job:

| Mode | Use it for |
|---|---|
| **Ask** | "Where is X?", "Why does this refuse?", understanding before changing |
| **Edit** | A change across files *you* name — precise, reviewable |
| **Agent** | A change where it should find the files itself — multi-file, more autonomy |

Two habits that make the difference:

- **Name the files.** Drag them into the chat, or type `#` and pick them. Copilot guesses
  badly and asks less when you have not.
- **Say how it will be verified.** "…and update the tests that cover it" is the
  difference between a change that holds and one that quietly breaks a rule.

### Prompts for the jobs you are most likely to have

Each of these is written to be pasted as-is. Adjust the specifics.

**Change a methodology rule** — the highest-risk kind of change, because the rules exist
twice:

> The priority bands should be Critical ≥4.5, High ≥4.0, Medium ≥3.2. Change this in
> both `frontend/lib/engine/constants.ts` and `backend/app/domain/constants.py`, then
> update the threshold cases in `frontend/__tests__/domain-rules.test.ts` and
> `backend/tests/test_domain_rules.py` so both suites still assert the documented
> numbers. Do not change anything else.

**Change the seeded plan** (reviews, capacity, taxonomy, businesses, locations):

> Add a new mandated review to `backend/app/seed/data.py`: ref 4.5, "…", Regulatory
> Reporting Assurance, size L, go-live 2027-06-30, regulator PRA, RRIS-10600. Then tell
> me the command to regenerate the instance JSON.

Then run it — the fixtures and the shipped instance must not drift:

```powershell
cd backend
py -m scripts.export_instance
cd ..
```

**Add a field to a screen:**

> In `frontend/components/StagingCapacity.tsx`, add a column showing each review's
> sub-team, between Team and Business. Read it from the review the way the other columns
> do; do not change `lib/engine/select.ts`.

**Add something a user can change** — this is the one to be careful with, because a new
mutation is a new command:

> Add the ability to edit a review's business on the Risk Radar tab. Follow the existing
> pattern: a new command in `frontend/lib/engine/workflow.ts` that validates, records an
> audit entry and returns a new document, called from the component through
> `plan.run(...)`. Add a test in `frontend/__tests__/workflow.test.ts` covering the audit
> entry and that the caller's document is untouched.

**Investigate something that looks wrong:**

> On the Approval tab, review 6.3 shows Standard but I expected RCA. Explain which code
> decides this and why it produces Standard here. Do not change anything yet.

**Before you commit, when the change touched a rule:**

> Review my working changes against the rules in `.github/copilot-instructions.md` and
> tell me which of them this change could break, and whether a test covers each one.

---

## 4. What to check before pushing

- `npm test` and `npm run typecheck` both clean.
- You have seen the change work in the browser, not only in a test.
- If you changed a rule, **both** the TypeScript and the Python copy changed, and both
  test suites still pass (`cd backend; .venv\Scripts\python -m pytest`).
- If you changed `backend/app/seed/data.py`, you re-ran `py -m scripts.export_instance`
  and committed the regenerated JSON.
- If a statement in `.github/copilot-instructions.md` or the README is now untrue, it is
  updated in the same commit.

Copilot writes plausible code that breaks rules quietly — the four checks above are what
catch that, and none of them take more than a minute.

---

## 5. Shipping it to a Windows host

```powershell
npm install
npm run build:static
```

That writes `frontend\out` — a folder of static files. Copy its contents to the IIS
site's physical path. `web.config` is already inside it. For a site under a sub-path,
set `$env:NEXT_BASE_PATH = "/iap"` before building.

To swap the plan without redeploying, overwrite `instances\2027-iap.json` on the server
with a document exported from the app's **Export instance JSON** button.

Full detail, including running under Node behind IIS, is in the README's
"Hosting on Windows".

---

## 6. Where to look when you are stuck

| Question | Read |
|---|---|
| What is this thing, and how do I run it? | `README.md` |
| Why is the code shaped like this? | `PLAN.md` — decisions D0–D5 and risks R1–R4 |
| What must not be broken? | `.github/copilot-instructions.md` |
| What does rule *n* actually mean? | `frontend/__tests__/domain-rules.test.ts` — one test per rule, in English |
| What can a user change? | `frontend/lib/engine/workflow.ts` — the command list is the answer |
