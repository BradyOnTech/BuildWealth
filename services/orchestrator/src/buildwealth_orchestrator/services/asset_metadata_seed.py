from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_ASSET_METADATA_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "asset_metadata_seed.json"
_CRYPTO_BASE_SYMBOLS = {
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "DOT",
    "LINK",
    "LTC",
    "BCH",
    "MATIC",
}


@lru_cache(maxsize=1)
def load_seed_asset_metadata() -> dict[str, dict[str, Any]]:
    if not _ASSET_METADATA_SEED_PATH.exists():
        return {}

    try:
        payload = json.loads(_ASSET_METADATA_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    raw_symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(raw_symbols, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for symbol, record in raw_symbols.items():
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol or not isinstance(record, dict):
            continue
        normalized[normalized_symbol] = dict(record)

    return normalized


def infer_asset_metadata(symbol: str) -> dict[str, Any] | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None

    if normalized in {"CASH", "USD", "USDT", "USDC"}:
        return {
            "name": normalized,
            "asset_type": "CASH",
            "asset_class": "Cash",
            "sector": "Cash",
            "region": "US",
            "data_source": "MANUAL",
            "metadata_source": "fallback",
        }

    if normalized.endswith("-USD"):
        base = normalized.split("-", 1)[0]
        if base in _CRYPTO_BASE_SYMBOLS:
            return {
                "name": normalized,
                "asset_type": "CRYPTO",
                "asset_class": "Crypto",
                "sector": "Digital Assets",
                "region": "Global",
                "data_source": "YAHOO",
                "metadata_source": "fallback",
            }

    if normalized in _CRYPTO_BASE_SYMBOLS:
        return {
            "name": normalized,
            "asset_type": "CRYPTO",
            "asset_class": "Crypto",
            "sector": "Digital Assets",
            "region": "Global",
            "data_source": "YAHOO",
            "metadata_source": "fallback",
        }

    if normalized.endswith("=X"):
        return {
            "name": normalized,
            "asset_type": "FOREX",
            "asset_class": "Cash",
            "sector": "FX",
            "region": "Global",
            "data_source": "YAHOO",
            "metadata_source": "fallback",
        }

    if 1 <= len(normalized) <= 6 and normalized.replace(".", "").isalpha():
        return {
            "name": normalized,
            "asset_type": "EQUITY",
            "asset_class": "US Stocks",
            "sector": None,
            "region": "US",
            "data_source": "YAHOO",
            "metadata_source": "fallback",
        }

    return None
