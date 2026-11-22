"""icloudpd argument building."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from cloudripr.store.account_store import Account
    from cloudripr.store.models import Policy


# Snake_case keys permitted inside Policy.icloudpd (moved from the old config builder).
ALLOWED_ICLOUDPD_KEYS: frozenset[str] = frozenset(
    {
        "album",
        "size",
        "skip_videos",
        "skip_live_photos",
        "auth_only",
        "recent",
        "until_found",
        "xmp_sidecar",
        "auto_delete",
        "folder_structure",
        "set_exif_datetime",
        "smtp_username",
        "smtp_password",
        "smtp_host",
        "smtp_port",
        "smtp_no_tls",
        "notification_email",
        "notification_email_from",
        "notification_script",
        "delete_after_download",
        "keep_icloud_recent_days",
        "dry_run",
        "skip_photos",
        "skip_created_before",
        "skip_created_after",
        "live_photo_size",
        "cookie_directory",
        "list_albums",
        "library",
        "list_libraries",
        "force_size",
        "keep_unicode_in_filenames",
        "file_match_policy",
        "live_photo_mov_filename_policy",
        "align_raw",
        "log_level",
        "domain",
        "no_progress_bar",
        "only_print_filenames",
        "use_os_locale",
        "watch_with_interval",
        "threads_num",
    }
)

# Controlled by the engine; never forwarded from a policy. cookie_directory and
# domain are account-level; the rest would break unattended parsing or our hook.
ENGINE_KEYS: frozenset[str] = frozenset(
    {
        "cookie_directory",
        "domain",
        "auth_only",
        "list_albums",
        "list_libraries",
        "dry_run",
        "log_level",
        "library",
        "notification_script",
        "smtp_username",
        "smtp_password",
        "smtp_host",
        "smtp_port",
        "smtp_no_tls",
        "notification_email",
        "notification_email_from",
        "only_print_filenames",
        "watch_with_interval",
    }
)

# Decide where a file lands and what it is called. Locked after a run.
NAMING_KEYS: frozenset[str] = frozenset(
    {
        "folder_structure",
        "size",
        "live_photo_size",
        "align_raw",
        "force_size",
        "live_photo_mov_filename_policy",
        "file_match_policy",
        "keep_unicode_in_filenames",
    }
)

# Store-true boolean flags: must have bool values.
BOOL_KEYS: frozenset[str] = frozenset(
    {
        "skip_videos",
        "skip_live_photos",
        "auth_only",
        "xmp_sidecar",
        "auto_delete",
        "set_exif_datetime",
        "smtp_no_tls",
        "delete_after_download",
        "dry_run",
        "skip_photos",
        "list_albums",
        "list_libraries",
        "force_size",
        "keep_unicode_in_filenames",
        "no_progress_bar",
        "only_print_filenames",
        "use_os_locale",
    }
)


def validate_icloudpd_values(icloudpd: Mapping[str, Any]) -> None:
    """Validate policy.icloudpd values to prevent argument injection.

    Raises ValueError if:
    - A BOOL_KEYS value is not a bool.
    - Any value (or list item) is bool/None/dict.
    - Any value (or list item) str representation starts with "-".
    """
    for key, value in icloudpd.items():
        if key in BOOL_KEYS:
            if not isinstance(value, bool):
                msg = f"{key} must be true or false"
                raise ValueError(msg)
        elif isinstance(value, (bool, type(None), dict)):
            msg = f"{key} has an unsupported value"
            raise ValueError(msg)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (bool, type(None), dict)) or str(item).startswith("-"):
                    msg = (
                        f"{key} can't start with '-'"
                        if isinstance(item, str) and str(item).startswith("-")
                        else f"{key} has an unsupported value"
                    )
                    raise ValueError(msg)
        elif isinstance(value, (str, int, float)):
            if str(value).startswith("-"):
                msg = f"{key} can't start with '-'"
                raise ValueError(msg)
        else:
            msg = f"{key} has an unsupported value"
            raise ValueError(msg)


def base_args(account: Account, session_dir: Path) -> list[str]:
    """Generate base arguments for icloudpd from account info."""
    return [
        "--username",
        account.apple_id,
        "--domain",
        account.domain,
        "--cookie-directory",
        str(session_dir),
        "--password-provider",
        "console",
        "--mfa-provider",
        "console",
    ]


def flag_args(icloudpd: Mapping[str, Any]) -> list[str]:
    """bool True → --flag; False → omitted; list → repeated flag; other → --flag value."""
    # Validate only keys that won't be filtered by ENGINE_KEYS
    policy_values = {k: v for k, v in icloudpd.items() if k not in ENGINE_KEYS}
    validate_icloudpd_values(policy_values)
    args: list[str] = []
    for key, value in icloudpd.items():
        if key in ENGINE_KEYS:
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                args.append(flag)
        elif isinstance(value, list):
            for item in value:
                args += [flag, str(item)]
        else:
            args += [flag, str(value)]
    return args


def download_args(
    policy: Policy, *, library: str | None, dry_run: bool = False, recent: int | None = None
) -> list[str]:
    """Generate download arguments from policy.

    recent limits this run to the newest photos, unless the policy already does.
    """
    args = ["--directory", str(policy.directory), "--log-level", "info"]
    args += flag_args(policy.icloudpd)
    if recent is not None and not policy.icloudpd.get("recent"):
        args += ["--recent", str(recent)]
    effective_library = library or policy.icloudpd.get("library")
    if effective_library:
        args += ["--library", str(effective_library)]
    if dry_run or bool(policy.icloudpd.get("dry_run")):
        args.append("--dry-run")
    return args


def naming_signature(policy: Policy) -> dict[str, Any]:
    """Comparable view of everything that determines file paths/names."""
    sig: dict[str, Any] = {
        "directory": str(policy.directory),
        "library_kind": policy.library_kind,
    }
    for key in sorted(NAMING_KEYS):
        value = policy.icloudpd.get(key)
        sig[key] = None if value is False else value
    return sig
