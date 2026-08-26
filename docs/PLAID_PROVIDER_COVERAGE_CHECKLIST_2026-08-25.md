# Plaid provider coverage checklist

Status: pre-release evidence log. A directory listing is not a successful connection test.

## Required products

Phase 1 requests only Plaid Investments. For each institution below, verify Link discovery, OAuth/credential return, account selection, `/item/get`, `/investments/holdings/get`, a later holdings update, update mode, and `/item/remove`. Record the date, Plaid environment, test owner, result, and any missing account types.

## Institution matrix

| Institution group | Representative institution | Directory precheck | End-to-end result |
|---|---|---:|---:|
| Local bank | Hills Bank | Plaid publicly lists Investments support | Pending credentialed test |
| Brokerage | Fidelity | Pending | Pending |
| Brokerage | Vanguard | Pending | Pending |
| Brokerage | Charles Schwab | Pending | Pending |
| Brokerage | E*TRADE | Pending | Pending |
| Brokerage | Merrill | Pending | Pending |
| Bank/brokerage | J.P. Morgan / Chase | Pending | Pending |
| Bank/brokerage | Wells Fargo | Pending | Pending |
| Brokerage | Edward Jones | Pending | Pending |
| Brokerage | Robinhood | Pending | Pending |
| Brokerage | Interactive Brokers | Pending | Pending |
| Retirement | Empower | Pending | Pending |
| Retirement | TIAA | Pending | Pending |
| Retirement | Principal | Pending | Pending |
| Retirement | Voya | Pending | Pending |
| Retirement | Transamerica | Pending | Pending |

## Scenario evidence required

- Desktop Link and mobile OAuth return use the same Link token.
- A second attempt for an already-connected institution is stopped before public-token exchange and points to Repair.
- The initial account/match preview remains staged until explicit approval.
- Login-required, consent-expired, institution-down, timeout, and malformed/partial response paths preserve the last valid snapshot.
- A holdings webhook is verified, durably queued, replay-safe, and retried after failed work.
- Both disconnect choices revoke the remote Item before local credentials are shredded.
- Restored connections remain quarantined until a fresh provider read succeeds.
- Seven consecutive daily reads complete without duplicate accounts, lost observations, or unexpected product billing.

## Cost and launch gates

- Record the signed Plaid pricing terms; public pricing pages are not a substitute for the account contract.
- Compare the monthly invoice with `potentially_billable_items` and enabled-product inventory from `GET /api/connections`.
- Set an owner and threshold for unexpected Item/product growth.
- Verify Plaid Dashboard branding, redirect URI, webhook URL, Data Transparency Messaging, and Production approval.

References: [Plaid institution coverage](https://plaid.com/institutions/), [Plaid Link web integration](https://plaid.com/docs/link/web/), and [Plaid duplicate Item guidance](https://plaid.com/docs/link/duplicate-items/).
