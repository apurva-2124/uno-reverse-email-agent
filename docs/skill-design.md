# Skill architecture

Uno Reverse is a self-contained agent skill with instructions, supporting references and a local Python helper. The host provides connected tools and execution.

## Responsibilities

- **Host agent:** chat interaction, classification, email tools, permissions, scheduling and meaningful notifications. No separate model adapter or custom Gmail OAuth app.
- **Skill:** scoped instructions, approved pitch template, optional BrandVault onboarding and recipient invitation, tool capability checks, explicit policy activation and recovery procedures.
- **Local helper:** immutable policy snapshots, exact rendered plans, permanent brand/source reservations, suppression, run locks, caps and send/reply history. No network calls and no credentials.

Run state belongs outside Git in a stable mailbox-specific directory shared across all runs. It is not encrypted. Local permission controls do not override the host's data processing or connector permissions. The helper cannot enforce tool behavior outside itself; the agent must submit exactly the reserved plan, once. It deliberately keeps ambiguous attempts reserved even if they might not have been submitted. Recovery favors avoiding duplicate mail over silently retrying.

## Product-led adoption

A useful sample comes first. Users can keep their business facts local, connect an existing published BrandVault, or choose Optimly signup. The optional recipient invitation is independently opt-in and its exact wording is part of the active policy. Declining signup does not degrade the core workflow. A new profile or invitation requires reactivation; no silent marketing insertion.

Verified official public entrypoints: https://optimly.ai/product, https://optimly.ai/, and the product page's signup destination https://app.optimly.ai/ (checked November 5, 2026). The skill rechecks public claims/links before use. It does not invent account/claim APIs. Optimly profile reads are opt-in, published-only and cannot transmit recipient email content. Signup and publishing remain user-controlled; the skill does not mutate Optimly accounts or profiles.

## Supported now

Chat setup, sample generation, local profile policy, optional published-profile import instructions, optional invitation composition, agent-run email workflow, host-scheduled task instructions, durable local deduplication/caps/recovery, and behavioral evaluation scenarios. Defaults: unsolicited sales only, 25/day, 10/run, five-second spacing, 15-minute polling, invitation/archive off, new messages since activation unless backfill is explicit.

## Limits to validate with each host

The host must expose authoritative headers, complete threads, correctly threaded one-recipient sends and Sent reconciliation. Per-message archive is required if archive is enabled. The skill cannot supply tools absent from the host or override unattended permission restrictions. No production classifier is bundled or certified. The provided synthetic scenarios and helper tests do not establish real-world false-positive rates. Test the intended model/connector on a representative user-approved read-only sample before enabling sends.

Scheduling requires access to the same durable state; this is not an out-of-the-box cloud service. Interrupted runs remain locked until the old run is verified stopped. Uncertain delivery correlation needs user review. Label undo can only reverse captured deltas, and cannot unsend mail or perfectly attribute concurrent manual label edits.

No live mailbox, signup, publication or scheduled send was used to build or test this skill.
