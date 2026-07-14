from __future__ import annotations

import base64
import socket
import threading

import harness.browser as browser


def test_search_redirect_unwraps_bing_and_duckduckgo():
    target = "https://example.com/path?q=1"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    assert browser._unwrap(
        f"https://www.bing.com/ck/a?u=a1{encoded}") == target
    assert browser._unwrap(
        "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fx") == \
        "https://example.com/x"


def test_public_host_validation_rejects_mixed_or_private_dns(
        monkeypatch):
    browser._PUBLIC_HOST_CACHE.clear()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
    ])
    assert browser._host_is_public("example.test")
    # Cached results remain stable for a browser session.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [])
    assert browser._host_is_public("example.test")

    browser._PUBLIC_HOST_CACHE.clear()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    ])
    assert not browser._host_is_public("mixed.test")
    assert not browser._host_is_public("localhost")


def test_reddit_formatter_handles_posts_listings_and_malformed_data():
    thread = [{"data": {"children": [{"data": {
        "title": "Post", "subreddit": "test", "author": "a",
        "score": 5, "num_comments": 1, "selftext": "Body",
    }}]}}, {"data": {"children": [{"kind": "t1", "data": {
        "author": "b", "score": 3, "body": "Comment", "replies": "",
    }}]}}]
    formatted = browser._format_reddit(thread)
    assert "# Post" in formatted and "Comment" in formatted

    listing = {"data": {"children": [{"kind": "t3", "data": {
        "title": "Listed", "subreddit": "test", "score": 2,
        "num_comments": 0, "permalink": "/r/test/1",
    }}]}}
    assert "Listed" in browser._format_reddit(listing)
    assert "0 posts" in browser._format_reddit([{"unexpected": True}])


def test_browser_control_rejects_unsafe_navigation_before_starting_worker():
    assert browser.control("open", url="http://localhost:8000").startswith(
        "Error: browser navigation only permits public hosts")
    assert browser.control("click", ref="made-up").startswith(
        "Error: browser ref must look like e1")


def test_browser_control_state_is_compact_and_ref_addressable():
    report = browser._format_control_state({
        "title": "Example", "url": "https://example.com/",
        "elements": [{"ref": "e1", "role": "button", "name": "Continue",
                      "value": "", "disabled": False}],
        "text": "Visible content",
    })
    assert "e1 button 'Continue'" in report
    assert "Visible content" in report
    assert "secret ? '[redacted]'" in browser.CONTROL_STATE_JS
    redacted = browser._redact_control_url(
        "https://example.com/callback?code=abc&view=inbox#access_token=xyz")
    assert "abc" not in redacted and "xyz" not in redacted
    assert "view=inbox" in redacted


def test_browser_worker_submission_honors_an_already_stopped_turn(
        monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(browser._worker, "_ensure_thread", lambda: None)
    result = browser.control("state", stop_event=stop)
    assert result == "Error: browser action stopped by user."
