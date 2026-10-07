# Vibe-Trading research notes

Primary-source review of `HKUDS/Vibe-Trading` for possible relevance to BuildWealth.

## Findings

- The project is a beta-stage MIT-licensed Python package named `vibe-trading-ai` (`0.1.13`) that targets Python 3.11 through 3.13 and depends on a broad stack: LangChain/LangGraph for the agent layer, FastAPI/Uvicorn/SSE for the server, and pandas/numpy/scipy/ccxt/akshare/yfinance/tushare plus document-processing libraries for analysis workflows. Source: [pyproject.toml](https://github.com/HKUDS/Vibe-Trading/blob/main/pyproject.toml#L1-L79), [LICENSE](https://github.com/HKUDS/Vibe-Trading/blob/main/LICENSE).

- The product is not just a CLI. The repo exposes a CLI entry point, a FastAPI API server, an MCP server, a React frontend, a desktop shell, market-data loaders, trading connectors, backtest engines, skills, and a large tool registry. The README’s project structure and API sections match that split. Source: [README.md](https://github.com/HKUDS/Vibe-Trading/blob/main/README.md#L1658-L1668), [README.md](https://github.com/HKUDS/Vibe-Trading/blob/main/README.md#L1113-L1153), [api_server.py](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/api_server.py#L1-L22).

- The AI/chat core is a ReAct-style agent loop with five-layer context management and parallel execution for consecutive read-only tools. The chat layer is designed around structured tool-calling and provider streaming, not just plain prompting. Source: [agent/loop.py](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/src/agent/loop.py#L1-L12), [agent/providers/chat.py](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/src/providers/chat.py#L1-L44).

- Market data is a first-class capability. `get_market_data` normalizes OHLCV across symbol formats and supports `auto` source selection. The README says it has 23 free sources plus optional QVeris routing, covering A-shares, HK/US/Canada equities, crypto, futures, forex/metals, Korea, India, and local files. The tool itself documents provenance and per-symbol volume units. Source: [README.md](https://github.com/HKUDS/Vibe-Trading/blob/main/README.md#L344-L408), [market_data_tool.py](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/src/tools/market_data_tool.py#L11-L106).

- Execution is connector-first rather than a generic broker adapter. The service layer has direct-SDK connectors for IBKR local TWS/Gateway, Longbridge, Alpaca, OKX, Binance, Futu, Dhan, Shoonya, Trading 212, MT5, and eToro, and the README describes paper/live or read-only modes with explicit mandate and kill-switch gating. Source: [trading/service.py](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/src/trading/service.py#L1-L29), [README.md](https://github.com/HKUDS/Vibe-Trading/blob/main/README.md#L1377-L1532).

- The repo ships a broad agent/API surface: 70 MCP tools, swarm presets, scheduled research jobs, an OpenBB bridge, IM channel adapters, and external MCP client-mode support. That makes it a workflow platform, not just a backtester. Source: [README.md](https://github.com/HKUDS/Vibe-Trading/blob/main/README.md#L1123-L1298), [api_server.py](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/api_server.py#L127-L160).

## What looks useful for BuildWealth

- Good fit: the normalized market-data layer, provenance-aware bar loading, research workflow orchestration, scheduled research, report/export patterns, and the ReAct/tooling architecture.
- Medium fit: the document-ingestion and read-only research tools if BuildWealth wants a richer evidence pipeline.
- Low fit: the live execution stack, because it is optimized for broker connectors, trading mandates, and kill switches rather than a personal-finance app’s narrower planning and portfolio workflows.

## Bottom line

Vibe-Trading looks most valuable to BuildWealth as a reference implementation for agentic research workflows, market-data normalization, scheduled analysis, and evidence-rich reporting. It is probably too trading-centric to adopt wholesale, especially where BuildWealth should stay focused on personal finance rather than broker execution.
