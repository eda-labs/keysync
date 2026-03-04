from __future__ import annotations

import os

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from keysync.models import KubernetesConnectionInfo, NodeUserResource

EDA_NODEUSER_GROUP = "core.eda.nokia.com"
EDA_NODEUSER_VERSION = "v1"
EDA_NODEUSER_PLURAL = "nodeusers"


def _canonical_public_key(value: str) -> str:
    parts = value.strip().split()
    if len(parts) < 2:
        return value.strip()
    return f"{parts[0]} {parts[1]}"


def _safe(value: str | None, fallback: str = "-") -> str:
    if value is None:
        return fallback
    stripped = value.strip()
    return stripped if stripped else fallback


def load_kubernetes_connection(
    kubeconfig: str | None = None, context: str | None = None
) -> tuple[client.CustomObjectsApi, KubernetesConnectionInfo]:
    """
    Load Kubernetes API configuration.

    Preference:
    1) explicit kubeconfig/context if provided
    2) in-cluster config
    3) local kubeconfig
    """

    if kubeconfig is not None or context is not None:
        config.load_kube_config(config_file=kubeconfig, context=context)
        info = _build_kubeconfig_info(kubeconfig=kubeconfig, context=context)
        return client.CustomObjectsApi(), info

    try:
        config.load_incluster_config()
        info = KubernetesConnectionInfo(
            mode="in-cluster",
            context_name="in-cluster",
            namespace_hint=_safe(
                _read_text_file("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
            ),
            cluster_name="in-cluster",
            user_name="service-account",
            kubeconfig_path="-",
        )
        return client.CustomObjectsApi(), info
    except ConfigException:
        config.load_kube_config()
        info = _build_kubeconfig_info(kubeconfig=None, context=None)
        return client.CustomObjectsApi(), info


def _read_text_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _build_kubeconfig_info(
    kubeconfig: str | None, context: str | None
) -> KubernetesConnectionInfo:
    contexts, active_context = config.list_kube_config_contexts(config_file=kubeconfig)
    selected = active_context
    if context:
        selected = next((item for item in contexts if item.get("name") == context), None)

    context_block = (selected or {}).get("context", {})
    kubeconfig_path = kubeconfig or os.environ.get("KUBECONFIG") or "~/.kube/config"

    return KubernetesConnectionInfo(
        mode="kubeconfig",
        context_name=_safe((selected or {}).get("name")),
        namespace_hint=_safe(context_block.get("namespace"), "default"),
        cluster_name=_safe(context_block.get("cluster")),
        user_name=_safe(context_block.get("user")),
        kubeconfig_path=kubeconfig_path,
    )


def list_nodeusers(
    custom_api: client.CustomObjectsApi, namespace: str | None
) -> list[NodeUserResource]:
    if namespace:
        payload = custom_api.list_namespaced_custom_object(
            group=EDA_NODEUSER_GROUP,
            version=EDA_NODEUSER_VERSION,
            namespace=namespace,
            plural=EDA_NODEUSER_PLURAL,
        )
    else:
        payload = custom_api.list_cluster_custom_object(
            group=EDA_NODEUSER_GROUP,
            version=EDA_NODEUSER_VERSION,
            plural=EDA_NODEUSER_PLURAL,
        )

    results: list[NodeUserResource] = []
    for item in payload.get("items", []):
        metadata = item.get("metadata", {}) or {}
        spec = item.get("spec", {}) or {}
        keys = spec.get("sshPublicKeys", []) or []
        key_list = [str(key) for key in keys if str(key).strip()]

        name = str(metadata.get("name", ""))
        namespace_name = str(metadata.get("namespace", "default"))
        username = str(spec.get("username") or name)

        results.append(
            NodeUserResource(
                namespace=namespace_name,
                name=name,
                username=username,
                ssh_public_keys=key_list,
            )
        )

    return sorted(results, key=lambda item: (item.namespace, item.name))


def patch_nodeuser_keys(
    custom_api: client.CustomObjectsApi,
    nodeuser: NodeUserResource,
    keys_to_add: list[str],
) -> int:
    """
    Append keys to a NodeUser resource without creating duplicates.

    Returns number of keys effectively added.
    """

    merged = list(nodeuser.ssh_public_keys)
    existing_canonical = {
        _canonical_public_key(existing_key) for existing_key in nodeuser.ssh_public_keys
    }
    added_count = 0

    for key in keys_to_add:
        canonical = _canonical_public_key(key)
        if canonical in existing_canonical:
            continue
        merged.append(key)
        existing_canonical.add(canonical)
        added_count += 1

    if added_count == 0:
        return 0

    body = {"spec": {"sshPublicKeys": merged}}
    custom_api.patch_namespaced_custom_object(
        group=EDA_NODEUSER_GROUP,
        version=EDA_NODEUSER_VERSION,
        namespace=nodeuser.namespace,
        plural=EDA_NODEUSER_PLURAL,
        name=nodeuser.name,
        body=body,
    )
    nodeuser.ssh_public_keys = merged
    return added_count
