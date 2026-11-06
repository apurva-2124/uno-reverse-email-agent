# Host tools and capability checks

Discover available tools at runtime; a skill is not a mailbox connector. Prefer connected Gmail tools over browser automation. Keep Gmail credentials in the host connector. Do not provision a custom OAuth app or ask the user to paste credentials.

Before activation, establish these capabilities without sending anything:

- Read the authenticated mailbox identity.
- Search with date/inbox scope, paginate, and read complete threads plus authoritative From/Reply-To headers.
- Send a reply to exactly one specified address with correct source-message/thread linkage and an exact body. No CC/BCC/attachments. Select safe plain text if the tool's Markdown/HTML behavior could alter the approved message.
- Inspect Sent messages and confirm sender, recipient, subject, body, timestamp and thread/provider IDs for reconciliation.
- Apply labels and, only if selected, remove INBOX from captured message IDs. If only thread-wide archive exists, leave archive off and explain why.
- Read/write the shared local ledger from every scheduled run.

The currently connected Gmail tool family exposes `get_profile`, email search/read operations, `read_email_thread`, `send_email`, label operations, drafts and archive. Inspect actual schemas: tools can change, thread reads can be capped, and result wrappers can contain nested arrays rather than a direct list. Do not assume a `messages` field or that the first result page is complete. Increasing `max_messages` is not proof of completeness when the service still truncates.

The host agent's model does classification; this skill has no separate API key, remote-model adapter or keyword classifier. The host may process email content in its service according to its own data controls. Local ledger storage does not mean all email processing stays on the device. Tell the user this during setup.

For replies, read the source first. Pass the tool's documented reply/thread reference and exact single recipient; do not guess parameter names. If the tool cannot preserve threading or returns no authoritative headers, defer that candidate instead of silently sending a new conversation.

If a send response is ambiguous, retain its reservation and pause. Some connector APIs cannot set a stable RFC Message-ID. Record every returned provider identifier and use corroborated exact Sent metadata; unresolved/ambiguous matches stay unknown and require user action. This skill does not promise exactly-once delivery.

A saved Gmail draft is an external write and is unnecessary for chat preview. Only create one if the user requests it. Do not use drafts or a browser as a workaround for unavailable sending permissions.

If the host cannot execute scheduled sends within its permissions, keep preview/manual mode and say which capability is missing. Do not create repeated approval requests or widen permissions on the user's behalf.
