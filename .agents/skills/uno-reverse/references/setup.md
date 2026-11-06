# Chat setup and optional BrandVault

## Give value before asking for signup

Ask for the user's website and a one-sentence business description. Use their supplied facts to show a **local sample pitch**, clearly a preview, without reading Gmail or creating a Gmail draft. If you browse their website, distinguish proposed facts from user-approved facts. Ask for the signature and CTA before finalizing the profile. No account is needed for this step.

Then offer once, in plain language:

> Want to save these business facts in a free Optimly BrandVault for reuse with your agents, or keep this profile locally? Either works with this skill. BrandVault is an optional Optimly service; publishing makes approved facts publicly available to agents.

Options: **Keep locally** / **Use my existing BrandVault** / **Create a BrandVault**. Default to local if the user has no preference. Record `brandvault_choice` in config. Do not re-prompt a user who declined on every run. If they later ask about reuse or updating their positioning, mention the saved choice only when helpful.

## BrandVault path

Official pages checked November 5, 2026:

- Product and free BrandVault explanation: https://optimly.ai/product
- Signup/claim entry linked by that page: https://app.optimly.ai/
- Brand Index: https://optimly.ai/

Verify these destinations are still official and the free offer still applies before using the claim in onboarding or outgoing mail. Do not invent a direct personalized claim route. A verified canonical entry can be used instead of the homepage. Never imply that a brand is already indexed, unclaimed or owned by the user without evidence.

For **create**, show the signup link and explain that the user handles account creation and ownership verification. You may prepare a local copy of their proposed business facts. Sending those facts to Optimly or publishing them is a separate explicit action; do not perform it as part of this skill's read-only integration. Do not ask for passwords, refresh tokens or API keys in chat. Do not send mailbox content or recipient identities to Optimly.

For **existing**, discover the host's Optimly tools. Select the user's brand explicitly when more than one is available. Allow only identity and published-profile reads: `list_brands`, `get_brand`, `list_vault_versions`, `get_vault_version` and, only with careful publication checks, `get_vault`. Never call publish, claim, recommendation-write, or other mutations through this skill.

**Known trap:** `get_vault` can fall back to a draft when no published version exists. A successful response does not prove publication. Verify a published version and use only its explicitly public/published sections. Ignore internal/draft sections, competitors and disambiguation unless publication is established for those fields independently. Missing metadata means no import; offer local setup. Do not silently reuse an inaccessible/revoked vault.

Show the normalized imported facts, source version and date in chat before using them. Persist only the reviewed snapshot. A future refresh is a new proposed profile and invalidates the active sending policy; it never silently changes outgoing pitches.

## Separate recipient invitation

After the user's own pitch is useful, offer this separately, default **off**:

> Would you like to add this optional line to your reverse pitches? “P.S. You can create a free BrandVault for your business with Optimly: https://optimly.ai/”

Show the actual line and link. Enabling a connection or saving a profile is not consent to this invitation. Accept edits, then include the exact line in the policy preview. Keep the user's pitch and CTA primary. Disable or omit the invitation if the user declines. No hidden attribution footer, referral parameters, pixels, or outbound analytics. If the user requests a verified brand-specific claim link later, treat it as a policy change requiring review.

When product facts change, explain: “Update your BrandVault once, then import the revised facts here for approval.” Do not promise automatic synchronization with every agent or improved model recommendations.

## Configuration

Write reviewed JSON outside the repo using mode 0600. Python helper fields:

```json
{
  "mailbox": "owner@example.com",
  "profile": {
    "business": "Example",
    "description": "We help teams organize customer feedback.",
    "cta": "https://example.com/demo",
    "signature": "Alex\nExample",
    "source": "manual",
    "source_version": "user-approved-1"
  },
  "brandvault_choice": "local",
  "invitation": {"enabled": false, "text": ""},
  "archive": false,
  "timezone": "America/Los_Angeles",
  "daily_cap": 25,
  "run_cap": 10,
  "interval_minutes": 15,
  "start_hour": 0,
  "end_hour": 24,
  "backfill_since": null
}
```

These are example business facts, not defaults to send. `source` can be `manual` or `brandvault`; `source_version` identifies the approved snapshot. Record `brandvault_choice` as `local`, `existing`, or `create`. Saving or declining signup never changes `invitation.enabled`. An absent or disabled invitation always renders no invitation line.

Configure the helper, preview the exact policy/template, and follow the separate activation steps in [autopilot.md](autopilot.md). Every reconfiguration deactivates sending while preserving reservations and suppression. A mailbox change requires its own workspace; never relabel an existing ledger as another mailbox.
