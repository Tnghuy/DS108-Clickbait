"""Keyboard Handler — single-key input cho Human Review CLI.

Windows: dùng msvcrt (built-in).
Unix:   fallback sang sys.stdin.read(1) + tty/termios.
"""

from __future__ import annotations

import sys
from typing import Optional


def get_single_key(prompt: str = "") -> str:
    """Đợi 1 phím từ user, KHÔNG cần Enter.

    Returns:
        Key string: '0'-'9', 's', 'S', 'p', 'P', 'n', 'N', 'q', 'Q', '?', '\r', '\x03'
        '\x03' = Ctrl+C (KeyboardInterrupt)
    """
    if prompt:
        sys.stdout.write(prompt)
        sys.stdout.flush()

    if sys.platform == "win32":
        return _get_key_windows()
    else:
        return _get_key_unix()


def _get_key_windows() -> str:
    """Windows: dùng msvcrt."""
    import msvcrt  # type: ignore[import-untyped]

    while True:
        key = msvcrt.getwch()
        if key == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if key == "\x00":  # Special key prefix (F-keys, arrows)
            msvcrt.getwch()  # discard the second byte
            continue
        return key


def _get_key_unix() -> str:
    """Unix: dùng tty + termios để đọc single char."""
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)  # type: ignore[reportAttributeAccessIssue]
    try:
        tty.setraw(fd)  # type: ignore[reportAttributeAccessIssue]
        if select.select([sys.stdin], [], [], 0.1)[0]:
            key = sys.stdin.read(1)
        else:
            key = ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # type: ignore[reportAttributeAccessIssue]

    if key == "\x03":  # Ctrl+C
        raise KeyboardInterrupt
    if key == "\x04":  # Ctrl+D
        raise EOFError
    return key


def prompt_rubric_score(criterion: str, criterion_name: str) -> int:
    """Đợi user nhập rubric score 0/1/2 cho 1 criterion.

    Args:
        criterion: "C1", "C2", "C3", hoặc "C4"
        criterion_name: tên tiêu chí tiếng Việt

    Returns:
        0, 1, hoặc 2
    """
    valid = {"0": 0, "1": 1, "2": 2}
    while True:
        key = get_single_key(f"  {criterion} [{criterion_name}] (0/1/2): ")
        if key in valid:
            # Echo the key
            sys.stdout.write(key + "\n")
            sys.stdout.flush()
            return valid[key]
        elif key in ("\r", "\n"):
            # Enter — prompt again
            pass
        elif key in ("\x03", "q", "Q"):
            raise KeyboardInterrupt


def prompt_label() -> int:
    """Đợi user chọn label 0 hoặc 1."""
    valid = {"0": 0, "1": 1}
    while True:
        key = get_single_key("  Label (0=non-clickbait, 1=clickbait): ")
        if key in valid:
            sys.stdout.write(key + "\n")
            sys.stdout.flush()
            return valid[key]
        elif key in ("\r", "\n"):
            pass
        elif key in ("\x03", "q", "Q"):
            raise KeyboardInterrupt


def prompt_severity() -> int:
    """Đợi user nhập severity 0-3."""
    valid = {"0": 0, "1": 1, "2": 2, "3": 3}
    while True:
        key = get_single_key("  Severity (0-3) (0=không clickbait, 1=nhẹ, 2=trung bình, 3=cao): ")
        if key in valid:
            sys.stdout.write(key + "\n")
            sys.stdout.flush()
            return valid[key]
        elif key in ("\r", "\n"):
            pass
        elif key in ("\x03", "q", "Q"):
            raise KeyboardInterrupt


def confirm_action(message: str) -> bool:
    """Confirm với user (y/n)."""
    sys.stdout.write(f"{message} (y/n): ")
    sys.stdout.flush()
    key = get_single_key()
    sys.stdout.write(key + "\n")
    sys.stdout.flush()
    return key.lower() == "y"
