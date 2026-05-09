from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.asset_metadata_seed import infer_asset_metadata
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


class AssetRegistry:
    """Native asset registry assembled from portfolio metadata, holdings, prices, and watchlist."""

    def __init__(self, portfolio_store: PortfolioStore):
        self._portfolio_store = portfolio_store

    def search(self, query: str = "", limit: int = 100) -> dict[str, Any]:
        q = _clean_text(query).lower()
        bounded_limit = max(1, min(int(limit), 500))
        items = [item for item in self._items() if self._matches(item, q)]
        items.sort(key=self._sort_key)
        return {
            "query": query,
            "count": len(items),
            "items": items[:bounded_limit],
        }

    def detail(self, symbol: str) -> dict[str, Any] | None:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return None
        for item in self._items():
            if item.get("symbol") == normalized_symbol:
                return item
        metadata = infer_asset_metadata(normalized_symbol)
        if metadata:
            return self._build_item(
                symbol=normalized_symbol,
                metadata=dict(metadata),
                holding={},
                manual_price={},
                watchlist_item={},
            )
        return None

    def update_metadata(self, symbol: str, updates: dict[str, Any]) -> dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")
        allowed = {
            "name",
            "asset_type",
            "asset_class",
            "sector",
            "region",
            "data_source",
            "metadata_source",
            "expense_ratio",
            "is_custom_asset",
            "valuation_method",
        }
        cleaned = {key: value for key, value in updates.items() if key in allowed}
        if not cleaned:
            raise ValueError("At least one metadata field is required.")
        self._portfolio_store.upsert_asset_metadata(normalized_symbol, cleaned)
        detail = self.detail(normalized_symbol)
        if not detail:
            raise ValueError("Asset could not be loaded after update.")
        return detail

    def _items(self) -> list[dict[str, Any]]:
        holdings_payload = self._portfolio_store.get_holdings()
        holdings_by_symbol = holdings_payload.get("holdings_by_symbol")
        if not isinstance(holdings_by_symbol, dict):
            holdings_by_symbol = {}
        metadata_map = self._portfolio_store.get_asset_metadata_map()
        manual_payload = self._portfolio_store.get_manual_prices()
        manual_prices = manual_payload.get("by_symbol") if isinstance(manual_payload, dict) else {}
        if not isinstance(manual_prices, dict):
            manual_prices = {}
        watchlist_items = self._portfolio_store.list_watchlist()
        watchlist_by_symbol = {
            _normalize_symbol(item.get("symbol")): item
            for item in watchlist_items
            if isinstance(item, dict) and _normalize_symbol(item.get("symbol"))
        }

        symbols: set[str] = set()
        for source in (holdings_by_symbol, metadata_map, manual_prices, watchlist_by_symbol):
            symbols.update(_normalize_symbol(symbol) for symbol in source.keys())
        symbols.discard("")

        return [
            self._build_item(
                symbol=symbol,
                metadata=metadata_map.get(symbol) if isinstance(metadata_map.get(symbol), dict) else {},
                holding=holdings_by_symbol.get(symbol) if isinstance(holdings_by_symbol.get(symbol), dict) else {},
                manual_price=manual_prices.get(symbol) if isinstance(manual_prices.get(symbol), dict) else {},
                watchlist_item=watchlist_by_symbol.get(symbol) if isinstance(watchlist_by_symbol.get(symbol), dict) else {},
            )
            for symbol in symbols
        ]

    def _build_item(
        self,
        *,
        symbol: str,
        metadata: dict[str, Any],
        holding: dict[str, Any],
        manual_price: dict[str, Any],
        watchlist_item: dict[str, Any],
    ) -> dict[str, Any]:
        inferred = infer_asset_metadata(symbol) or {}
        merged = self._merge_records(inferred, metadata, holding)
        current_price = holding.get("current_price")
        if current_price is None and manual_price:
            current_price = manual_price.get("price")
        current_value = holding.get("current_value")
        quality = self._quality(symbol=symbol, merged=merged, holding=holding, manual_price=manual_price)
        held = bool(holding)
        watchlisted = bool(watchlist_item)
        custom = bool(merged.get("is_custom_asset")) or str(merged.get("data_source") or "").upper() == "MANUAL"
        tags = [
            label
            for label, enabled in (
                ("Held", held),
                ("Watchlist", watchlisted),
                ("Custom", custom),
                ("Manual price", bool(manual_price)),
            )
            if enabled
        ]
        return {
            "symbol": symbol,
            "name": _clean_text(merged.get("name")) or symbol,
            "asset_type": _clean_text(merged.get("asset_type")) or None,
            "asset_class": _clean_text(merged.get("asset_class")) or None,
            "sector": _clean_text(merged.get("sector")) or None,
            "region": _clean_text(merged.get("region")) or None,
            "data_source": _clean_text(merged.get("data_source")) or None,
            "metadata_source": _clean_text(merged.get("metadata_source")) or None,
            "expense_ratio": _safe_float(merged.get("expense_ratio")),
            "held": held,
            "watchlisted": watchlisted,
            "custom": custom,
            "manual_price": bool(manual_price),
            "quantity": _safe_float(holding.get("quantity")),
            "current_price": _safe_float(current_price),
            "current_value": _safe_float(current_value),
            "cost_basis": _safe_float(holding.get("cost_basis")),
            "accounts": holding.get("accounts") if isinstance(holding.get("accounts"), list) else [],
            "price_source": _clean_text(holding.get("price_source")) or ("MANUAL" if manual_price else None),
            "valuation_method": _clean_text(merged.get("valuation_method")) or None,
            "tags": tags,
            "quality_status": quality["status"],
            "quality_label": quality["label"],
            "review_reasons": quality["reasons"],
            "watchlist_note": _clean_text(watchlist_item.get("note")) or None,
            "thesis": _clean_text(watchlist_item.get("thesis")) or None,
        }

    @staticmethod
    def _merge_records(*records: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for record in records:
            for key, value in record.items():
                if value is None or value == "":
                    continue
                merged[key] = value
        return merged

    @staticmethod
    def _quality(
        *,
        symbol: str,
        merged: dict[str, Any],
        holding: dict[str, Any],
        manual_price: dict[str, Any],
    ) -> dict[str, Any]:
        reasons: list[str] = []
        if not _clean_text(merged.get("name")):
            reasons.append("Name is missing.")
        if not _clean_text(merged.get("asset_class")):
            reasons.append("Asset class is missing.")
        if not _clean_text(merged.get("asset_type")):
            reasons.append("Asset type is missing.")
        if not symbol:
            reasons.append("Symbol is missing.")
        metadata_missing = bool(reasons)

        held = bool(holding)
        has_value = _safe_float(holding.get("current_value")) is not None
        has_price = _safe_float(holding.get("current_price")) is not None or bool(manual_price)
        if held and not (has_value or has_price):
            reasons.append("Price or value is missing.")

        if metadata_missing:
            status = "needs_review"
            label = "Needs review"
        elif reasons:
            status = "unpriced"
            label = "Needs price"
        else:
            status = "ready"
            label = "Ready"
        return {"status": status, "label": label, "reasons": reasons}

    @staticmethod
    def _matches(item: dict[str, Any], query: str) -> bool:
        if not query:
            return True
        haystack = " ".join(
            _clean_text(item.get(key)).lower()
            for key in ("symbol", "name", "asset_type", "asset_class", "sector", "region")
        )
        return query in haystack

    @staticmethod
    def _sort_key(item: dict[str, Any]) -> tuple[int, int, float, str]:
        status_rank = {"needs_review": 0, "unpriced": 1, "ready": 2}.get(str(item.get("quality_status")), 3)
        relationship_rank = (
            0
            if item.get("held") or item.get("watchlisted") or item.get("custom") or item.get("manual_price")
            else 1
        )
        value = _safe_float(item.get("current_value")) or 0.0
        return (status_rank, relationship_rank, -value, str(item.get("symbol") or ""))
