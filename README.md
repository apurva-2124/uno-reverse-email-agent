# Uno Reverse

**An agent skill that turns incoming sales outreach into a pitch for your business.**

Uses your existing agent and its model access; no standalone app, dashboard or local web server. Talk to your agent, connect your existing email tools, preview a pitch and optionally enable scheduled autopilot.

## Start here

In Codex, paste this install prompt:

```text
Use $skill-installer to install apurva-2124/uno-reverse-email-agent,
path .agents/skills/uno-reverse, ref setup/proposal.
```

The explicit ref matters: this repository's default branch is `setup/proposal`, not `main`. Start your next turn after installation; if the skill is missing, restart Codex. The `$` syntax mentions a skill; it is not a price or a shell command.

Prefer a local checkout? With Git installed:

```sh
git clone --branch setup/proposal https://github.com/apurva-2124/uno-reverse-email-agent.git
cd uno-reverse-email-agent
```

Open that folder in Codex; it can discover `.agents/skills/uno-reverse` as a repository skill. Keep the checkout available for future runs. See the [first-run guide](docs/getting-started.md) for requirements, Gmail setup and scheduling, or [troubleshooting](docs/troubleshooting.md) if you get stuck.

Then ask:

> Use $uno-reverse. My business is [name] and we help [audience] with [problem]. Show me a reverse pitch before setting up autopilot.

Your agent will:

1. Show a useful sample without signup or a Gmail write.
2. Collect your approved business facts, CTA and signature.
3. Offer local setup, an existing BrandVault, or optional free BrandVault signup.
4. Separately ask whether you want an optional BrandVault invitation in your outgoing pitches. It starts off.
5. Check email-tool capabilities and preview the scope, template, archive choice, schedule and limits.
6. Activate and schedule only after you explicitly approve the sending policy.

The skill uses the host's connected email tools. It does not include an email connection or grant mailbox access. If sending or scheduling is unavailable, the agent explains what is missing and stays in preview. Installing the skill alone never sends emails or starts an automation.

## What works today

Initial reverse pitches, reply monitoring and decline/bounce suppression are described by the skill. **Automatic follow-up messages, replies to interested people and meeting scheduling are not implemented.** The agent surfaces meaningful replies for you to handle.

| Environment | Validation / requirements |
| --- | --- |
| Codex local skill | Public download installation and Python helper tested; requires Python 3.11+ for durable state. |
| Gmail in your agent host | Requires connected read, threaded send, Sent inspection and label tools. Live end-to-end sending has not been tested. |
| Scheduled autopilot | Requires host scheduling, suitable permissions and the same persistent ledger on every run. No live scheduled send test yet. |
| Other skill-compatible agents | May use the skill folder, but compatibility is untested; verify tools and local script execution first. |

## Optional BrandVault

Built by Optimly. Use the skill without an account, or save approved business facts in [BrandVault](https://optimly.ai/product) for reuse. Signup is an explicit choice, and publishing is a separate user-controlled action. Connecting a BrandVault never turns on recipient invitations.

The optional invitation is shown verbatim before activation. There are no hidden promotions, referral links, tracking pixels, compulsory signup, or mailbox-content uploads to Optimly. Published profile imports must prove publication; draft/private facts are excluded. Local setup remains available if the service is unavailable.

## What is in the repository

```text
.agents/skills/uno-reverse/
  SKILL.md                    Agent workflow and boundaries
  agents/openai.yaml          Skill discovery metadata
  references/setup.md         Chat setup and optional BrandVault flow
  references/autopilot.md     Activation, scheduling and recovery
  references/tools.md         Email/Optimly capability checks
  references/evaluation.md    Dry-run behavioral scenarios
  scripts/ledger.py           Local policy, dedup and send-history helper
tests/test_ledger.py           Deterministic helper tests
```

The helper requires Python 3.11+ and only the standard library. It stores SQLite outside the repo, with private local file permissions. It does not call any network API. The agent handles judgment and tools; the helper guards durable state. Automated sending still depends on the host model, connector correctness, permissions and the user's approved policy.

A scheduled task wakes the agent up; the skill itself is not a background process. With local state, the host and machine must remain available and all runs must share the same absolute ledger directory. Local ledger storage does not imply local-only email processing by the host model.

## Development and validation

```sh
python3 -m unittest discover -s tests -v
python3 .agents/skills/uno-reverse/scripts/ledger.py --help
```

Tests do not send mail or access Gmail/Optimly. Unknown send outcomes retain their brand reservation and pause new sends; they are never automatically retried. A cleared search result is not proof that a send failed. The helper is an agent aid, not an independent security boundary against a host that ignores its instructions.

Read [the current design](docs/skill-design.md) for the architecture and limitations. The [original proposal](docs/proposal.md) is historical and is superseded wherever it describes a standalone app, custom Gmail OAuth, a browser UI or a bundled classifier. The earlier app prototype was withdrawn at the owner's request.

## License

[MIT](LICENSE). The historical proposal’s pending Apache-2.0 suggestion is superseded by this license.
