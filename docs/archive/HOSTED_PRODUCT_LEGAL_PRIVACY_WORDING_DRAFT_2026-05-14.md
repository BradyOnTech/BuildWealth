# Hosted Product, Legal, and Privacy Wording Draft

**Date:** 2026-05-14

**Status:** Draft product/legal/privacy wording for hosted BuildWealth. This is not legal advice. Counsel or qualified compliance review is required before public launch.

## Purpose

BuildWealth now owns the full product experience: household workspaces, portfolio analysis, simulations, recommendations, research, Copilot, hosted sign-in integration, account closure, delayed data deletion, and irreversible purge. The public wording needs to match those implementation facts in plain language.

This document is the working copy source for:

- privacy policy language
- terms and financial guidance disclaimers
- AI-use disclosure
- Settings and deletion microcopy
- hosted launch legal/privacy review

## Source Guidance

These external references are not BuildWealth policy by themselves, but they are useful anchors for review:

- [FTC Start with Security: A Guide for Business](https://www.ftc.gov/business-guidance/resources/start-security-guide-business) emphasizes building security into the product, collecting only what is needed, limiting access, protecting stored data, and disposing of data safely when it is no longer needed.
- [California Attorney General CCPA guidance](https://oag.ca.gov/privacy/ccpa) describes consumer rights and notice topics such as access/know, deletion, correction, opt-out of sale or sharing, limiting sensitive personal information, non-discrimination, and required privacy notices where the law applies.

BuildWealth copy should avoid broad promises unless the product, operations, vendor contracts, and legal review can support them.

## Product Positioning Boundary

Use this plain-language boundary everywhere:

> BuildWealth helps you organize your financial life, test simulations, review tradeoffs, and keep a record of the assumptions behind your decisions. BuildWealth is not your financial advisor, broker, tax professional, or attorney.

Preferred terms:

- **simulation** for exploratory planning experiments
- **review** for human-checkable analysis
- **suggestion** or **draft** for AI output
- **workspace** for the user's household financial data area
- **Close BuildWealth access** for access revocation without data purge
- **Delete BuildWealth data** for delayed destructive deletion

Avoid:

- "guaranteed"
- "advisor-approved"
- "tax advice"
- "investment advice"
- "we will make decisions for you"
- "delete account" when the action only closes BuildWealth access
- "permanent deletion" before the purge worker has actually completed

## User-Facing Privacy Summary

Short version for Settings, onboarding, or a privacy overview:

> BuildWealth stores the information needed to help you use your household workspace: account details, profile inputs, portfolio records, simulations, Copilot conversations, saved research, imports, reports, backups, and security/audit records. If you add an AI provider key or use Copilot, BuildWealth may send the context needed for that request to your selected provider. You can close BuildWealth access, export available account data, remove provider keys, and request deletion of BuildWealth workspace data through Settings.

## Privacy Policy Draft

### What BuildWealth Collects

BuildWealth may collect and store:

- account information, such as email address, display name, hosted identity-provider ID, sign-in status, and account role
- household profile information, such as income, expenses, debts, goals, tax-related planning inputs, retirement assumptions, and notes you choose to save
- portfolio information, such as accounts, holdings, transactions, prices, benchmarks, allocation targets, risk guardrails, and performance views
- simulation information, such as saved scenarios, contribution assumptions, withdrawal comparisons, retirement settings, tax settings, and results
- research and recommendation information, such as watchlist items, evidence packets, thesis notes, recommendation drafts, accepted decisions, rejected decisions, and review history
- Copilot information, such as messages, tool traces, context packets, drafts, recommendations, and profile-update proposals
- import and export information, such as uploaded files, generated reports, reconciliation results, and audit trails
- provider configuration, such as selected AI provider, model, endpoint, and encrypted API keys or tokens
- operational information, such as sessions, CSRF records, audit events, recovery metadata, backup metadata, error records, and maintenance-job results

### How BuildWealth Uses Data

BuildWealth uses data to:

- provide access to private household workspaces
- show portfolio, performance, allocation, and risk views
- run simulations and compare possible outcomes
- support imports, reconciliation, exports, backups, and recovery
- personalize Copilot responses and drafted recommendations
- store provider settings and encrypted workspace secrets
- secure accounts, enforce workspace permissions, prevent abuse, and audit sensitive actions
- operate, debug, maintain, and improve the hosted service

### Hosted Sign-In

BuildWealth may use a hosted identity provider for sign-in, password reset, multi-factor sign-in, passkeys, email verification, and provider-side account security controls.

BuildWealth receives only the identity information needed to create or link a BuildWealth account, such as email address, display name, provider user ID, and sign-in/security status signals. The hosted identity provider may separately process sign-in and security data under its own terms and privacy practices.

Closing BuildWealth access does not automatically delete the hosted identity-provider account.

### AI Providers and Copilot

If you configure an AI provider or use Copilot, BuildWealth may send the information needed to answer your request to the configured provider. That context may include financial profile details, portfolio data, simulation inputs, research notes, or conversation history when those details are relevant to the request.

BuildWealth should minimize unnecessary context, but users should assume that information included in a Copilot request may be processed by the selected provider. Provider use is also governed by the provider's own terms, privacy policy, and data-handling settings.

BuildWealth stores provider API keys as encrypted workspace secrets. After a key is saved, BuildWealth does not return the raw key value through the UI or API.

### Financial Guidance Boundary

BuildWealth provides tools, simulations, analysis, drafts, and suggestions. It does not provide personalized financial, investment, tax, legal, accounting, or brokerage advice.

Simulations are experiments based on the assumptions and data available at the time. They are not guarantees, forecasts, or promises. Market conditions, taxes, laws, income, expenses, and personal circumstances can change.

AI-generated content can be incomplete, outdated, or wrong. Users are responsible for reviewing assumptions, checking important facts, and deciding whether to act. Users should consult qualified professionals before making major financial, tax, legal, or investment decisions.

### Sharing

Draft public-language position:

> BuildWealth does not sell household financial data.

Counsel review required:

- Confirm whether any analytics, identity, AI, infrastructure, or support vendors create a "sale," "share," "targeted advertising," or similar disclosure obligation under applicable privacy laws.
- Confirm whether BuildWealth needs a "Do Not Sell or Share" link, opt-out mechanism, or sensitive-data limitation control.
- Confirm whether AI-provider processing must be separately disclosed as service-provider, processor, subprocessor, or independent-controller processing.

### Security

Draft public-language position:

> BuildWealth uses access controls, workspace isolation, encrypted provider secrets, protected session cookies, CSRF protection for sensitive actions, and audit records for important account and data events.

Avoid absolute language:

- do not say "fully secure"
- do not say "bank-level security" unless independently validated
- do not say "all data is encrypted" unless storage, transit, backups, logs, and secrets all support the statement

### Exports

Users should be able to export available account metadata and, as product coverage matures, workspace data bundles. Account metadata export is not the same as a full financial-data export.

Draft Settings copy:

> Export account details before closing access or requesting data deletion. Some workspace files, generated reports, backups, and audit records may not be included in this account metadata export.

### Close BuildWealth Access

Use this for the non-destructive hosted closure flow:

> Close BuildWealth access disables your BuildWealth account, removes your active workspace memberships, and signs you out. It does not delete workspace files, backups, encrypted provider secrets, audit records, or your hosted identity-provider account.

Confirmation label:

> Type close buildwealth access

Success message:

> BuildWealth access closed. Workspace data and required records were retained under the current retention policy.

### Delete BuildWealth Data

Use this for the delayed destructive deletion flow:

> Delete BuildWealth data schedules deletion for the selected scope. You will see a preview before scheduling. During the recovery window, affected workspaces are unavailable in normal app workflows and you can cancel the request. After the recovery window ends, a private maintenance job permanently removes due workspace files, backups inside the workspace, and encrypted workspace secrets.

Scope labels:

- **Current workspace:** Deletes data for the workspace you are using now.
- **Household data:** Deletes the household workspaces covered by the request.
- **Account data:** Deletes BuildWealth workspace data tied to the account scope, while retaining required security, audit, legal, and operational records.

Preview copy:

> Review what will be deleted and what will be retained before scheduling deletion.

Pending copy:

> Deletion is scheduled. You can cancel until the recovery window ends.

Completed copy:

> Deletion completed. BuildWealth removed the affected workspace files, backups inside those workspaces, and encrypted workspace secrets. Required security, audit, legal, and operational records may be retained.

Failed copy:

> Deletion could not be completed. BuildWealth kept the request record and failure details for review. Contact support before retrying.

### What Deletion Removes

When the purge worker completes successfully, BuildWealth removes:

- affected workspace files
- backup archives stored inside affected workspace roots
- encrypted workspace secrets, including provider API keys stored in the workspace
- imports, reports, generated artifacts, research packets, Copilot conversations, simulations, recommendations, and profile data stored in the affected workspace root

### What Deletion May Retain

BuildWealth may retain limited records after deletion when needed for security, abuse prevention, legal compliance, accounting, dispute resolution, operational integrity, or proof that deletion occurred.

Retained records may include:

- deletion request ledger rows
- purge results and failure records
- minimal control-plane account, organization, workspace, and membership records
- audit events for sensitive account and data actions
- session/security records needed for investigation
- records required by law or legitimate operational needs

Do not promise that every copy is instantly removed from every backup or log unless backup pruning, offsite backup retention, logs, vendor retention, and legal holds are all covered by implementation and policy.

## Terms Draft

### No Professional Advice

> BuildWealth is a software tool. BuildWealth is not a registered investment adviser, broker-dealer, tax advisor, accountant, attorney, or financial planner. BuildWealth does not make decisions for you or place trades for you. Any simulation, score, review, draft, suggestion, or recommendation is informational and must be reviewed by you.

### Simulations

> Simulations are experiments. They use assumptions, estimates, and data available at the time. Actual outcomes can be different. You should review the assumptions and update them as your life, market conditions, tax rules, and goals change.

### AI Output

> Copilot and other AI-assisted features can produce incomplete, inaccurate, or outdated information. AI output should be treated as a draft or starting point, not as a final decision.

### User Responsibility

> You are responsible for the information you enter, the assumptions you choose, and the decisions you make. For important financial, investment, tax, legal, or estate decisions, consult a qualified professional.

### Provider Keys

> If you add a provider API key, you confirm that you are allowed to use it with BuildWealth. You are responsible for the provider account, provider charges, limits, and provider terms. Removing a key from BuildWealth does not close your provider account.

## Settings Microcopy

### Connections and AI

Header:

> Connections & AI

Subtext:

> Connect the provider Copilot should use. Keys are stored as encrypted workspace secrets and are not shown again after saving.

Provider-key hint:

> Required for live Copilot responses. Remove the key to stop BuildWealth from using this provider for the current workspace.

### Account and Data

Header:

> Account & data

Subtext:

> Manage sign-in, exports, access closure, and BuildWealth data deletion.

Hosted sign-in:

> Sign-in security is managed by your identity provider. Use it for password reset, multi-factor sign-in, and passkeys.

Close access:

> Close BuildWealth access signs you out, disables your BuildWealth account, and removes active workspace memberships. It does not delete workspace data or your identity-provider account.

Data deletion:

> Preview first. Deletion is delayed for 30 days and can be canceled during that window. After the recovery window, due requests are processed by a private purge job.

Retained records:

> BuildWealth may retain limited security, audit, legal, and operational records after deletion.

## Public Privacy Page Outline

1. Overview
2. Data BuildWealth collects
3. How BuildWealth uses data
4. Hosted sign-in and identity provider
5. AI providers and Copilot
6. Provider API keys and encrypted workspace secrets
7. Data sharing and vendors
8. Exports, access closure, and deletion
9. Retention and backups
10. Security
11. User rights and choices
12. Children's privacy and age limits
13. International users, if supported
14. Changes to this policy
15. Contact information

## User Rights Copy Placeholders

These need jurisdiction and counsel review before publishing:

> Depending on where you live, you may have rights to request access, correction, deletion, portability, restriction, objection, opt-out of sale or sharing, or appeal of certain privacy decisions. To make a request, contact [privacy contact].

> We may need to verify your identity before completing a request. Some records may be retained when required or permitted for security, legal, operational, or compliance reasons.

## Launch Review Checklist

- [ ] Legal operator name chosen.
- [ ] Privacy contact email chosen.
- [ ] Terms contact email chosen.
- [ ] Support path chosen for deletion failures.
- [ ] Jurisdiction and governing law chosen.
- [ ] Minimum user age chosen.
- [ ] Public privacy policy reviewed by counsel.
- [ ] Terms of service reviewed by counsel.
- [ ] Financial guidance disclaimer reviewed by counsel.
- [ ] AI-use disclosure reviewed by counsel.
- [ ] Hosted identity-provider disclosure reviewed against provider contract.
- [ ] AI provider disclosure reviewed against provider contracts and data-use settings.
- [ ] Vendor/subprocessor list created.
- [ ] No-sale/no-share language reviewed for applicable laws.
- [ ] Sensitive-data handling reviewed.
- [ ] Deletion retention and backup wording reviewed against actual infrastructure.
- [ ] Support and abuse-handling retention needs documented.
- [ ] Incident response and breach-notification obligations reviewed.

## Open Product Decisions

- What is the legal operator name?
- What privacy contact email should users see?
- What support path handles deletion failures?
- Which jurisdictions will hosted BuildWealth support at private beta?
- What is the minimum user age?
- Is MFA optional, encouraged, or required?
- Are remote analytics, crash reporting, or session replay tools allowed?
- Which AI providers are officially supported in hosted mode?
- Does hosted mode allow user-supplied custom AI endpoints?
- Are embeddings local-only, remote, or disabled by default?
- Should account email be anonymized after the purge worker completes?
- Should BuildWealth ever call the hosted identity provider to delete provider-side identities?
- What offsite backup retention exists outside workspace-local backups?
- What records are retained under legal hold, fraud prevention, tax, accounting, or abuse policies?

## Implementation Notes

- Keep the authoritative product state in v2 Settings, not hidden admin pages.
- Serve public hosted pages at `/privacy`, `/terms`, and `/ai-disclosure`.
- Put plain-language deletion controls under **Settings -> Account & data**.
- Put provider key and AI-routing copy under **Settings -> Connections & AI**.
- Put public policy pages in the hosted web shell once the deployment target exists.
- Keep API response messages aligned with this document so browser UI, tests, and docs use the same terms.
- Do not expose raw provider secrets in preview, export, logs, audit metadata, or error details.
- Treat account metadata export and workspace data export as separate product surfaces.
- Keep "Close BuildWealth access" separate from "Delete BuildWealth data" in both UI and backend route names.
- Mark completed deletion requests only after filesystem purge succeeds.
- Mark failed deletion requests with reviewable failure results and no false success message.
