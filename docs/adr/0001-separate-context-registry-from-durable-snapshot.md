# Separate Context Registry From Durable Snapshot

BuildWealth keeps the **Context Registry** in `DURABLE_STORAGE_DIR/context_index.db` instead of adding live registry tables to `DURABLE_STORAGE_DIR/buildwealth_durable.db`. The durable database is a checksum-verified recovery snapshot of file-backed **Canonical State**, while the context index is a live, rebuildable retrieval index for **Context Intelligence**. Keeping them separate prevents recovery and migration state from being coupled to mutable search behavior.
