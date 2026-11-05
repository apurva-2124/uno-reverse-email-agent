# Uno Reverse Email Agent

Status: proposed — ready for review, not implementation approval  
Author: Optimly team  
Date: 2026-11-05  
Working tagline: You pitched me. Now it's my turn.

## 1. Problem statement

Founders receive repetitive marketing outreach while struggling to get attention for their own products. Replying with a friendly reverse pitch can start conversations, but manually identifying outreach, checking recipients, writing pitches, avoiding duplicates, organizing threads, and checking responses is tedious.

Uno Reverse Email Agent is an open-source, local-first agent that turns incoming marketing outreach into a user-approved pitch for the user's business, then organizes the conversation and tracks responses. Optional Optimly BrandVault integration supplies approved brand facts and creates a useful path to BrandVault adoption.

The first manual run sent 133 pitches to distinct brands. Follow-up checks found one positive response, one decline, automated acknowledgements, and two delivery failures. These are observations from a single run, not a conversion benchmark. Sender domains also proved insufficient for company identification: a sales domain used by Zipchat was mistaken for the brand being pitched.

## 2. Goals

- A user can connect Gmail, configure their business, choose review mode or autopilot in the MVP, send reverse pitches, and organize the resulting conversations.
- The complete core workflow works without an Optimly account.
- BrandVault users can reuse explicitly published, approved information through a read-only integration.
- One eligible brand receives at most one initial reverse pitch per connected mailbox unless the user explicitly resets that decision.
- Each external action is attributable to a reviewed plan or an explicitly enabled automation policy.
- Results distinguish Gmail acceptance, bounce reports, automated responses, substantive replies, and expressed interest.
- The project is runnable locally, documented, testable, and suitable for public contributions.

## 3. Non-goals

- Purchased prospect lists, discovering new recipients, cold outbound campaigns unrelated to received outreach, or reply-all blasts.
- Automatically negotiating, answering substantive replies, or sending follow-up sequences.
- Automatically claiming brands, publishing BrandVaults, or enrolling recipients in Optimly.
- Outlook, IMAP, hosted multi-tenant infrastructure, and a desktop installer in the first release.
- Guaranteed delivery, exactly-once delivery across Gmail and local storage, or guaranteed AI recommendations.
- Using UNO artwork, card designs, or other third-party brand assets. The requested product name is a working name; public naming review remains a release task.

## 4. Behavioral requirements

### 4.1 Setup and modes

MVP: a local CLI with a browser-based local review screen. The server binds to loopback only, validates origin, and requires a per-session token for mutations. No model or Gmail keys are exposed to the browser.

Setup collects mailbox identity, business name, canonical domain, approved description, supported claims/evidence, CTA URL, signature, tone, exclusions, and model configuration. A user can provide a manual profile or optionally connect BrandVault. Preview is the default; enabling automatic sending is a separate action.

Both modes ship in the first release and use the same classification, reservation, sending, recovery, organization, and response-monitoring pipeline:

- **Review mode:** approve exact messages individually or as a batch before sending.
- **Autopilot:** approve a versioned policy once; the local worker scans and sends eligible initial pitches without per-message approval. Ambiguous candidates go to Review. This is an MVP feature, not a later phase.

### 4.1.1 Autopilot policy and execution

Enabling autopilot presents and records the mailbox, eligible categories, inbox/date scope, approved profile snapshot, template, permitted personalization fields, CTA, signature, archive setting, sending hours/timezone, daily/run caps, and polling interval. Show representative generated messages before activation. Explicit policy activation authorizes matching sends; do not ask for approval on every qualifying message.

Default: poll every 15 minutes while the local worker is running; process new inbound messages since activation; unsolicited sales only; 25 accepted or unresolved submissions per local calendar day and 10 per polling run. Historical inbox backfill is a separate explicit scope choice. Store a stable cursor and process overlapping windows to tolerate delayed indexing; deduplication, rather than timestamps alone, prevents repeat sends. Sleeping/offline devices resume on launch. Do not imply that the agent runs when its process is stopped.

Autopilot requires a supported classifier with a versioned, evaluated high-confidence threshold, unambiguous company identity, one valid reply address, and all deterministic exclusions passing. Model self-reported confidence alone is insufficient: before enabling a classifier version, pass the labeled eligibility fixtures with zero sends to protected classes. This is a release acceptance condition, not proof that future errors are impossible. If no classifier is configured, users can still review template-generated pitches, but cannot enable automatic classification/sending.

Use an approved template with bounded substitutions (recipient company/name and an evidence-backed outreach category); freeform model-generated claims or new URLs require review. Immediately before sending, re-read the thread and recheck policy, exclusions, suppression, reservation, mailbox identity, caps, and substantive replies. Capture the exact outgoing content and a policy-authorization receipt in the same durable workflow used for manual approvals.

Changing profile facts, template, CTA, eligibility, historical scope, archive behavior, or increasing caps invalidates the active policy and pauses queued automatic sends until the new policy is enabled. Lower caps and pause/suppression changes apply immediately. Refreshing BrandVault never silently changes an active policy. A candidate with a stale authorization receipt must be evaluated again.

An unknown send, failed credential refresh, or revoked authorization pauses new automatic submissions for that mailbox. Unresolved submissions consume budget until reconciled. Pause state persists across restarts; reconnecting Google does not itself resume autopilot. A manual resume rechecks the approved policy and pending work. There are no automatic follow-up sequences or automatic replies to human responses.

Scan scope defaults to the last seven days of the inbox. The user can choose another date range or entire inbox history. Show the scope and candidate count before drafting; do not infer entire-history consent from connecting Gmail.

### 4.2 Candidate classification

- Page through all results in the selected scope; Gmail categories are hints, not eligibility decisions.
- Distinguish unsolicited sales, promotional newsletters, personal conversations, transactional/security messages, job applications, support conversations, media requests, and automated notifications.
- Default eligibility is unsolicited commercial sales outreach. Promotional newsletters are a separate opt-in category.
- Exclude sent, draft, spam, trash, self-sent, already processed, suppressed, automated-loop, and account/security messages before generation.
- Existing substantive two-way conversations and ambiguous relationships require review and are never autopilot candidates.
- Read the relevant thread and show the evidence supporting the classification. Never claim that an email was AI-written merely from its style.
- Resolve the sender's company using signature, message context, and domain together. Store evidence and confidence. Ambiguous company identity or multiple possible brands blocks autopilot.
- Do not download attachments, load remote images, or follow email links during classification.

### 4.3 Recipient selection and brand deduplication

- Parse authoritative RFC Reply-To, falling back to From. Reply to the sender only; exclude original To, CC, and BCC recipients.
- Multiple reply recipients, invalid addresses, no-reply mailboxes, and suspicious identity mismatches require review or exclusion.
- Recognize relay addresses from newsletter/event platforms without treating the platform as the sender's brand.
- Normalize domains with a maintained public-suffix implementation. A registrable domain is evidence, not a universal brand ID.
- Let users merge aliases or split brands. Re-evaluate affected unsent candidates after a change.
- Store a durable mailbox/brand reservation before sending. Two processes cannot reserve the same brand concurrently. Suppression persists across scans and campaigns; a new campaign does not reset it.
- A decline, opt-out, or bounce suppresses further automatic pitches to that address. Brand-level opt-outs suppress the resolved brand and known aliases.

### 4.4 Pitch creation and review

Generate a short, friendly pitch with an optional playful opener, one supported value proposition, one CTA, and the user's signature. The default is warm and lightly humorous. No fabricated familiarity, fake research, guarantees, invented customer outcomes, or implied endorsement.

Review shows: source email and thread link, recipient, resolved company and evidence, eligibility reason, exact subject/body, source profile version, and proposed label/archive actions. Users can edit, exclude, suppress, or approve selected entries.

In review mode, approval binds a hash of the recipient, content, source facts, source message, and organization actions. In autopilot, the policy authorization binds its approved snapshot/template/actions and each matching candidate receives an auditable authorization receipt. Material edits invalidate the applicable approval or policy. BrandVault refreshes produce new drafts; they do not silently rewrite approved mail.

Use a deterministic template when no model is configured. A model can classify and tailor copy through a provider interface; it never receives mailbox credentials or direct send authority. Selecting a remote model explicitly discloses that relevant message content will be sent to that provider.

### 4.5 Sending and recovery

- Preserve threading with the Gmail thread ID, a compatible subject, and valid In-Reply-To/References headers. Build MIME with a maintained library; do not concatenate raw headers.
- Send multipart plain text and escaped HTML. No attachments or tracking pixels in MVP.
- Default maximum: 10 sends per run and 25 per mailbox per day, with at least five seconds between submissions. These are conservative product defaults, not claims about Gmail limits. Users can lower them; raising them requires explicit configuration.
- Store the exact MIME bytes, stable generated RFC Message-ID, authorization receipt hash (manual approval or autopilot policy), and send attempt before submission.
- A successful Gmail response records the provider message ID and `accepted_by_gmail`; it does not imply delivery.
- Pre-submission failures can be retried with bounded backoff. A timeout, crash during submission, or ambiguous provider response enters `send_unknown`. Reconcile Sent mail using the stable Message-ID and supporting metadata before any retry. No automatic resend while uncertainty remains.
- Invalid threading metadata becomes a review item. The user may choose another message in the conversation or approve a separate email; never silently change to a new conversation.
- Respect quota responses and stop the run on revoked authorization. A pause command stops new submissions immediately; an in-flight request can still complete.

### 4.6 Organization

After a confirmed accepted send, apply the `uno reverse` label to the source conversation and outgoing reply. Archive only when the user selected that option, which is shown in the review plan.

Before removing INBOX, re-read the conversation. Remove INBOX only from the message set captured by the manual approval or autopilot authorization receipt; do not archive newly arrived human replies or unrelated messages that appeared afterward. Label/archive failures are retried independently and never trigger a resend.

Persist previous label membership so organization changes can be undone per run. Never trash or delete messages. New substantive replies stay in the inbox and also receive the campaign label when detected; the agent does not create a blanket Gmail filter that hides future responses.

### 4.7 Reply monitoring

An explicit `check-replies` command polls known conversations and relevant delivery notifications. An optional local monitor polls every 15 minutes while running. Store provider timestamps in UTC and display the user's timezone; compare incoming timestamps against the actual outgoing send.

Classify results as interested, declined/opted-out, substantive-other, automated acknowledgement, out-of-office, unmonitored mailbox, bounce, or uncertain. Detect bounces and acknowledgements that arrive in separate threads using RFC delivery metadata where available. Uncertain correlation stays uncertain.

Show quoted evidence and Gmail links. Never count auto-replies as interest or claim adoption from a positive email. Do not send any response automatically. Notify only on new substantive replies, delivery failures, or required user action; unchanged polls stay quiet.

### 4.8 Optional BrandVault integration and adoption

Two independent choices:

1. **Use my BrandVault:** retrieve the user's brand identity and published facts to write a pitch for their business.
2. **Invite recipients to BrandVault:** add an editable, explicitly enabled invitation for the recipient to claim their own free BrandVault.

Neither is required. The second is off by default, even when BrandVault is connected. The Optimly-owned demo can explicitly enable both.

The adapter invokes only allowlisted read operations through the existing keyed/MCP gateway. It does not expose publish, claim, or recommendation mutation tools to the model. Never send recipient email content to Optimly for profile retrieval.

Existing `get_vault` returns sections with publication states and can fall back to an unpublished draft. The adapter must verify an actual published version and select only published sections; discard draft/private content, competitors, and disambiguation unless separately known to be published. Missing or ambiguous publication metadata blocks import. If the existing surface cannot establish this reliably, add a narrowly scoped published-profile read surface before enabling the connector.

Show imported facts and source version for approval. If BrandVault is unavailable, retain the reviewed snapshot with a visible stale status or use a separately approved manual profile. Do not silently substitute new facts or default to promoting Optimly.

The invitation links to the canonical Brand Index entry/claim action when verified, otherwise the verified Brand Index homepage. Never invent a personalized claim URL. Explain domain ownership verification without implying the recipient's brand is already available or unclaimed.

An optional editable attribution footer can mention the open-source agent; it is off by default. No hidden affiliate links or required Optimly branding.

## 5. Technical approach and architecture

Proposed implementation: Python application, SQLite durable state, a loopback review UI, and adapters for Gmail, a model provider, and BrandVault. Use official Gmail client libraries and a maintained MIME parser. Exact external packages must be verified on their registries before addition (`verify-new-dependencies`). Package versions are implementation decisions, not guessed in this spec.

Modules:

- `mailbox`: OAuth, paginated queries, thread/header normalization, MIME submission, labels, and Sent reconciliation.
- `eligibility`: deterministic exclusions, structured classifier output, sender identity, and policy decisions.
- `profiles`: manual profile and read-only BrandVault snapshots.
- `composer`: constrained template/model generation and claim provenance.
- `workflow`: approvals, durable reservations, rate limits, send recovery, organization, and suppression.
- `replies`: incremental response/bounce discovery, classification, and local digest.
- `cli` / `review`: command surface and exact-action review.

The workflow is explicit application code. Model output is validated data, not executable instructions. Email bodies, signatures, retrieved profiles, and model outputs cannot change policy, recipients, permissions, or tool configuration. Escape HTML and enforce size limits; do not render incoming HTML directly.

Relevant existing Optimly architecture elements:

- `keyed-api-mcp-gateway`: optional read integration boundary; respect existing brand authorization and rate limits.
- `oauth-provider-logic` and `connections-mcp-module`: existing Optimly authorization/connection experience; verify supported read scopes before choosing a credential mechanism.
- `public-api-surface` and `optimly-index-server`: canonical public brand and claim discovery surfaces.
- `onboarding-pipeline`: remains the owner of domain verification and claiming; the email agent only links to it.
- `optimly-postgresql-db`, `optimly-task-worker`, and `work-queue-engine`: no changes for MVP. Local mail processing must not become a production platform job.

Gjalla architecture cache was marked stale during authoring; the MCP draft fallback above was verified directly in source. Refresh architecture state during implementation planning.

Keep this spec in the monorepo. Proposed distributable location is an isolated `tools/uno-reverse-email-agent/` package, with no imports from private Optimly backend code. A separate public repository or automated export is a later explicit release decision. This respects `monorepo-only` while preparing an independently usable open-source tool. Use Apache-2.0 for the isolated package, subject to repository/license compatibility review; do not relicense the parent repository.

### 5.1 Google / Gmail authentication — implementation decision

Use direct Gmail API authorization with a **Google OAuth Desktop app client**, Authorization Code + PKCE (S256), the system browser, and a short-lived loopback callback. No Gmail passwords, app passwords, service accounts, domain-wide delegation, or dependency on a user's Codex/ChatGPT Gmail connector. A Google sign-in identity alone does not grant mailbox access. Optimly authentication is a separate optional connection.

Two credential distribution paths use the same adapter:

| Path | Intended users | Setup |
| --- | --- | --- |
| Bring your own Google OAuth client | Initial developer/personal pilot and forks | User creates a Google project/Desktop client and imports its downloaded installed-app JSON locally |
| Maintainer-owned OAuth client | Public supported release | Maintainers configure and verify a dedicated Uno Reverse Email Agent Google project; users click Connect Gmail without creating a project |

Desktop applications are public OAuth clients: their client configuration cannot be treated as a confidential service credential. User refresh/access tokens are secrets. Do not ship a web-server client secret as a substitute for a Desktop client. Use Google-supported libraries for the flow. [Desktop OAuth reference](https://developers.google.com/identity/protocols/oauth2/native-app).

#### 5.1.1 Concrete Google Cloud setup for the pilot

The setup guide must walk through:

1. Create/select a dedicated Google Cloud project and enable the Gmail API.
2. Configure Google Auth Platform branding with application name, support email, and developer contact. Use External audience for Gmail/general users. Internal is an option only for a project belonging to a Workspace organization and its organization users.
3. For an External testing app, add the pilot mailbox addresses as test users. Configure the Gmail scope in Data Access.
4. Create an OAuth client with application type **Desktop app**, download its JSON, and import it using `ure connect gmail --client-secrets /absolute/path/client.json`. Reject JSON for the wrong client type; validate expected Google endpoint origins and never follow arbitrary endpoints supplied by the file.
5. Select preview-only or full Gmail functionality, complete browser consent, and verify that the mailbox displayed locally matches the intended account. Keep downloaded configuration out of Git and local review exports.

No production Optimly credentials or Google infrastructure changes are required to write this integration. Creating the actual OAuth project/client is a separate implementation/setup action; this spec does not claim credentials have already been created.

#### 5.1.2 Scopes and consent behavior

| Connection capability | Requested Gmail scope | Local behavior |
| --- | --- | --- |
| Read-only preview | `https://www.googleapis.com/auth/gmail.readonly` | Scan and generate local previews; no Gmail drafts, sends, labels, or archive |
| Full workflow, either mode | `https://www.googleapis.com/auth/gmail.modify` | Read, draft, send, label, and archive through the same connection |

Do not request full `https://mail.google.com/` access. Separate `gmail.send` and `gmail.labels` grants are unnecessary when using `gmail.modify`. Google permissions are broader than the review/autopilot distinction: both modes use the same full scope; application policy controls when sending is authorized. Both listed scopes are restricted. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).

Installed apps do not support Google's incremental authorization mechanism. Upgrading a preview connection therefore starts a fresh explicit authorization request for the complete required scope set, verifies the returned grant, and replaces the connection only after success. Do not implement this as `include_granted_scopes`-based incremental consent. Declining an upgrade leaves preview usable. A scope downgrade similarly requires an appropriate fresh grant; explain that revoking an existing grant can affect tokens for the same app. [Installed-app scope behavior](https://developers.google.com/identity/protocols/oauth2/native-app#identify-access-scopes).

#### 5.1.3 Runtime connection flow

1. `connect gmail` checks credential-store availability, creates an unpredictable state value and PKCE verifier, and opens a callback listener bound only to `127.0.0.1` on an OS-assigned port. The callback path and actual port are fixed for that attempt.
2. Open Google's authorization page in the system browser, using the selected Desktop client, exact callback URI, selected scopes, and account selection. Request offline access through the supported library flow. Do not use an embedded webview or deprecated out-of-band copy/paste-code flow.
3. Accept one matching callback, validate state and OAuth error fields, exchange the code with its PKCE verifier, and close the listener. Proposed timeout: five minutes. Unmatched callbacks cannot consume the valid attempt. Never log the code, verifier, tokens, or callback query.
4. Verify returned scopes, call Gmail `users.getProfile` with `userId=me`, and display the authorized email. Connecting a different mailbox must not attach old campaigns/reservations to it. Persist refresh credentials only after validation.
5. Store refresh credentials in the OS credential store (Keychain on macOS; corresponding supported stores on Windows/Linux), with account/client identifiers as the lookup key. Access tokens remain in memory. The local browser receives connection status, not tokens. Require reconnect if no refresh token is available and none is already stored; do not repeatedly force consent on normal starts.
6. Refresh expired access tokens on demand under a per-connection lock. Preserve an existing refresh token when a successful response omits a replacement. Back off transient network failures; `invalid_grant`, scope loss, and admin blocks require clear reauthentication and suspend new sends. Do not turn auth failures into retries of unknown mail submissions.
7. `ure disconnect gmail` first pauses processing, attempts Google token revocation, deletes local credentials, and marks the connection disconnected. If offline, local disconnection still succeeds and the UI gives Google's account-permissions link to complete revocation. Retain non-secret send/suppression history unless the user explicitly purges it.

#### 5.1.4 Autopilot lifetime and diagnostics

Offline refresh access enables unattended operation while the local worker is running; it does not guarantee perpetual authorization. External apps in Testing with Gmail scopes receive refresh tokens that expire after seven days. Show the testing-mode limitation in setup documentation and reconnect diagnostics; do not describe it as a Gmail bug. Moving a project to Production is distinct from Google verification and is not an assurance of unrestricted public access. [Google token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).

`ure auth status` shows connected email, client source, granted capabilities, last successful refresh, worker state, and any required action, without printing tokens. Support actionable errors for denied consent, missing scope, wrong account/client type, unavailable credential store, callback timeout/port failure, expired/revoked grant, and Workspace administrator restrictions. Credentials cannot silently resume a user-paused policy.

#### 5.1.5 Public release and model-provider data handling

The maintainer-owned project needs verified branding/domains and scope justification, a public homepage/privacy policy, user-data deletion instructions, accurate consent text, and a working demonstration for Google's review. Confirm that the product's email-productivity use case and data handling qualify under Google's permitted-use policies before broad distribution. Personal/development/internal exceptions are specific deployment paths, not a way to bypass review for public users.

Google requires restricted-scope verification unless an exception applies; server access/transmission of restricted data can also require a security assessment. Our local-first design removes an Optimly mailbox backend, but forwarding email text to a remote model is still a third-party data flow and must be included in the review and assessment determination. The public release must document each supported provider's processing/retention/training terms and Google policy compatibility. Local/template processing remains available; remote processing is explicit opt-in and unavailable in the maintained public build until its data flow is cleared. Do not promise that sending only excerpts automatically removes these obligations. [Restricted-scope requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

Forks use their own OAuth projects, branding, and privacy disclosures. Never tell fork maintainers to reuse the official app identity. Public setup should not require users to disable account protections or paste tokens into chat.

### 5.2 Local data handling

Never persist refresh tokens or API keys in SQLite, generated review files, logs, or the repository. Fail clearly if secure credential storage is unavailable.

Default storage contains IDs, decisions, approved outgoing content, profile snapshots, timestamps, and action receipts. Incoming bodies are transient unless the user opts into caching. Local files use restrictive permissions. Provide data export, local purge, and credential disconnect. Explain that SQLite records are not encrypted by default and rely on device protection. No mailbox telemetry, remote logs, or training use.

## 6. Data model

No Optimly database migration is required. Local schema:

| Entity | Essential fields |
| --- | --- |
| Mailbox | account ID, address, timezone, OAuth credential reference, scan/reply cursors |
| Campaign | mailbox, scope, category policy, tone, limits, archive setting, adoption setting |
| ProfileSnapshot | manual/BrandVault source, brand ID/domain, version, publication metadata, approved facts, hash |
| BrandIdentity | canonical ID, display name, domain/relay aliases, evidence, user corrections |
| Candidate | source message/thread, brand, Reply-To, classification, reason, exclusions |
| Approval | candidate, exact recipient/content/actions hash, approver, time, policy version |
| AutopilotPolicy | mailbox, enabled/paused state, scope, snapshot/template hashes, allowed substitutions, thresholds, schedule/timezone, caps, version, activated by/at |
| AuthorizationReceipt | candidate, manual approval or policy version, eligibility evidence, exact outgoing/action hash, authorized at |
| BrandReservation | unique mailbox + brand, reserved/sending/sent/unknown status |
| SendAttempt | approval, MIME/Message-ID, attempt state, provider ID, error, timestamps |
| OrganizationAction | exact message IDs, prior labels, intended changes, completion/error |
| ReplyEvent | incoming message, correlated send, category, evidence, first-seen time |
| Suppression | mailbox, address/brand scope, reason, provenance, time |

Candidate states: discovered → excluded / needs_review / ready → authorized (manual approval or active autopilot policy) → reserved → sending → accepted_by_gmail / failed_before_send / send_unknown. Organization and reply events have independent states. Rejected/expired approvals and inactive policy versions cannot send. An unresolved send reservation remains held; deleting a run does not silently clear suppression or send history. Mailbox records additionally hold credential reference, client source, granted scopes, connection health, and refresh status; never the token itself.

## 7. API and user surfaces

Proposed commands (the `ure` executable name must be checked before publishing):

```text
ure init
ure connect gmail                  # browser OAuth, full capability by default
ure connect gmail --preview-only
ure connect gmail --client-secrets /absolute/path/client.json
ure auth status
ure profile edit
ure connect brandvault
ure scan --since <date>             # or explicit --all-inbox
ure review <run-id>
ure send <run-id>                   # sends only approved entries
ure status <run-id>
ure check-replies
ure monitor start                  # reply monitoring, not automatic pitching
ure autopilot enable               # MVP: review and activate explicit policy
ure autopilot status
ure autopilot pause
ure autopilot resume
ure worker start                   # runs enabled policies and reply checks locally
ure pause
ure undo-organization <run-id>
ure disconnect gmail
ure data export | purge
```

The local UI has Setup, Review, Autopilot, Activity, and Replies views. Autopilot shows the active policy, current caps, pending review items, worker/connection health, and pause/resume controls. Counters distinguish scanned, eligible, excluded, manually approved, policy-authorized, accepted, unknown, bounced, substantive replies, and interested replies. No remote REST service or public API is needed for MVP.

Expose testable internal interfaces: `MailboxAdapter`, `ProfileSource`, and `ModelProvider`. The BrandVault adapter returns a normalized published profile snapshot; it never returns arbitrary tool access. Initial support is one connected mailbox per local workspace.

## 8. Testing strategy and acceptance criteria

Use synthetic or consented, redacted fixtures. Never commit this run's real emails or customer information.

Required behavioral coverage:

1. A mixed mailbox fixture selects sales outreach, excludes security/personal/job/support messages, and gates newsletters behind opt-in.
2. Sender signature resolves the actual company when the sending domain is a sales alias; uncertainty requires review.
3. Header parsing honors Reply-To, safely handles encoded/malformed headers, avoids CC/reply-all, and excludes no-reply targets.
4. Pagination scans the full requested scope. Repeated scans, concurrent workers, and different campaigns cannot send a second pitch to the same brand.
5. Editing recipient/body/profile/actions invalidates approval. Prompt injection in emails or profile content cannot change recipients or trigger actions.
6. MIME fixtures validate compatible reply subjects, References/In-Reply-To, escaped HTML, Unicode, and one clean reply prefix.
7. Crash tests before submission, during submission, and after acceptance verify durable state, unknown-send reconciliation, and no blind resend. Do not claim exactly-once guarantees.
8. Label/archive failure retries organization only. A new human reply arriving between approval and archive remains in the inbox. Undo restores only this run's label changes.
9. Separate-thread bounces, acknowledgements, out-of-office, interest, and declines are classified correctly and deduplicated across polling runs. Quoted old text cannot count as a new reply.
10. BrandVault draft fallback, private sections, absent publication metadata, revocation, and unavailable service never leak unpublished facts. Manual mode remains complete with no Optimly credentials.
11. Daily limits, pause, revoked access, suppression, and opt-out survive restarts. Pausing prevents additional submissions after the in-flight operation.
12. Secrets do not appear in logs, browser payloads, SQLite, exports, or error traces; incoming HTML and forged local cross-origin requests cannot execute actions.
13. Review mode never submits unapproved mail. Autopilot submits qualifying initial pitches without per-message approval, routes ambiguous cases to Review, respects the activation watermark and explicit backfill scope, and records the matching policy version for every send.
14. Policy edits invalidate queued authorization receipts; lower caps, pause, new substantive replies, and suppressions take effect before the next submission. Concurrent polling and local-day budget rollover do not exceed caps or duplicate sends. Restart preserves pause/cursors; an offline device catches up only within approved scope.
15. Desktop OAuth tests cover PKCE/state validation, callback mismatch/replay/timeout, scope verification, wrong mailbox, denied upgrade, missing refresh token, secure-store failure, concurrent refresh, token revocation, and failed network revocation during disconnect. Use a simulated authorization server for protocol failures and the real Gmail client against dedicated accounts for acceptance.
16. A fresh preview-only grant cannot mutate Gmail. Upgrading uses fresh full-scope consent, not installed-app incremental authorization. Autopilot continues across access-token refresh, stops on `invalid_grant` or lost scope, and requires explicit resume after reconnect. Test-mode seven-day expiry is documented and exercised through an expired-grant fixture.

Run an end-to-end Gmail acceptance test with dedicated consenting test accounts: connect with browser OAuth, approve a small review-mode batch, enable a tightly scoped autopilot policy, receive qualifying and excluded outreach, send threaded mail in both modes, label/archive, refresh authorization, restart, receive replies and a controlled failure, and verify counts and inbox behavior. Live sends are an explicit test step, never part of routine CI. A deterministic fake mailbox tests state-machine transitions; MIME and parsing tests exercise real serialization/parsing logic.

MVP ships only when these acceptance cases pass, installation works from a clean environment, preview makes no mailbox mutations, and documentation explains credentials, model data flow, limits, recovery, and uninstallation.

## 9. Dependencies, rollout, and success measures

### Phase 1 — MVP with review mode and autopilot

Manual profile, direct Gmail Desktop OAuth (bring-your-own client and maintainer-client support), classification, review/approval, policy-authorized autopilot with local scheduling, bounded generation, durable sending, label/archive with undo, quiet reply monitoring, and optional published-only BrandVault import/invitation. Both modes are required MVP acceptance paths. Ship template-only review mode and a supported classifier/model adapter; unattended classification requires the evaluated classifier configuration described above. Prioritize a local classifier path for public distribution; any remote-provider path must meet section 5.1.5 before being enabled in that release.

### Phase 2 — expanded integrations and ergonomics

Better alias resolution, additional model adapters, installation/service-manager helpers, and expanded review tools. These improve an already working autopilot; they are not prerequisites for shipping it. Approval of this spec does not authorize mail sends from an implementation or test account.

### Phase 3 — distribution

Public repository/package release, contributor guide, redacted demo, OAuth production verification, supported packaging, and a decision on optional hosted onboarding. Keep functional use independent of Optimly.

Prerequisites: provision the pilot Desktop OAuth client using section 5.1.1; complete the public OAuth/data-flow review before broad maintainer-client distribution; verify supported Optimly read scopes/publication metadata; verify package names and licenses; review the working product name before public launch. No production Optimly infrastructure access is required to write or test the local core.

Local success measures: time to first approved send; false-positive exclusions/corrections; duplicate sends (target zero); unresolved sends; bounce rate; substantive and interested replies per accepted send. Distinguish local engagement from confirmed BrandVault adoption. Optional adoption measurement requires user consent and first-party confirmation from Optimly; no mailbox addresses or email bodies are sent as analytics. Set numerical conversion targets after a pilot, not from the 133-email anecdote.

Rules constraining implementation: `stay-in-scope`, `dont-over-engineer`, `small-single-responsibility-modules-no-duplication`, `ship-meaningful-tests-with-behavior-changes`, `verify-new-dependencies`, `monorepo-only`, and `worktree-per-unit-of-work`. Implementation work must use an isolated worktree and branch. This documentation-only spec does not create a branch, commit, public repository, or deployed service.

## 10. Rollback and open decisions

Pause the local worker, cancel unsent queued actions, revoke/disconnect credentials, and optionally undo recorded organization changes. Retain reservations for accepted or unknown submissions until reconciled. Sent emails cannot be reliably recalled; rollback never promises to unsend them. BrandVault is read-only, so no platform data rollback is required.

Implementation defaults are the isolated package location, direct Google Desktop OAuth, and both operating modes specified above. Select and verify the initial classifier/model adapter during dependency evaluation; confirm how the MCP surface proves a published snapshot and exposes appropriately limited read access. Before public release: complete naming/license review, public repo ownership/export approach, and the Google OAuth/data-flow requirements in section 5.1.5. These are release tasks, not reasons to defer MVP autopilot.

## References

- Existing MCP surface: `backend/optimly/api/mcp_server.py`, particularly `get_brand`, `get_vault`, and `get_vault_version`.
- [Gmail OAuth scopes and verification](https://developers.google.com/workspace/gmail/api/auth/scopes).
- [Google Desktop OAuth, PKCE, loopback redirects, and installed-app scope behavior](https://developers.google.com/identity/protocols/oauth2/native-app).
- [Google refresh-token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
- [Google restricted-scope verification and security assessments](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).
- [Gmail MIME creation and sending](https://developers.google.com/workspace/gmail/api/guides/sending).
- [Gmail thread and reply requirements](https://developers.google.com/workspace/gmail/api/guides/threads).
- [BrandVault product and publication model](https://optimly.ai/product).
