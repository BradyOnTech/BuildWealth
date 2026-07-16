# Risk Lens is exploratory, deterministic, and non-blocking

BuildWealth implements **Risk Lens** as a conversation-scoped way to inspect the same financial conditions under Conservative, Moderate, or Aggressive posture policy.

The application, not the LLM, owns the comparison. One deterministic run freezes its inputs, calculates all three variants, records a fingerprint and policy/adapter versions, and stores the structured result with the Copilot answer. The LLM may explain those results but cannot suppress a variant or manufacture a difference.

Risk willingness and risk capacity remain distinct signals. Capacity changes `capacity_fit`, recommendation status, warnings, and the explanation; it never changes whether the user may explore a posture. In particular, `not_recommended` and `exceeds` remain visible and complete unless a separate technical or invalid-input failure makes calculation unavailable.

A Risk Lens is not **Canonical State**. Moving the lens cannot update Profile, Portfolio, Plan, Recommendations, or saved simulations. A user may change the saved Profile posture only through a visible draft/review/confirm action. Future Profile-mode turns then resolve the newly confirmed value.

Risk Lens is also distinct from **Session Focus** and **Context Materiality**: Focus chooses which context receives attention, Materiality governs review authority and urgency, and Risk Lens compares candidate tradeoffs. None may silently relax restrictions, concentration caps, tax sensitivity, research standards, or other confirmed guardrails.

The initial adapter is cash liquidity, using a versioned 9/6/4-month reserve policy. Portfolio and Plan adapters must preserve the same frozen-input, all-posture, non-blocking contract.

Full implementation plan: `docs/COPILOT_RISK_LENS_IMPLEMENTATION_PLAN_2026-07-15.md`.
