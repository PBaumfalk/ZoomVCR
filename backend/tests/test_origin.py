"""ZOOMVCR_PUBLIC_ORIGIN: which values the API accepts and how it compares them with the browser's Origin."""
import pytest

from zoomvcr.config import normalize_origin, origin_allowed


@pytest.mark.parametrize("value", [
    "https://vcr.example.com", "https://vcr.example.com/", "https://vcr.example.com:8443",
    "http://localhost", "http://localhost/", "http://localhost:8080", "http://127.0.0.1:8000",
])
def test_allowed(value):
    assert origin_allowed(value)


@pytest.mark.parametrize("value", [
    "", "https://", "http://vcr.example.com", "http://localhost.evil.example", "http://localhost:8080/pfad",
    "http://192.168.1.10", "ftp://localhost",
])
def test_rejected(value):
    assert not origin_allowed(value)


@pytest.mark.parametrize("value, browser", [
    ("http://localhost:80", "http://localhost"),        # Browser lassen den Standardport weg
    ("https://vcr.example.com:443/", "https://vcr.example.com"),
    ("http://localhost:8080/", "http://localhost:8080"),
])
def test_normalized_like_the_browser(value, browser):
    assert normalize_origin(value) == browser
