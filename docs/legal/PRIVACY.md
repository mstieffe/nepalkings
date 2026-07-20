# Nepal Kings Privacy Policy

Version: 2026-07-20

This Privacy Policy explains what the public Nepal Kings game service collects and how it is used.

## Data We Collect

We collect account data such as username, password hash, optional email address, legal acceptance timestamps, and a session-revocation version. Signed login tokens are held by the client; the service does not store their plaintext value. We also store gameplay data such as games, cards, figures, battle moves, spells, kingdom state, rankings, chat messages, logs, and match results.

Technical data may include IP address, request metadata, timestamps, browser or client information, error logs, and security events. Passwords are stored as hashes, not plaintext.

We also keep a first-party gameplay-event log (for example: account created, booster opened, match finished) used solely to understand and improve the new-player experience. This log stays in our own database, contains no IP addresses or device fingerprints, and is never shared with third parties.

## How We Use Data

We use data to operate accounts, run matches, persist game progress, provide rankings, troubleshoot bugs, prevent abuse, enforce fair play, secure the service, and comply with legal obligations.

Player reports store the reporter, reported player, reason, optional details,
and a bounded evidence snapshot. Message evidence is accepted only when the
reporter was authorized to see that message. Player blocks are stored so the
service can hide and prevent direct contact. Moderation actions are recorded
for accountability.

## Public and Shared Data

Other players may see your username, online status, rankings, public kingdom/game state needed for gameplay, and messages you send to them. Hidden cards, hands, deck order, private tactics, and private match state should be shown only to authorized players except when game mechanics reveal them.

## Email

If email verification is enabled and you provide an email address, it is used for account verification and account-related messages. Email is optional unless a deployment chooses to require it.

## Retention

Account and gameplay data are retained while needed to operate the service,
preserve game history, handle disputes, or protect security. Application and
security logs are normally kept for up to 30 days. Production backups are
normally kept for up to 90 days. Closed report evidence and moderation audit
records may be kept for up to 12 months, or longer when an active safety,
abuse, security, or legal matter requires it.

Account deletion immediately revokes sessions and anonymizes the username,
email, sent messages, kingdom name, and related identifiers that can be
removed without breaking shared match history or economy integrity. Historic
games and results remain under an anonymous deleted-player identity. Received
private kingdom messages are removed from the deleted account. Backup copies
expire through the normal backup-retention cycle rather than being rewritten
in place.

## Security

We use authentication, authorization checks, rate limits, redaction of hidden game state, dependency scanning, and operational safeguards. No system is perfectly secure, and players should avoid sharing sensitive personal information in chat or usernames.

## Children

The service is not intended for children under 13. Registration requires age confirmation.

## Your Choices

Use the **Account** tab in **Settings** to change your password, revoke every
device session, download a JSON copy of your account data, block/report a
player, or delete and anonymize your account. For account or data questions,
use <https://github.com/mstieffe/nepalkings/issues/new> without posting
passwords, tokens, private messages, or other personal data.

## Changes

We may update this Privacy Policy. Material updates should receive a new version date.
