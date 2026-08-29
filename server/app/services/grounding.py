import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class GroundingMatch:
    char_start: int
    char_end: int
    matched_text: str
    method: str
    score: float


def align_evidence_quote(
    source_text: str,
    quote: str,
    *,
    allow_fuzzy: bool = True,
    fuzzy_threshold: float = 0.88,
) -> GroundingMatch | None:
    """Locate a quote in source text while preserving original character offsets."""
    cleaned = quote.strip()
    if not cleaned:
        return None

    direct_start = source_text.casefold().find(cleaned.casefold())
    if direct_start >= 0:
        return GroundingMatch(
            char_start=direct_start,
            char_end=direct_start + len(cleaned),
            matched_text=source_text[direct_start : direct_start + len(cleaned)],
            method="exact",
            score=1.0,
        )

    tokens = [token for token in re.findall(r"\S+", cleaned) if token]
    if tokens:
        pattern = r"\s+".join(re.escape(token) for token in tokens)
        normalized_match = re.search(pattern, source_text, flags=re.IGNORECASE)
        if normalized_match:
            return GroundingMatch(
                char_start=normalized_match.start(),
                char_end=normalized_match.end(),
                matched_text=normalized_match.group(0),
                method="whitespace_normalized",
                score=1.0,
            )

    if not allow_fuzzy:
        return None
    return _fuzzy_token_window(source_text, cleaned, fuzzy_threshold)


def _fuzzy_token_window(
    source_text: str,
    quote: str,
    threshold: float,
) -> GroundingMatch | None:
    source_tokens = list(re.finditer(r"\S+", source_text))
    quote_tokens = re.findall(r"\S+", quote)
    if not source_tokens or not quote_tokens:
        return None
    target_size = len(quote_tokens)
    minimum = max(1, int(target_size * 0.8))
    maximum = min(len(source_tokens), max(minimum, int(target_size * 1.2) + 1))
    best: GroundingMatch | None = None
    normalized_quote = " ".join(quote.casefold().split())
    for size in range(minimum, maximum + 1):
        for start_index in range(0, len(source_tokens) - size + 1):
            start = source_tokens[start_index].start()
            end = source_tokens[start_index + size - 1].end()
            candidate = source_text[start:end]
            score = SequenceMatcher(
                None,
                normalized_quote,
                " ".join(candidate.casefold().split()),
            ).ratio()
            if score >= threshold and (best is None or score > best.score):
                best = GroundingMatch(start, end, candidate, "fuzzy", score)
    return best
