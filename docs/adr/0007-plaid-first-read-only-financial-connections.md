# Plaid First for Read-Only Financial Connections

BuildWealth will own a provider-neutral **Financial Connection** capability and use Plaid as its first production provider. Plaid was selected for its broad household-finance direction and documented support for Hills Bank, while a narrow provider boundary keeps Plaid-specific contracts out of BuildWealth's domain and leaves room for a measured second provider later.

Manual entry and CSV import remain permanent, first-class alternatives. Connections are strictly read-only and advisory: BuildWealth may receive accounts, balances, cash, and holdings, but it will not place trades, move money, or collect execution credentials. Provider-owned current quantities and balances cannot be manually overwritten; BuildWealth-owned classifications, tax treatment, goals, tags, and notes remain editable.

The first release covers current investment and retirement account state, not connected transaction history, bank spending, liabilities, paid real-time refresh, trading, or transfers. New connections require explicit account-mapping and initial-data review; approved connections then update automatically while preserving prior observations, source evidence, health, and staleness. Disconnecting always revokes provider access and then lets the user retain a clearly stale frozen copy or remove provider-imported data.
