from app.extractor import deterministic_extract


def test_deterministic_extract():
    text = """Test Community Grant
Funding organisation
Example Foundation
Location
Yorkshire and the Humber
Who can apply
Non-profit, Local authority
How much you can get
From £1,000 to £10,000
Opening date
1 August 2026
Closing date
30 September 2026
This programme supports community development and youth services across Yorkshire.
"""
    grant = deterministic_extract("Test Community Grant - Find a grant", text, "https://example.org/grant")
    assert grant.funder_name == "Example Foundation"
    assert grant.maximum_amount == 10000
    assert grant.deadline.isoformat() == "2026-09-30"
