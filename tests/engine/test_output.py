from __future__ import annotations

from cloudripr.engine.output import OutputEvent, OutputParser


def kinds(events: list[OutputEvent]) -> list[str]:
    return [e.kind for e in events]


def test_complete_lines_become_line_events() -> None:
    p = OutputParser()
    evs = p.feed("first\nsecond\r\npartial")
    assert [(e.kind, e.text) for e in evs] == [("line", "first"), ("line", "second")]
    assert p.flush() == [OutputEvent("line", "partial")]
    assert p.flush() == []


def test_downloaded_and_would_download_paths() -> None:
    p = OutputParser()
    evs = p.feed(
        "2026-10-14 03:00:05 INFO     Downloaded /downloads/2026/10/IMG_1.HEIC\n"
        "2026-10-14 03:00:06 INFO     [DRY RUN] Would download /downloads/2026/10/IMG_2.HEIC\n"
    )
    assert OutputEvent("downloaded", evs[0].text, "/downloads/2026/10/IMG_1.HEIC") in evs
    would = [e for e in evs if e.kind == "would_download"]
    assert would[0].value == "/downloads/2026/10/IMG_2.HEIC"


def test_twofa_and_twosa_detected() -> None:
    p = OutputParser()
    evs = p.feed(
        "2026-10-14 03:00:01 INFO     Two-factor authentication is required (2fa)\n"
        "2026-10-14 03:00:01 INFO     Two-step authentication is required (2sa)\n"
    )
    assert kinds(evs).count("twofa_required") == 2


def test_phone_options() -> None:
    p = OutputParser()
    evs = p.feed("  a: (•••) •••-••12\n  b: +31 •• ••• ••34\n")
    phones = [(e.value, e.text) for e in evs if e.kind == "phone_option"]
    assert phones == [("a", "(•••) •••-••12"), ("b", "+31 •• ••• ••34")]


def test_prompt_without_newline_emitted_once_and_cleared() -> None:
    p = OutputParser()
    prompt = (
        "Please enter two-factor authentication code or device index (a) to send SMS with a code: "
    )
    evs = p.feed(prompt)
    assert kinds(evs) == ["line", "prompt"]
    assert evs[1].value == "code_or_index"
    # The next output starts fresh, not glued to the prompt.
    evs = p.feed("Should be index (a) or six-digit code. Try again\n")
    assert evs == [OutputEvent("line", "Should be index (a) or six-digit code. Try again")]


def test_prompt_split_across_chunks() -> None:
    p = OutputParser()
    assert p.feed("Please enter two-factor authentication code th") == []
    evs = p.feed("at you received over SMS: ")
    assert evs[-1] == OutputEvent(
        "prompt",
        "Please enter two-factor authentication code that you received over SMS:",
        "sms_code",
    )


def test_multi_phone_and_code_only_prompts() -> None:
    p = OutputParser()
    evs = p.feed(
        "Please enter two-factor authentication code or device index (a..c) "
        "to send SMS with a code: "
    )
    assert evs[-1].value == "code_or_index"
    evs = p.feed("Please enter two-factor authentication code: ")
    assert evs[-1].value == "code"


def test_prompt_inside_complete_line_is_not_a_prompt() -> None:
    p = OutputParser()
    evs = p.feed("Please enter two-factor authentication code: 123456\n")
    assert kinds(evs) == ["line"]


def test_rejections_and_success() -> None:
    p = OutputParser()
    evs = p.feed(
        "2026-10-14 03:00:01 ERROR    Code verification failed.\n"
        "Failed to verify two-factor authentication code\n"
        "2026-10-14 03:00:01 ERROR    Invalid email/password combination.\n"
        "2026-10-14 03:00:01 INFO     Great, you're all set up. The script can now be run\n"
        "2026-10-14 03:00:01 INFO     Authentication completed successfully\n"
    )
    assert kinds(evs).count("mfa_rejected") == 2
    assert kinds(evs).count("bad_password") == 1
    assert kinds(evs).count("auth_ok") == 2


def test_total_event() -> None:
    p = OutputParser()
    evs = p.feed(
        "2026-11-22 15:07:53 INFO     Downloading 75993 original photos and videos "
        "to /downloads ...\n"
    )
    totals = [e for e in evs if e.kind == "total"]
    assert [t.value for t in totals] == ["75993"]
