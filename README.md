# Uno Reverse Email Agent

You pitched me. Now it's my turn.

A local-first reverse-pitch email agent, currently a **runnable development preview using a synthetic mailbox**. Review a pitch, approve its exact content, simulate a threaded send, organize the conversation, and track replies. The same durable workflow supports a versioned autopilot policy.

**This is not the Gmail MVP yet.** There is no Gmail OAuth or live-mail adapter, and live submission is explicitly disabled. The rules classifier is a synthetic demonstrator, not a validated real-world outreach classifier. No credentials are needed and no real email is sent.

## Run locally

Python 3.11+ on macOS or Linux. Runtime uses the Python standard library; packaging uses setuptools.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
ure demo --timezone America/Los_Angeles
ure scan
ure review
```

The review screen opens on `127.0.0.1` with a per-session token. It displays the source email, recipient, company evidence, exact outgoing message, and organization actions. Edit → save → approve → send to the synthetic mailbox. Editing invalidates approval. Reloading the page requires reopening the full URL printed in your terminal.

Data defaults to `~/.local/share/uno-reverse-demo`. Use `ure --state /absolute/path/to/demo COMMAND` consistently for a separate workspace. `demo` refuses to overwrite an existing synthetic mailbox.

## Commands

```sh
ure status                      # Exact plans, IDs, hashes, and states
ure approve CANDIDATE --hash HASH
ure send CANDIDATE               # Requires exact approval; simulated submission only
ure pause
ure reconcile                   # Find unknown submissions by stable Message-ID
ure resume                      # Explicit; unresolved submissions prevent resume
ure organize CANDIDATE          # Retry labels/archive without resending
ure undo-organization RUN
ure check-replies               # Quiet when unchanged
ure suppress BRAND_OR_ADDRESS
ure profile reviewed-profile.json
ure brands reviewed-brands.json
ure redraft CANDIDATE            # Refresh source/profile, then review and approve again
ure export > local-export.json  # Contains local business/outgoing content, keep private
```

A profile JSON contains `business`, `domain`, `description`, `cta` (HTTPS), and `signature`. Descriptions are supplied by the user as approved facts; the template adds no generated business claims. Brand configuration maps exact sender domains to `{"id":"stable-brand-id","name":"Company Name"}`. Shared IDs merge known aliases; a sender domain alone is never treated as the company identity. Reviewers can set a candidate's company and brand explicitly.

Profile or brand-mapping updates deactivate policies and invalidate unsent approvals. Use `redraft` and review again. Excluded protected messages cannot be approved. `scan --since YYYY-MM-DD` or `scan --all-inbox` changes the scope; CLI displays scope/count and asks before drafting. `scan --yes` confirms it explicitly. Browser Scan uses the fixed seven-day inbox default.

## Try autopilot against synthetic messages

```sh
ure evaluate-classifier
ure autopilot enable --backfill-since 2020-01-01
# Review the printed policy, example pitch and hash. Then repeat with:
ure autopilot enable --backfill-since 2020-01-01 --confirm-hash HASH
ure worker --once
```

Without `--backfill-since`, only messages received after activation qualify. A policy binds the mailbox, profile version, brand mapping, template, classifier, scope, archive choice, local timezone/hours and caps. Defaults: 25 submissions/day, 10/run, five-second spacing, and 15-minute polling. Unknown submissions consume budget and pause the mailbox. Candidate IDs prevent repeat processing across scans.

`ure worker` stays in the foreground; it polls only while the process runs. This prototype sends at most one message per five-second interval and leaves rate-limited candidates for the next poll. `ure monitor` only checks replies. Pause is durable across restarts. Policy activation and mailbox resume are separate actions.

## What's implemented

- SQLite approvals, policy receipts, reservations, suppressions and send attempts; a process lock serializes submissions.
- Conservative recipient/header checks; protected-message exclusions; bounded template composition; real MIME serialization with escaped HTML and reply threading.
- Durable outgoing MIME before submission; explicit unknown-send state and reconciliation; no blind resend.
- Labels/archive recorded as reversible deltas on captured message IDs; newly arrived replies remain in the inbox.
- Local review UI with strict Host/Origin validation, token-protected API, CSP and text-only source rendering.
- Synthetic reply monitoring, quoted-text exclusion, opt-out suppression and quiet repeated checks.

The state name `accepted_by_gmail` matches the proposal's state machine. **In this build it means acceptance by the fake adapter only, never Gmail acceptance or delivery.**

## Validation and next milestones

```sh
python -m unittest discover -s tests -v
```

Tests exercise real SQLite transactions, MIME parsing, concurrent processes, HTTP security boundaries, approval invalidation, crash/timeout recovery, deduplication, policy authorization/caps, organization undo, and reply monitoring. CI installs the package and runs the suite on Python 3.11 and 3.14.

See [implementation status and remaining acceptance work](docs/implementation.md). Gmail Desktop OAuth/PKCE and OS keychain storage, live Gmail pagination/reconciliation, production classifier evaluation, public-suffix normalization, full reply/bounce correlation, and published-only BrandVault integration are not implemented. The MVP is not complete until the proposal's acceptance criteria pass, including a separately authorized live-mail test.

## Local data and recovery

The state directory is mode `0700`; the SQLite database and synthetic mailbox are `0600`. SQLite is not encrypted. Outgoing drafts, profile snapshots, classification evidence and reply excerpts are stored; incoming bodies are only in the synthetic fixture and fetched on demand by review. No telemetry or remote model calls exist. Treat exports as private. Do not import real email into the fake adapter.

Pause before stopping a worker. If a send is unknown, reconcile; an empty search result never authorizes a retry. Reconciliation leaves pause in place until explicit resume. Undo reverses recorded label deltas; it cannot unsend mail. Concurrent manual edits to the same labels cannot be attributed perfectly. The synthetic JSON adapter is a development fixture, not a general concurrent mailbox storage system.

To uninstall, stop the review/worker process and run `python -m pip uninstall uno-reverse-email-agent`. The state directory remains for recovery; archive or remove it yourself only when its local history is no longer needed.

## Project context

The [original proposal](docs/proposal.md) is retained unchanged. The owner chose this standalone private repository on November 5, 2026, superseding its earlier monorepo plan, and subsequently authorized implementation. Public release, product naming, and the proposed Apache-2.0 license remain separate decisions. No open-source license is granted yet.
