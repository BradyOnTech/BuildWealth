# Session Focus is distinct from Context Materiality, Candidate Prompt Influence, and Retrieval Relevance

BuildWealth implements **Session Focus** as a conversation-scoped steering layer for Copilot context assembly.

Session Focus may control which domains and sections are expanded, ordered, or muted in the **Prompt Brief** and retrieval ordering for one conversation. It must not:

- alter **Materiality Policy** outputs
- change **Candidate Prompt Influence** or candidate lifecycle
- fully suppress high/critical blocking safety signals (muted domains may still emit short safety warnings)
- replace tools or Canonical State as the source of deep financial detail

Default chat uses a slim Prompt Brief rather than serializing the full assembled context package. Conversation focus metadata lives on ConversationStore documents, outside the Context Registry (see ADR 0001).

Full design: `docs/COPILOT_SESSION_FOCUS_DESIGN_2026-07-09.md`.
