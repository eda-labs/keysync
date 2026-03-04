from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SSHKeyCandidate:
    """Public key candidate discovered from the local system."""

    fingerprint: str
    public_key: str
    key_type: str
    comment: str
    sources: tuple[str, ...]


@dataclass
class NodeUserResource:
    """Minimal NodeUser view required for key patching."""

    namespace: str
    name: str
    username: str
    ssh_public_keys: list[str]

    @property
    def fq_name(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass(frozen=True)
class KubernetesConnectionInfo:
    """Metadata shown in the TUI header about active Kubernetes connectivity."""

    mode: str
    context_name: str
    namespace_hint: str
    cluster_name: str
    user_name: str
    kubeconfig_path: str

