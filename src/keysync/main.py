from __future__ import annotations

import argparse
import sys

from keysync.k8s import load_kubernetes_connection
from keysync.tui import KeySyncApp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keysync",
        description=(
            "Interactive TUI to append SSH public keys (from ssh-agent and ~/.ssh) "
            "to selected EDA NodeUser resources through the Kubernetes API."
        ),
    )
    parser.add_argument(
        "--namespace",
        help="Restrict NodeUser discovery to a single namespace (default: all namespaces).",
    )
    parser.add_argument(
        "--kubeconfig",
        help="Optional kubeconfig path to use instead of default discovery.",
    )
    parser.add_argument(
        "--context",
        help="Optional kubeconfig context name to use.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        custom_api, info = load_kubernetes_connection(
            kubeconfig=args.kubeconfig,
            context=args.context,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to initialize Kubernetes config: {exc}", file=sys.stderr)
        return 2

    app = KeySyncApp(
        custom_api=custom_api,
        connection_info=info,
        namespace_filter=args.namespace,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
