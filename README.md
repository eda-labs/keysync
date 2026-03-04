# keysync

Interactive Textual TUI that:

1. Detects Kubernetes connectivity (`in-cluster` or local kubeconfig)
2. Collects SSH public keys from:
   - `ssh-agent` (`ssh-add -L`)
   - `~/.ssh/*.pub`
   - `~/.ssh/authorized_keys`
3. Lists EDA `NodeUser` resources
4. Lets you select keys + nodeusers
5. Patches selected `NodeUser` resources via Kubernetes API to append keys

UI behavior:

- Responsive layout for smaller terminals (including typical VS Code terminal sizes)
- Full-pane layout tuned for short-wide terminals such as `170x20`
- Focus and hover highlighting for faster keyboard navigation
- `l` key to toggle the log pane when you need more space

## Kubernetes resources used

Validated against live CRDs:

- Read:
  - `nodeusers.core.eda.nokia.com` (list)
- Write:
  - `nodeusers.core.eda.nokia.com` (patch `spec.sshPublicKeys`)

## Run locally

```bash
cd keysync
uv run keysync
```

Optional filters:

```bash
uv run keysync --namespace clab-dci-ott
uv run keysync --kubeconfig ~/.kube/config --context kubernetes-admin@kubernetes
```

## Run from repo tag with uvx

```bash
uvx --from "https://github.com/eda-labs/keysync/archive/refs/tags/<tag>.zip" keysync
```

With your wrapper style:

```bash
curl https://eda.dev/uvx | sh -s -- "https://github.com/eda-labs/keysync/archive/refs/tags/<tag>.zip" keysync
```
