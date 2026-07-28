"""Tests for the landing-write dedupe, which is the pipeline's first cost control."""
import time

import common.s3_landing as sl


class _FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, Bucket, Key, Body):
        self.puts.append(Key)


def _patch(monkeypatch, previous_state):
    fake = _FakeS3()
    written = {}
    monkeypatch.setenv("LANDING_BUCKET", "test-bucket")
    monkeypatch.setattr(sl, "_s3", fake)
    monkeypatch.setattr(sl, "get_state", lambda name: previous_state)
    monkeypatch.setattr(sl, "put_state", lambda name, state: written.update(state))
    return fake, written


def test_first_pull_always_lands(monkeypatch):
    fake, written = _patch(monkeypatch, None)
    assert sl.write_raw("feodo", {"a": 1}) is not None
    assert len(fake.puts) == 1
    assert "landed_at" in written


def test_unchanged_recent_payload_is_skipped(monkeypatch):
    fake, _ = _patch(monkeypatch, None)
    key = sl.write_raw("feodo", {"a": 1})
    digest = key and True

    fake2, _ = _patch(monkeypatch, {"sha256": _digest_of({"a": 1}), "landed_at": int(time.time())})
    assert sl.write_raw("feodo", {"a": 1}) is None
    assert fake2.puts == []
    assert digest


def test_changed_payload_lands(monkeypatch):
    fake, _ = _patch(monkeypatch, {"sha256": _digest_of({"a": 1}), "landed_at": int(time.time())})
    assert sl.write_raw("feodo", {"a": 2}) is not None
    assert len(fake.puts) == 1


def test_stale_unchanged_payload_relands(monkeypatch):
    """A feed must not stay stuck if the normalizer failed on the last landed object."""
    stale = int(time.time()) - sl.MAX_SKIP_SECONDS - 1
    fake, _ = _patch(monkeypatch, {"sha256": _digest_of({"a": 1}), "landed_at": stale})
    assert sl.write_raw("feodo", {"a": 1}) is not None
    assert len(fake.puts) == 1


def test_state_without_landed_at_relands(monkeypatch):
    """State written before landed_at existed must self-heal rather than skip forever."""
    fake, _ = _patch(monkeypatch, {"sha256": _digest_of({"a": 1})})
    assert sl.write_raw("feodo", {"a": 1}) is not None
    assert len(fake.puts) == 1


def _digest_of(payload):
    import hashlib
    import json

    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
