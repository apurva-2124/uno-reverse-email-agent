# First run

## Requirements and installation

Use an agent host that can load the skill and execute local Python 3.11+. Your host supplies model access; its own pricing and usage limits still apply. Gmail and scheduling are only needed when you choose to enable sending. No Optimly account or separate model API key is required by this skill.

Follow the [README installation instructions](../README.md#start-here). Install the whole skill folder, including `references`, `scripts` and `agents`. See [official skill documentation](https://learn.chatgpt.com/docs/build-skills) for Codex discovery and invocation behavior.

## 1. Try a sample without connecting email

Paste this into your agent:

```text
Use $uno-reverse for a chat-only preview. My fictional business is Acme
Analytics. We help small retailers understand inventory trends. My CTA is
https://example.com/demo and my signature is Alex, Acme Analytics.
Example incoming email: "Hi Alex, I'm Sam at Example Sales. Could we book
15 minutes to show you our sales reporting product?"
Show a sample reverse pitch using only these facts. Do not connect or read
my mailbox, create a Gmail draft, send anything or activate autopilot.
```

Expect a sample reply in chat and a request to confirm your business facts. The example domain and fictional business are placeholders; replace them before real use. A preview is not activation and is not a saved Gmail draft.

## 2. Confirm your business profile

Provide your business name, approved description, real CTA URL and signature. Choose local profile storage, import from an existing published BrandVault, or optional signup. You can use the complete core workflow with local facts.

Recipient invitations are a separate choice and start off. If you enable one, review its exact text before activation. Signup does not enable invitations or sending.

## 3. Connect and check Gmail

Use your host's connected-app or plugin connection flow for Gmail and select the intended mailbox. If you cannot find it, ask the agent which Gmail integration is available in that host. Do not paste passwords, tokens or OAuth secrets into the chat. Connecting in one host does not guarantee tools exist in another, including a separate CLI session.

Ask:

```text
Check Uno Reverse's Gmail capabilities and tell me which mailbox is connected.
Do not send or create drafts. Explain any missing capabilities before setup.
```

The agent needs authoritative sender headers, complete threads, paginated search, exact single-recipient threaded sending, Sent inspection and labeling. Archive stays off unless message-level archive is supported. See the [capability checklist](../.agents/skills/uno-reverse/references/tools.md).

Mailbox contents may be processed by the host model and connector under their data controls. The local ledger does not make that processing local-only. Host permissions still apply after you approve a skill policy; unavailable unattended sending cannot be enabled by the skill itself.

## 4. Review candidates and policy

Authorize a read-only preview of a bounded inbox sample, such as the last seven days. Expect eligible examples, exclusions and ambiguous items left for review. No messages should be sent during this step.

Ask the agent to show the policy: mailbox, business facts, exact template, invitation choice, archive setting, timezone/hours, limits, starting scope and schedule. Defaults are 25 attempts/day, 10/run, at least five seconds apart, a 15-minute cadence, and only new messages since activation. Invitation and archive default off. Historical backfill requires a separate choice.

The agent must choose and report one absolute state directory outside Git, such as `~/.local/share/uno-reverse/<mailbox-key>` expanded to an absolute path. All future runs must share it. Review the policy hash and activate only when the displayed policy matches your intent.

## 5. Test one run, then schedule

Explicitly approving activation authorizes initial pitches within that policy. It does not authorize follow-up sequences, conversations with interested respondents or booking meetings. Review one authorized run before asking the agent to schedule it.

```text
Schedule the approved Uno Reverse policy every 15 minutes, using the same
absolute ledger directory. Stay quiet when nothing meaningful changes.
Notify me about substantive replies, delivery failures or required action.
Do not automatically follow up or schedule meetings.
```

Expect a confirmed schedule and shared state location. If the host cannot schedule or send unattended, remain in on-demand mode. A skill is not a background service. Local scheduled tasks require the computer on and app running; cloud execution needs equivalent persistent storage and tools and is not bundled here. See [official scheduled-task documentation](https://learn.chatgpt.com/docs/scheduled-tasks) and the [agent run procedure](../.agents/skills/uno-reverse/references/autopilot.md).

## 6. Pause, inspect or change settings

Ask `Pause Uno Reverse sending and pause its scheduled task.` Expect both the persistent ledger pause and scheduler pause to be confirmed. A send already submitted may still finish.

Ask `Show Uno Reverse status and any unresolved attempts` to inspect the ledger. Unknown delivery results pause new sends and retain reservations; they must never be retried automatically. Changing your profile or policy requires a fresh preview and activation. Do not delete state to clear a pause or deduplication.

## Validation status

The public download installer and local helper have been exercised without mailbox access. The helper test suite uses synthetic inputs. Live Gmail sending, model classification accuracy and unattended scheduled sending are not yet end-to-end validated. Validate the intended host and connector on your own approved sample before activation.
