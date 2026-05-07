# Embeddings Are Opt-In For Context Intelligence

BuildWealth keeps embeddings disabled by default and limits them to **Narrative Evidence** when enabled. Structured **Canonical State** remains the source for balances, holdings, tax rates, contribution amounts, policy limits, and plan settings. Local providers such as Ollama are preferred first, while remote providers remain opt-in only, because Context Intelligence handles sensitive financial context.

This is the current default posture, not a permanent rejection of embeddings. If local or remote embeddings improve retrieval source recall by at least 20% on a representative BuildWealth eval set without increasing incorrect-source retrieval, BuildWealth may revisit the default after adding user-visible privacy controls, delete/rebuild actions, and provider visibility.
