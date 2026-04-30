# BuildWealth Product Testing Checklist

## Date
2026-04-30

## Purpose

Use this checklist after the release-readiness backend/product contract lands. The goal is to manually test the product feature by feature, find issues in the real user loop, and fix correctness, trust, routing, and data-loss risks before adding new feature breadth.

The product loop under test is:

1. Understand current financial reality.
2. Notice what changed.
3. Identify the best next review or action.
4. Inspect, simulate, discuss, apply, reject, or defer.
5. Capture what happened.
6. Improve future guidance.

## Gate 0: Release Readiness

Before testing the rest of the product:

- Confirm release readiness status is visible in v2 Atelier.
- Confirm Today Trust domain reflects the same readiness posture.
- Confirm backup exists and backup age is acceptable.
- Confirm protection status is compliant or clearly actionable.
- Confirm checkpoint state is visible and dirty state is understandable.
- Confirm read-only restore preview can be generated without applying restore.
- Confirm Profile/Copilot audit events appear after profile and Copilot-applied changes.
- Confirm provider/degraded-mode blockers are visible when mocked or naturally present.

If readiness is `blocked`, stop broad product testing and fix trust issues first.

After completing a pass, record the result through the workflow verification endpoint so future release-readiness checks can cite real evidence instead of only pointing back to this checklist:

```bash
curl -X POST http://localhost:8000/api/release-readiness/workflow-verification \
  -H 'Content-Type: application/json' \
  -d '{"workflow":"product_testing","status":"passed","passed_count":9,"failed_count":0,"checklist_path":"docs/PRODUCT_TESTING_CHECKLIST_2026-04-30.md","notes":"Manual product pass completed."}'
```

## Today

- Open Today and verify the top action is understandable without navigating elsewhere.
- Review What Changed and record a daily checkpoint.
- Verify confidence heat-map domains route to the correct surfaces.
- Verify cash runway, profile readiness, research readiness, trust, and pending outcome cards are coherent.
- Confirm stale/degraded/missing context is visible and not hidden in diagnostics only.

## Profile And Copilot Profile Completion

- Trigger guided profile completion from Today or Copilot.
- Draft a profile update through Copilot.
- Review the draft before applying.
- Apply the draft and confirm profile readiness updates.
- Confirm the profile update is audited in v2 Atelier.

## Inbox Recommendation Loop

- Preview generated recommendations.
- Create a reviewed batch.
- Open a recommendation and verify evidence, quality, freshness, actionability, and ranking explanation.
- Preview before apply where supported.
- Apply or reject with a rationale.
- Capture outcome and verify closure/pre-mortem context appears when relevant.

## Plan

- Open active v2 Plan.
- Edit a core assumption and save.
- Review Plan health.
- Open evidence/artifact center.
- Run scenario diff.
- Run life-event branch preview.
- Run withdrawal-strategy comparison.
- Append or review a decision.
- Open bounded Copilot plan review and confirm it avoids full-history context bloat.

## Portfolio And Investment Fit

- Open Portfolio fit review for a symbol.
- Verify evidence packet, concentration, cash runway, policy guardrails, tax/account-location context, and plan horizon appear.
- Try a proposed account/contribution route and confirm conflicts are review-only.
- Open Copilot investment-fit discussion from the fit result.
- Confirm no surface uses hidden buy/sell language.

## Research

- Open packet-native symbol evidence.
- Compare a small symbol set.
- Open saved dossier lookup and detail.
- Review thesis status and expiry.
- Revise a thesis through Copilot and save back to watchlist or dossier metadata.
- Confirm research routes stay in v2 for normal workflows.

## Copilot

- Ask for a daily review explanation.
- Ask why a recommendation is blocked by missing context.
- Ask whether an investment fits.
- Ask for a bounded plan review.
- Confirm tool traces render as structured cards.
- Confirm important mutations are drafted/reviewed/applied rather than silently saved.

## Atelier

- Review release readiness.
- Create backup.
- Apply protection.
- Create checkpoint.
- Generate read-only restore preview.
- Review Profile & Copilot changes.
- Confirm classic links remain available only for advanced or lower-frequency maintenance.

## Issue Triage Rules

Classify issues found during testing:

- `P0`: data loss, unsafe mutation, restore/checkpoint failure, or hidden investment action.
- `P1`: incorrect financial result, broken apply/preview/outcome flow, or misleading readiness/confidence state.
- `P2`: broken routing, missing evidence, weak explanation, or confusing degraded-state handling.
- `P3`: copy, polish, layout, or non-blocking ergonomics.

Fix order:

1. P0/P1 trust and correctness issues.
2. Cross-surface workflow breaks.
3. Missing confidence/readiness explanations.
4. UI polish.

Do not add new product breadth until P0/P1 issues from the pass are closed.
