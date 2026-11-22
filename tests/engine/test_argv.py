from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from cloudripr.engine.argv import (
    ENGINE_KEYS,
    NAMING_KEYS,
    base_args,
    download_args,
    flag_args,
    naming_signature,
    validate_icloudpd_values,
)
from cloudripr.store.account_store import Account
from cloudripr.store.models import Policy


FIXTURE = Path(__file__).parent.parent / "fixtures" / "policies" / "icloud.toml"

# Produced by the CURRENT app (the old argv builder) for the user's
# real policy on 2026-10-14, plus the resolved --library it appends at run time.
OLD_ARGV = [
    "--username",
    "you@example.com",
    "--directory",
    "/downloads",
    "--mfa-provider",
    "console",
    "--password-provider",
    "console",
    "--domain",
    "com",
    "--folder-structure",
    "{:%Y/%m}",
    "--size",
    "original",
    "--live-photo-size",
    "original",
    "--align-raw",
    "original",
    "--live-photo-mov-filename-policy",
    "suffix",
    "--file-match-policy",
    "name-size-dedup-with-suffix",
    "--log-level",
    "info",
    "--library",
    "SharedSync-TEST",
]
NAMING_FLAGS = {
    "--directory",
    "--folder-structure",
    "--size",
    "--live-photo-size",
    "--align-raw",
    "--force-size",
    "--live-photo-mov-filename-policy",
    "--file-match-policy",
    "--keep-unicode-in-filenames",
    "--library",
}


def pairs(argv: list[str], wanted: set[str]) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for i, tok in enumerate(argv):
        if tok in wanted:
            nxt = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
            out.append((tok, nxt))
    return out


def load_policy() -> Policy:
    return Policy.model_validate(tomllib.loads(FIXTURE.read_text()))


def test_golden_naming_flags_unchanged() -> None:
    """Spec §3: the user's ~400 GB library must keep the exact same names."""
    policy = load_policy()
    account = Account(apple_id=policy.username, domain="com")
    new = [
        *base_args(account, Path("/data/icloud-session")),
        *download_args(policy, library="SharedSync-TEST"),
    ]
    assert pairs(new, NAMING_FLAGS) == pairs(OLD_ARGV, NAMING_FLAGS)
    old_flags = {t for t in OLD_ARGV if t.startswith("--")}
    new_flags = {t for t in new if t.startswith("--")}
    assert old_flags <= new_flags
    assert new_flags - old_flags == {"--cookie-directory"}


def test_base_args() -> None:
    assert base_args(Account(apple_id="me@x.com", domain="cn"), Path("/s")) == [
        "--username",
        "me@x.com",
        "--domain",
        "cn",
        "--cookie-directory",
        "/s",
        "--password-provider",
        "console",
        "--mfa-provider",
        "console",
    ]


def test_engine_keys_never_come_from_policy() -> None:
    hostile = dict.fromkeys(ENGINE_KEYS, True) | {
        "cookie_directory": "/elsewhere",
        "domain": "cn",
        "log_level": "debug",
    }
    assert flag_args(hostile) == []


def test_flag_translation() -> None:
    assert flag_args(
        {"skip_videos": True, "skip_photos": False, "size": ["original", "medium"], "recent": 10}
    ) == [
        "--skip-videos",
        "--size",
        "original",
        "--size",
        "medium",
        "--recent",
        "10",
    ]


def test_download_args_library_and_dry_run() -> None:
    policy = load_policy()
    args = download_args(policy, library=None, dry_run=True)
    assert args[:4] == ["--directory", "/downloads", "--log-level", "info"]
    assert "--library" not in args
    assert args[-1] == "--dry-run"
    legacy = policy.model_copy(
        update={"library_kind": None, "icloudpd": {**policy.icloudpd, "library": "Custom"}}
    )
    assert download_args(legacy, library=None)[-2:] == ["--library", "Custom"]
    own_dry = policy.model_copy(update={"icloudpd": {**policy.icloudpd, "dry_run": True}})
    assert download_args(own_dry, library=None).count("--dry-run") == 1


def test_download_args_recent_keeps_the_policys_own_limit() -> None:
    policy = load_policy()
    args = download_args(policy, library=None, recent=1000)
    assert args[args.index("--recent") + 1] == "1000"
    own = policy.model_copy(update={"icloudpd": {**policy.icloudpd, "recent": 50}})
    args = download_args(own, library=None, recent=1000)
    assert args.count("--recent") == 1
    assert args[args.index("--recent") + 1] == "50"


def test_naming_signature_normalises_false_and_missing() -> None:
    policy = load_policy()
    sig = naming_signature(policy)
    assert sig["directory"] == "/downloads"
    assert sig["library_kind"] == "shared"
    assert sig["force_size"] is None  # False and missing are the same argv
    assert set(sig) == NAMING_KEYS | {"directory", "library_kind"}
    trimmed = policy.model_copy(
        update={"icloudpd": {k: v for k, v in policy.icloudpd.items() if k != "force_size"}}
    )
    assert naming_signature(trimmed) == sig


def test_validate_rejects_non_bool_for_bool_keys() -> None:
    with pytest.raises(ValueError, match="skip_videos must be true or false"):
        validate_icloudpd_values({"skip_videos": "yes"})


def test_validate_rejects_leading_dash_in_scalar() -> None:
    with pytest.raises(ValueError, match="can't start with '-'"):
        validate_icloudpd_values({"size": "--injected"})


def test_validate_rejects_leading_dash_in_list_item() -> None:
    with pytest.raises(ValueError, match="can't start with '-'"):
        validate_icloudpd_values({"size": ["original", "--injected"]})


def test_validate_rejects_none_and_dict() -> None:
    with pytest.raises(ValueError, match="has an unsupported value"):
        validate_icloudpd_values({"size": None})
    with pytest.raises(ValueError, match="has an unsupported value"):
        validate_icloudpd_values({"size": {"nested": "dict"}})


def test_flag_args_validates() -> None:
    with pytest.raises(ValueError, match="must be true or false"):
        flag_args({"skip_videos": "invalid"})


def test_policy_validates_icloudpd_values() -> None:
    with pytest.raises(ValueError, match="must be true or false"):
        Policy(
            name="p",
            username="u@x.com",
            directory="/tmp",
            cron="0 3 * * *",
            icloudpd={"skip_videos": "invalid"},
        )


def test_validate_rejects_unsupported_types() -> None:
    with pytest.raises(ValueError, match="has an unsupported value"):
        validate_icloudpd_values({"size": {1, 2}})
