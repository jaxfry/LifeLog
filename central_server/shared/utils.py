import re

def extract_summary_from_reflection(reflection: str) -> str:
    """
    Extracts the <summary>...</summary> section from the LLM Solace reflection.
    Returns an empty string if not found.
    """
    if not reflection:
        return ""
    match = re.search(r"<summary>(.*?)</summary>", reflection, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""
