from __future__ import annotations

import base64
import socket

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
