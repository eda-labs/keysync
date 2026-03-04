from __future__ import annotations

import base64
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Iterable

from keysync.models import SSHKeyCandidate

PUBKEY_TYPES = (
    "ssh-rsa",
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "sk-ssh-ed25519@openssh.com",
)


def _decode_key_blob(key_blob: str) -> bytes | None:
    try:
        padding = "=" * ((4 - len(key_blob) % 4) % 4)
        return base64.b64decode(key_blob + padding, validate=True)
    except Exception:
        return None


def _parse_public_key_line(line: str) -> tuple[str, str, str] | None:
    value = line.strip()
    if not value or value.startswith("#"):
        return None

    parts = value.split(maxsplit=2)
    if len(parts) < 2:
        return None

    key_type, key_blob = parts[0], parts[1]
    comment = parts[2] if len(parts) > 2 else ""
    if key_type not in PUBKEY_TYPES:
        return None
    if _decode_key_blob(key_blob) is None:
        return None
    return key_type, key_blob, comment


def _fingerprint_sha256(key_blob: str) -> str | None:
    decoded = _decode_key_blob(key_blob)
    if decoded is None:
        return None
    digest = hashlib.sha256(decoded).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def _iter_agent_lines() -> Iterable[tuple[str, str]]:
    if not os.environ.get("SSH_AUTH_SOCK"):
        return []

    try:
        proc = subprocess.run(  # noqa: S603
            ["ssh-add", "-L"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    # Common "empty agent" output should not be treated as fatal.
    empty_agent = "The agent has no identities."
    if proc.returncode != 0 and empty_agent not in (proc.stderr or ""):
        return []

    entries: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        entries.append(("agent", line))
    return entries


def _iter_ssh_file_lines() -> Iterable[tuple[str, str]]:
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return []

    paths = sorted(ssh_dir.glob("*.pub"))
    authorized_keys = ssh_dir / "authorized_keys"
    if authorized_keys.exists():
        paths.append(authorized_keys)

    entries: list[tuple[str, str]] = []
    for path in paths:
        source = str(path).replace(str(Path.home()), "~")
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            entries.append((source, line))
    return entries


def discover_ssh_keys() -> list[SSHKeyCandidate]:
    """Collect SSH public keys from ssh-agent and ~/.ssh files."""

    indexed: dict[str, dict[str, object]] = {}
    for source, line in [*_iter_agent_lines(), *_iter_ssh_file_lines()]:
        parsed = _parse_public_key_line(line)
        if parsed is None:
            continue
        key_type, key_blob, comment = parsed
        fingerprint = _fingerprint_sha256(key_blob)
        if fingerprint is None:
            continue
        public_key = f"{key_type} {key_blob}"
        if comment:
            public_key = f"{public_key} {comment}"

        current = indexed.get(fingerprint)
        if current is None:
            indexed[fingerprint] = {
                "fingerprint": fingerprint,
                "public_key": public_key,
                "key_type": key_type,
                "comment": comment,
                "sources": {source},
            }
            continue

        current["sources"].add(source)  # type: ignore[attr-defined]
        if not current["comment"] and comment:
            current["comment"] = comment

    candidates: list[SSHKeyCandidate] = []
    for entry in indexed.values():
        sources = tuple(sorted(entry["sources"]))  # type: ignore[arg-type]
        candidates.append(
            SSHKeyCandidate(
                fingerprint=entry["fingerprint"],  # type: ignore[arg-type]
                public_key=entry["public_key"],  # type: ignore[arg-type]
                key_type=entry["key_type"],  # type: ignore[arg-type]
                comment=entry["comment"],  # type: ignore[arg-type]
                sources=sources,
            )
        )

    return sorted(candidates, key=lambda item: (item.key_type, item.comment, item.fingerprint))
