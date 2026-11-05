# Implementation status

## Milestone 1: runnable local workflow

Implementation is authorized. This first milestone exercises manual review and autopilot with a persistent synthetic mailbox; it is not an MVP release or a live-mail authorization.

The adapter boundary is `MailboxAdapter`. Core state belongs in SQLite, not the adapter. Each state directory belongs to exactly one mailbox. A global process lock serializes submission and recovery so another process cannot mistake an active send for a crashed one. Reservations and daily budgets are committed before submission. Failures after submission begins are unknown unless the adapter expressly guarantees that nothing was submitted. Unknown reservations remain held even when Sent lookup finds no match.

Manual approval hashes the exact plan. A policy adds a policy-version identifier to the authorization receipt. Profile/mapping changes invalidate approvals and deactivate the active policy. The synthetic classifier requires an explicitly configured sender-domain/company mapping and supporting body text. Its small evaluation fixture is a development guard, not evidence that real incoming mail is safe to classify automatically. Live submissions are blocked in the workflow.

Organization is independent of sending. Deltas persist before mutation and operate on captured message IDs. Failed label operations can be retried without calling send. Incoming messages arriving after approval cannot be archived by that approval.

## Remaining work before MVP acceptance

1. Gmail Desktop OAuth with PKCE/state-validated loopback callback, OS keychain storage, scope upgrades, identity checks, refresh serialization, revocation and error fixtures. Provisioning actual Google infrastructure requires the user's explicit setup instruction.
2. Official Gmail API adapter: full pagination, maintained MIME/header normalization, transient incoming content, preview-only enforcement, real provider error classification, stable Message-ID reconciliation, organization retry and live-account acceptance.
3. Maintained public-suffix domain handling, stronger identity/relay handling, richer protected categories and a versioned production classifier with a substantial labeled evaluation corpus. No remote model data flow is enabled. Select any model provider separately from the sending authority.
4. Full policy scheduling and cursor support: overlapping incremental Gmail windows, per-run pacing that drains a batch, explicit cap-lowering updates and richer policy editing/review UI. The prototype rescans the approved scope and deduplicates by source ID.
5. Separate-thread delivery-status parsing/correlation and bounce suppression; robust reply parsing across MIME/quote formats; uncertain correlation remains uncertain. Current reply heuristics are for synthetic fixtures only.
6. Published-only BrandVault adapter with verifiable publication metadata and explicit profile approval. No Optimly production integration is currently used.
7. Full Setup/Autopilot/Activity/Replies screens, secure data purge/export UX, cross-platform credential stores/locks and packaging. Current process locking supports macOS/Linux.
8. Dedicated consenting-account Gmail acceptance run (requires separate live-send authorization), clean install checks, public naming/license/OAuth/privacy review and supported release packaging.

## Dependencies

No third-party runtime packages. Build dependency: `setuptools`, verified against its [official PyPI project](https://pypi.org/project/setuptools/) before addition. CI uses the official [checkout v4](https://github.com/actions/checkout/tree/v4) and [setup-python v5](https://github.com/actions/setup-python/tree/v5) actions. Additional dependencies must be verified at their official registries before use.
