"""The sandbox-only guard (CONTRACT.md §1.6) must reject production hosts."""

import pytest

from mtd_agent.config import SANDBOX_HOST, assert_sandbox


def test_sandbox_url_is_accepted():
    url = f"https://{SANDBOX_HOST}"
    assert assert_sandbox(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.service.hmrc.gov.uk",          # production
        "https://api.service.hmrc.gov.uk/vat",       # production w/ path
        "http://evil.example.com",
        "https://test-api.service.hmrc.gov.uk.evil.com",  # lookalike host
    ],
)
def test_non_sandbox_urls_are_rejected(url):
    with pytest.raises(RuntimeError):
        assert_sandbox(url)
