# keysync

`keysync` is an interactive terminal UI (Textual) for syncing local SSH public keys into Nokia EDA `NodeUser` Kubernetes custom resources.

In EDA, access is mediated through `NodeUser` resources. `keysync` focuses on that layer: it discovers your keys, shows available `NodeUser` objects in your current cluster context, and patches only missing keys into `spec.sshPublicKeys`.

## Features

- Interactive TUI for selecting SSH keys and `NodeUser` targets
- Kubernetes connection auto-discovery:
  1. Explicit `--kubeconfig` / `--context`
  2. In-cluster config
  3. Local kubeconfig (`~/.kube/config`)
- SSH key discovery from:
  - `ssh-agent` (`ssh-add -L`)
  - `~/.ssh/*.pub`
  - `~/.ssh/authorized_keys`
- Deduplicates discovered keys by SHA256 fingerprint
- Appends only keys not already present on each `NodeUser`
- Namespace-scoped or cluster-wide `NodeUser` discovery
- Keyboard-first workflow with responsive layout for smaller terminals

## Runtime Requirements

- `curl` and `sh`
- A Kubernetes cluster with EDA `NodeUser` CRD:
  - API group: `core.eda.nokia.com`
  - Version: `v1`
  - Resource: `nodeusers`
- A valid kubeconfig context (or in-cluster service account)
- Kubernetes permissions to list and patch `NodeUser` resources
- Optional: running `ssh-agent` with identities loaded (`SSH_AUTH_SOCK`)

## Quick Start

No local Python or `uv` installation is required when launched through the `eda.dev/uvx` bootstrap wrapper.

```bash
curl eda.dev/uvx | sh -s -- https://github.com/eda-labs/keysync/archive/refs/heads/main.zip
```

For reproducible runs, use a pinned tag archive:

```bash
curl eda.dev/uvx | sh -s -- https://github.com/eda-labs/keysync/archive/refs/tags/<tag>.zip
```

## Usage

```bash
keysync [--namespace <ns>] [--kubeconfig <path>] [--context <name>]
```

If you run from source (developer workflow), use:

```bash
uv run keysync [--namespace <ns>] [--kubeconfig <path>] [--context <name>]
```

Examples:

```bash
keysync --namespace clab-dci-ott
keysync --kubeconfig ~/.kube/config --context kubernetes-admin@kubernetes
```

### CLI Options

- `--namespace`: Restrict `NodeUser` discovery to one namespace. If omitted, discovers across all namespaces.
- `--kubeconfig`: Path to kubeconfig file.
- `--context`: Kubeconfig context name.

## Keyboard Shortcuts

- `q`: Quit
- `r`: Refresh keys and `NodeUser` list
- `a`: Apply selected keys to selected `NodeUser` resources
- `k`: Select all keys
- `u`: Select all `NodeUser` resources
- `l`: Toggle log pane

## Key Discovery and Dedup Semantics

`keysync` accepts valid OpenSSH public key lines for these types:

- `ssh-rsa`
- `ssh-ed25519`
- `ecdsa-sha2-nistp256`
- `ecdsa-sha2-nistp384`
- `ecdsa-sha2-nistp521`
- `sk-ecdsa-sha2-nistp256@openssh.com`
- `sk-ssh-ed25519@openssh.com`

Behavior details:

- Discovery dedup is by SHA256 fingerprint of decoded key blob.
- Sources are tracked and shown in the UI.
- When patching a `NodeUser`, duplicate detection uses canonical `"<type> <key_blob>"`.
- Key comments are preserved for newly added keys but are ignored for duplicate checks.

## Kubernetes API Behavior

Patch behavior:

- Existing keys are preserved.
- Only missing keys are appended.
- No delete or replace operations are performed.

## Troubleshooting

- `Failed to initialize Kubernetes config`:
  - Verify kubeconfig path/context or in-cluster service account configuration.
- `0 key(s)` loaded:
  - Check `ssh-add -L` output and files in `~/.ssh`.
- Kubernetes API `403` errors during apply:
  - Confirm RBAC includes `patch` on `nodeusers.core.eda.nokia.com`.
- Keys appear duplicated due to comment differences:
  - Duplicate checks intentionally ignore comments and compare key type + key blob.

## License

Apache-2.0. See [LICENSE](LICENSE).
