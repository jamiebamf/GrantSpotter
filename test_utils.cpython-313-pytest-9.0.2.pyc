from datetime import date
from app.utils import fingerprint, normalise_text


def test_normalise_text():
    assert normalise_text("  Asda Foundation – Grant! ") == "asda foundation grant"


def test_fingerprint_stable():
    a = fingerprint("Test Grant", "Test Fund", date(2027, 1, 1), 5000, "https://example.org/apply")
    b = fingerprint("test-grant", "TEST FUND", date(2027, 1, 1), 5000.0, "https://www.example.org/apply")
    assert a == b
