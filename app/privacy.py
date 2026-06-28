import re
from typing import Iterable


PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
LONG_ID_PATTERN = re.compile(r"\b[A-Z0-9]{10,}\b", re.IGNORECASE)
ACCOUNT_DIGITS_PATTERN = re.compile(r"\b\d{8,}\b")


def mask_identifier(value: str, visible_prefix: int = 2, visible_suffix: int = 2) -> str:
    text = str(value or "").strip()
    if len(text) <= visible_prefix + visible_suffix:
        return "*" * len(text)
    return f"{text[:visible_prefix]}{'*' * (len(text) - visible_prefix - visible_suffix)}{text[-visible_suffix:]}"


def mask_filename(filename: str) -> str:
    if not filename:
        return "statement"
    if "." in filename:
        stem, ext = filename.rsplit(".", 1)
        return f"statement-{abs(hash(stem)) % 10000:04d}.{ext.lower()}"
    return f"statement-{abs(hash(filename)) % 10000:04d}"


def mask_free_text(text: str) -> str:
    if not text:
        return text

    masked = str(text)
    masked = EMAIL_PATTERN.sub("<masked-email>", masked)
    masked = PAN_PATTERN.sub("<masked-pan>", masked)
    masked = ACCOUNT_DIGITS_PATTERN.sub("<masked-id>", masked)

    def _mask_named_value(pattern: str, replacement_label: str) -> None:
        nonlocal masked
        masked = re.sub(pattern, replacement_label, masked, flags=re.IGNORECASE)

    _mask_named_value(r"(client\s*name\s*[:=-]\s*)([^\n,]+)", r"\1<masked-client>")
    _mask_named_value(r"(client\s*code\s*[:=-]\s*)([^\n,]+)", r"\1<masked-code>")
    _mask_named_value(r"(username\s*[:=-]\s*)([^\n,]+)", r"\1<masked-user>")
    _mask_named_value(r"(pan\s*(?:number)?\s*[:=-]\s*)([^\n,]+)", r"\1<masked-pan>")
    _mask_named_value(r"(account\s*(?:number|id)?\s*[:=-]\s*)([^\n,]+)", r"\1<masked-account>")
    _mask_named_value(r"(folio\s*(?:number|id)?\s*[:=-]\s*)([^\n,]+)", r"\1<masked-folio>")
    _mask_named_value(r"(demat\s*(?:number|id)?\s*[:=-]\s*)([^\n,]+)", r"\1<masked-demat>")

    masked = re.sub(r"\b[A-Z]{2}[A-Z0-9]{8,}\b", "<masked-id>", masked, flags=re.IGNORECASE)

    tokens = masked.split()
    softened: list[str] = []
    for token in tokens:
        bare = token.strip(",;:()[]{}")
        if LONG_ID_PATTERN.fullmatch(bare) and sum(ch.isdigit() for ch in bare) >= 4:
            softened.append(token.replace(bare, mask_identifier(bare)))
        else:
            softened.append(token)
    return " ".join(softened)


def safe_user_visible_error(error: Exception | str) -> str:
    text = str(error or "").strip()
    lowered = text.lower()
    if "missing required column" in lowered:
        column_name = text.split(":", 1)[-1].split(".", 1)[0].strip() if ":" in text else "required field"
        return f"Validation failed: the sheet is missing the required `{column_name}` field. Review the column mapping and upload again."
    return mask_free_text(text)


def redact_sample_value(column_name: str, value) -> object:
    """Mask sensitive Excel cell values before they are ever sent to an LLM."""
    if value is None:
        return value
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return text

    col = (column_name or "").strip().lower()
    if any(token in col for token in ["client", "investor", "account holder", "holder name", "full name"]):
        return "<REDACTED_CLIENT>"
    if any(token in col for token in ["code", "account", "id", "pan", "dp", "demat", "folio", "email", "phone", "mobile"]):
        return "<REDACTED_ID>"
    if any(token in col for token in ["symbol", "ticker", "stock", "scrip", "company", "instrument", "description", "name"]):
        return "<REDACTED_ASSET>"
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{8,}", text.upper()):
        return "<REDACTED_ID>"
    if "@" in text:
        return "<REDACTED_EMAIL>"
    if len(text) > 12 and sum(ch.isdigit() for ch in text) >= 6:
        return "<REDACTED_VALUE>"
    return text[:35] + "..." if len(text) > 35 else text


def build_asset_alias_map(symbols: Iterable[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    seen = []
    for symbol in symbols:
        cleaned = str(symbol).strip()
        if cleaned and cleaned not in aliases:
            seen.append(cleaned)
            aliases[cleaned] = f"ASSET_{len(seen):02d}"
    return aliases


def alias_text(text: str, alias_map: dict[str, str]) -> str:
    aliased = text
    for original, alias in sorted(alias_map.items(), key=lambda item: len(item[0]), reverse=True):
        aliased = aliased.replace(original, alias)
    return aliased


def restore_alias_text(text: str, alias_map: dict[str, str]) -> str:
    restored = text
    for original, alias in sorted(alias_map.items(), key=lambda item: len(item[1]), reverse=True):
        restored = restored.replace(alias, original)
    return restored


def restore_alias_list(items: list[str], alias_map: dict[str, str]) -> list[str]:
    return [restore_alias_text(item, alias_map) for item in items]
