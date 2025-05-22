import pytest
from LifeLog.enrichment.example import _extract_json

@pytest.mark.parametrize("input_txt, expected_len", [
    ("[ {\"a\":1} ]", 1),
    ("```json\n[1,2,3]\n```", 3),
])
def test_extract_json(input_txt, expected_len):
    arr = _extract_json(input_txt)
    assert isinstance(arr, list)
    assert len(arr) == expected_len
