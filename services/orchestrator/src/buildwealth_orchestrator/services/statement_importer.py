"""Parse bank/credit card CSV statements and suggest expense items for the financial profile."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


DATE_FORMATS = (
    "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%m-%d-%Y",
)

# Column name aliases for auto-detection
COLUMN_ALIASES: dict[str, set[str]] = {
    "date": {"date", "transactiondate", "transaction date", "postdate", "post date",
             "posteddate", "posted date", "booking date", "bookingdate"},
    "description": {"description", "merchant", "name", "payee", "memo",
                    "transaction description", "details", "narrative"},
    "amount": {"amount", "total", "value", "sum", "debit", "charge", "cost"},
    "category": {"category", "type", "transaction type", "classification"},
}

# Keyword-based category inference
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "housing": ["rent", "mortgage", "hoa", "property"],
    "utilities": ["electric", "gas", "water", "sewer", "utility", "power", "energy", "xcel", "comcast", "spectrum", "att", "t-mobile", "verizon"],
    "insurance": ["insurance", "geico", "state farm", "allstate", "progressive", "usaa"],
    "groceries": ["grocery", "whole foods", "trader joe", "costco", "target", "walmart", "aldi", "kroger", "safeway", "publix"],
    "dining": ["restaurant", "doordash", "ubereats", "grubhub", "mcdonald", "starbucks", "chipotle", "chick-fil"],
    "transportation": ["gas station", "shell", "chevron", "bp", "uber", "lyft", "parking", "toll"],
    "subscriptions": ["netflix", "spotify", "hulu", "disney", "apple.com/bill", "amazon prime", "youtube", "hbo", "openai", "github", "icloud"],
    "healthcare": ["pharmacy", "cvs", "walgreens", "doctor", "medical", "dental", "hospital", "urgent care"],
    "fitness": ["gym", "planet fitness", "ymca", "peloton", "fitness"],
    "shopping": ["amazon", "best buy", "home depot", "lowes", "ikea", "nordstrom"],
    "education": ["tuition", "student", "course", "udemy", "university"],
    "childcare": ["daycare", "childcare", "school", "tutor"],
    "pets": ["petco", "petsmart", "vet", "veterinary"],
}

# Descriptions that signal income rather than expenses
INCOME_KEYWORDS = ["payroll", "direct deposit", "salary", "wages", "employer", "paycheck", "ach credit", "tax refund"]


def _parse_date(raw: str) -> datetime | None:
    text = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _normalize_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def _detect_columns(headers: list[str]) -> dict[str, int]:
    """Map logical field names to column indices."""
    mapping: dict[str, int] = {}
    normalized = [_normalize_col(h) for h in headers]

    for field_name, aliases in COLUMN_ALIASES.items():
        normalized_aliases = {re.sub(r"[^a-z0-9]", "", a) for a in aliases}
        for idx, col in enumerate(normalized):
            if col in normalized_aliases:
                mapping[field_name] = idx
                break

    return mapping


def _parse_amount(raw: str) -> float | None:
    text = raw.strip().replace("$", "").replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        # Handle parenthesized negatives: (123.45) → -123.45
        if text.startswith("(") and text.endswith(")"):
            return -float(text[1:-1])
        return float(text)
    except ValueError:
        return None


def _infer_category(description: str) -> str:
    lower = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "general"


def _is_income(description: str) -> bool:
    lower = description.lower()
    if any(kw in lower for kw in INCOME_KEYWORDS):
        return True
    # Positive amounts in credit card statements are usually payments/credits, not income
    # But in bank statements, positive credits could be income
    return False


@dataclass
class ParsedTransaction:
    date: datetime | None
    description: str
    amount: float
    category: str
    raw_row: dict[str, str] = field(default_factory=dict)


@dataclass
class ExpenseSuggestion:
    label: str
    monthly_amount_usd: float
    category: str
    is_fixed: bool
    transaction_count: int
    sample_descriptions: list[str]
    source: str = "statement-import"


@dataclass
class IncomeSuggestion:
    label: str
    monthly_amount_usd: float
    source_type: str
    transaction_count: int
    is_pre_tax: bool = False


@dataclass
class StatementParseResult:
    transactions: list[ParsedTransaction]
    expense_suggestions: list[ExpenseSuggestion]
    income_suggestions: list[IncomeSuggestion]
    date_range_start: datetime | None
    date_range_end: datetime | None
    total_expenses: float
    total_income: float
    months_covered: float
    parse_errors: list[str]


def parse_statement_csv(
    content: str,
    delimiter: str = ",",
) -> StatementParseResult:
    """Parse a bank/credit card CSV and generate expense/income suggestions."""
    errors: list[str] = []
    transactions: list[ParsedTransaction] = []

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows: list[list[str]] = list(reader)

    if len(rows) < 2:
        return StatementParseResult(
            transactions=[], expense_suggestions=[], income_suggestions=[],
            date_range_start=None, date_range_end=None,
            total_expenses=0, total_income=0, months_covered=0,
            parse_errors=["CSV has fewer than 2 rows (need header + data)."],
        )

    headers = rows[0]
    col_map = _detect_columns(headers)

    if "date" not in col_map:
        errors.append(f"Could not detect a date column. Headers: {headers}")
    if "description" not in col_map:
        errors.append(f"Could not detect a description column. Headers: {headers}")
    if "amount" not in col_map:
        errors.append(f"Could not detect an amount column. Headers: {headers}")

    if "amount" not in col_map:
        return StatementParseResult(
            transactions=[], expense_suggestions=[], income_suggestions=[],
            date_range_start=None, date_range_end=None,
            total_expenses=0, total_income=0, months_covered=0,
            parse_errors=errors,
        )

    date_idx = col_map.get("date")
    desc_idx = col_map.get("description")
    amount_idx = col_map["amount"]
    cat_idx = col_map.get("category")

    for row_num, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        try:
            raw_amount = row[amount_idx] if amount_idx < len(row) else ""
            amount = _parse_amount(raw_amount)
            if amount is None:
                continue

            date = None
            if date_idx is not None and date_idx < len(row):
                date = _parse_date(row[date_idx])

            description = ""
            if desc_idx is not None and desc_idx < len(row):
                description = row[desc_idx].strip()

            category = "general"
            if cat_idx is not None and cat_idx < len(row) and row[cat_idx].strip():
                category = row[cat_idx].strip().lower()
            elif description:
                category = _infer_category(description)

            transactions.append(ParsedTransaction(
                date=date, description=description, amount=amount,
                category=category, raw_row=dict(zip(headers, row)),
            ))
        except (IndexError, ValueError) as exc:
            errors.append(f"Row {row_num}: {exc}")

    if not transactions:
        return StatementParseResult(
            transactions=[], expense_suggestions=[], income_suggestions=[],
            date_range_start=None, date_range_end=None,
            total_expenses=0, total_income=0, months_covered=0,
            parse_errors=errors or ["No valid transactions found."],
        )

    return build_statement_result(transactions, parse_errors=errors)


def build_statement_result(
    transactions: list[ParsedTransaction],
    *,
    parse_errors: list[str] | None = None,
) -> StatementParseResult:
    """Aggregate parsed transactions into expense/income suggestions.

    Shared by every extraction path (CSV today, LLM vision extraction of
    screenshots) so a transaction is a transaction regardless of how it
    entered the app.
    """
    errors = list(parse_errors or [])

    # Date range
    dated = [t for t in transactions if t.date]
    date_start = min(t.date for t in dated) if dated else None
    date_end = max(t.date for t in dated) if dated else None
    if date_start and date_end:
        months_covered = max(1.0, (date_end - date_start).days / 30.44)
    else:
        months_covered = 1.0

    # Split expenses vs income
    expense_txns: list[ParsedTransaction] = []
    income_txns: list[ParsedTransaction] = []

    for t in transactions:
        if _is_income(t.description):
            income_txns.append(t)
        elif t.amount < 0:
            # Negative = charge/expense in most bank formats
            expense_txns.append(t)
        elif t.amount > 0 and _is_income(t.description):
            income_txns.append(t)
        else:
            # Positive amounts: could be expense (credit card) or credit (bank)
            # Credit card statements: charges are positive
            # Bank statements: charges are negative
            # Heuristic: if most amounts are positive, treat positive as expenses
            expense_txns.append(t)

    # Group expenses by normalized description
    expense_groups: dict[str, list[ParsedTransaction]] = defaultdict(list)
    for t in expense_txns:
        key = _normalize_merchant(t.description) if t.description else "unknown"
        expense_groups[key].append(t)

    # Generate expense suggestions
    expense_suggestions: list[ExpenseSuggestion] = []
    for key, group in sorted(expense_groups.items(), key=lambda x: sum(abs(t.amount) for t in x[1]), reverse=True):
        total = sum(abs(t.amount) for t in group)
        monthly = total / months_covered
        if monthly < 5:
            continue

        count = len(group)
        is_recurring = count >= 2 and months_covered >= 1.5
        categories = [t.category for t in group]
        top_category = max(set(categories), key=categories.count) if categories else "general"
        samples = list({t.description for t in group if t.description})[:3]
        label = _clean_label(samples[0]) if samples else key.title()

        expense_suggestions.append(ExpenseSuggestion(
            label=label,
            monthly_amount_usd=round(monthly, 2),
            category=top_category,
            is_fixed=is_recurring,
            transaction_count=count,
            sample_descriptions=samples,
        ))

    # Generate income suggestions
    income_suggestions: list[IncomeSuggestion] = []
    if income_txns:
        income_groups: dict[str, list[ParsedTransaction]] = defaultdict(list)
        for t in income_txns:
            key = _normalize_merchant(t.description) if t.description else "income"
            income_groups[key].append(t)

        for key, group in income_groups.items():
            total = sum(abs(t.amount) for t in group)
            monthly = total / months_covered
            if monthly < 10:
                continue
            samples = list({t.description for t in group if t.description})[:2]
            label = _clean_label(samples[0]) if samples else key.title()
            income_suggestions.append(IncomeSuggestion(
                label=label,
                monthly_amount_usd=round(monthly, 2),
                source_type="salary" if any(kw in key for kw in ["payroll", "salary", "employer"]) else "other",
                transaction_count=len(group),
            ))

    total_expenses = sum(s.monthly_amount_usd for s in expense_suggestions)
    total_income = sum(s.monthly_amount_usd for s in income_suggestions)

    return StatementParseResult(
        transactions=transactions,
        expense_suggestions=expense_suggestions,
        income_suggestions=income_suggestions,
        date_range_start=date_start,
        date_range_end=date_end,
        total_expenses=round(total_expenses, 2),
        total_income=round(total_income, 2),
        months_covered=round(months_covered, 1),
        parse_errors=errors,
    )


def _normalize_merchant(description: str) -> str:
    """Collapse merchant names to a consistent key (strip trailing numbers, IDs)."""
    text = description.strip()
    # Remove trailing reference numbers, dates, locations
    text = re.sub(r"\s*#?\d{4,}.*$", "", text)
    text = re.sub(r"\s+\d{2}/\d{2}$", "", text)
    text = re.sub(r"\s+(NY|CA|TX|IL|FL|WA|MN|CO|OH|GA|NC|PA|MA|AZ|VA|NJ|OR)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()[:60]


def _clean_label(description: str) -> str:
    """Create a human-readable label from a merchant description."""
    text = description.strip()
    text = re.sub(r"\s*#?\d{4,}.*$", "", text)
    text = re.sub(r"\s+\d{2}/\d{2}$", "", text)
    text = re.sub(r"\s+(NY|CA|TX|IL|FL|WA|MN|CO|OH|GA|NC|PA|MA|AZ|VA|NJ|OR)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 40:
        text = text[:40].rsplit(" ", 1)[0]
    return text.title() if text else "Unknown"
