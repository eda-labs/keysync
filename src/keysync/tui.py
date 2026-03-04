from __future__ import annotations

from typing import Iterable

from kubernetes import client
from kubernetes.client.rest import ApiException
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.content import Content
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.style import Style
from textual.widgets import Button, Checkbox, Footer, Header, RichLog, Static

from keysync.k8s import list_nodeusers, patch_nodeuser_keys
from keysync.models import (
    KubernetesConnectionInfo,
    NodeUserResource,
    SSHKeyCandidate,
)
from keysync.ssh_keys import discover_ssh_keys


class VisualCheckbox(Checkbox):
    """Checkbox with explicit on/off inner glyph for clearer state indication."""

    @property
    def _button(self) -> Content:  # type: ignore[override]
        button_style = self.get_visual_style("toggle--button")
        side_style = Style(
            foreground=button_style.background,
            background=self.background_colors[1],
        )
        inner = "X" if self.value else " "
        return Content.assemble(
            (self.BUTTON_LEFT, side_style),
            (inner, button_style),
            (self.BUTTON_RIGHT, side_style),
        )


class KeySyncApp(App[None]):
    TITLE = "keysync"
    CSS = """
    Screen {
        background: #0b1219;
        color: #e6edf3;
        layout: vertical;
    }

    Header {
        background: #184e77;
        color: #f7fff7;
        text-style: bold;
    }

    Footer {
        background: #1b263b;
        color: #f7fff7;
    }

    #context {
        background: #003049;
        color: #fdf0d5;
        padding: 0 1;
        margin: 0 1;
        border: round #669bbc;
        text-style: bold;
        height: 3;
    }

    #columns {
        height: 1fr;
        margin: 0 1;
    }

    .card {
        width: 1fr;
        height: 1fr;
        border: round #457b9d;
        padding: 0 1;
        margin: 0 1 0 0;
        background: #111a24;
        min-height: 8;
    }

    .card:focus-within {
        border: round #8ecae6;
    }

    #nodeusers-card {
        margin: 0;
    }

    .title {
        color: #ffb703;
        text-style: bold;
        margin: 0;
    }

    VerticalScroll {
        height: 1fr;
        border: solid #264653;
        background: #0f1720;
        padding: 0 1;
    }

    Checkbox {
        margin: 0;
    }

    Checkbox:focus {
        background: #16324f;
        color: #ffffff;
        text-style: bold;
    }

    Checkbox.-on {
        background: #143624;
        color: #f1fff7;
    }

    Checkbox > .toggle--button {
        color: #84a59d;
    }

    Checkbox.-on > .toggle--button {
        color: #70e1c8;
        text-style: bold;
    }

    Checkbox:focus > .toggle--button {
        color: #ffb703;
    }

    Checkbox.-on > .toggle--label {
        text-style: bold;
    }

    Checkbox > .toggle--label {
        text-overflow: ellipsis;
        text-wrap: nowrap;
    }

    #controls {
        layout: grid;
        grid-size: 7;
        grid-columns: 1fr 1fr 1fr 1fr 1fr 1fr 1fr;
        grid-gutter: 0 1;
        margin: 0 1;
        height: auto;
    }

    #controls Button {
        margin: 0;
        width: 1fr;
        color: #f1f5f9;
        background: #264653;
    }

    #controls Button:hover {
        background: #386fa4;
    }

    #controls Button:focus {
        background: #468faf;
        text-style: bold;
    }

    #controls Button:disabled {
        color: #93a1af;
        background: #1e2f42;
    }

    #apply {
        background: #2a9d8f;
        color: #081c15;
        text-style: bold;
    }

    #status {
        height: 3;
        margin: 0 1;
        padding: 0 1;
        border: round #495057;
        background: #10151c;
        color: #ced4da;
    }

    #log {
        height: 7;
        margin: 0 1;
        border: round #495057;
        background: #090f14;
        color: #dbe7f3;
    }

    #columns.narrow {
        layout: vertical;
    }

    #columns.narrow .card {
        margin: 0 0 1 0;
    }

    #columns.narrow #nodeusers-card {
        margin: 0;
    }

    #controls.narrow {
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
    }

    #controls.compact {
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }

    #controls.compact Button.aux {
        display: none;
    }

    Screen.short-height .card {
        min-height: 5;
    }

    Screen.short-height #log {
        height: 3;
    }

    Screen.ultra-height Header {
        display: none;
    }

    Screen.ultra-height Footer {
        display: none;
    }

    Screen.ultra-height #log {
        height: 4;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_data", "Refresh"),
        Binding("a", "apply_selected", "Apply"),
        Binding("k", "select_all_keys", "All Keys"),
        Binding("u", "select_all_nodeusers", "All Users"),
        Binding("l", "toggle_log", "Toggle Log"),
    ]

    def __init__(
        self,
        custom_api: client.CustomObjectsApi,
        connection_info: KubernetesConnectionInfo,
        namespace_filter: str | None = None,
    ) -> None:
        super().__init__()
        self.custom_api = custom_api
        self.connection_info = connection_info
        self.namespace_filter = namespace_filter
        self.key_candidates: list[SSHKeyCandidate] = []
        self.nodeusers: list[NodeUserResource] = []
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="context")
        with Horizontal(id="columns"):
            with Vertical(classes="card", id="keys-card"):
                yield Static("SSH Public Keys", classes="title")
                yield VerticalScroll(id="keys-list")
            with Vertical(classes="card", id="nodeusers-card"):
                yield Static("NodeUsers", classes="title")
                yield VerticalScroll(id="nodeusers-list")
        with Horizontal(id="controls"):
            yield Button("Refresh", id="refresh")
            yield Button("All Keys", id="all-keys", classes="aux")
            yield Button("Clear Keys", id="clear-keys", classes="aux")
            yield Button("All Users", id="all-users", classes="aux")
            yield Button("Clear Users", id="clear-users", classes="aux")
            yield Button("Apply Keys", id="apply")
            yield Button("Quit", id="quit")
        yield Static(id="status")
        yield RichLog(id="log", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._apply_responsive_layout()
        self.query_one("#refresh", Button).focus()
        self._update_context_banner()
        self.action_refresh_data()

    def on_resize(self, event: events.Resize) -> None:
        _ = event
        self._apply_responsive_layout()
        self._update_context_banner()

    def _apply_responsive_layout(self) -> None:
        width = self.size.width
        height = self.size.height
        self.query_one("#columns", Horizontal).set_class(width <= 110, "narrow")
        controls = self.query_one("#controls", Horizontal)
        controls.set_class(width <= 120, "narrow")
        controls.set_class(width <= 85, "compact")
        self.screen.set_class(height <= 22, "short-height")
        self.screen.set_class(height <= 16, "ultra-height")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "refresh":
            self.action_refresh_data()
        elif button_id == "all-keys":
            self.action_select_all_keys()
        elif button_id == "clear-keys":
            self.action_clear_all_keys()
        elif button_id == "all-users":
            self.action_select_all_nodeusers()
        elif button_id == "clear-users":
            self.action_clear_all_nodeusers()
        elif button_id == "apply":
            self.action_apply_selected()
        elif button_id == "quit":
            self.exit()

    def action_refresh_data(self) -> None:
        if self.busy:
            return
        self._set_busy(True, "Refreshing SSH keys and NodeUsers...")
        self._refresh_worker()

    def action_apply_selected(self) -> None:
        if self.busy:
            return

        selected_key_indices = self._selected_indices("key-choice")
        selected_node_indices = self._selected_indices("node-choice")

        if not selected_key_indices:
            self._set_status("Select at least one SSH key.")
            return
        if not selected_node_indices:
            self._set_status("Select at least one NodeUser.")
            return

        key_values = [self.key_candidates[index].public_key for index in selected_key_indices]
        self._set_busy(
            True,
            f"Applying {len(key_values)} key(s) to {len(selected_node_indices)} NodeUser(s)...",
        )
        self._apply_worker(key_values, selected_node_indices)

    def action_select_all_keys(self) -> None:
        total = self._set_checkbox_values("key-choice", True)
        self._set_status(f"Selected {total} key(s).")

    def action_select_all_nodeusers(self) -> None:
        total = self._set_checkbox_values("node-choice", True)
        self._set_status(f"Selected {total} NodeUser(s).")

    def action_clear_all_keys(self) -> None:
        total = self._set_checkbox_values("key-choice", False)
        self._set_status(f"Cleared key selection ({total} total).")

    def action_clear_all_nodeusers(self) -> None:
        total = self._set_checkbox_values("node-choice", False)
        self._set_status(f"Cleared NodeUser selection ({total} total).")

    def action_toggle_log(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.display = not log_widget.display

    def _update_context_banner(self) -> None:
        scope = self.namespace_filter or "all namespaces"
        info = self.connection_info
        if self.size.width <= 95:
            line = f"K8s {info.mode} | ctx={info.context_name} | scope={scope}"
        else:
            line = (
                f"K8s {info.mode} | context={info.context_name} | cluster={info.cluster_name} | "
                f"user={info.user_name} | default-ns={info.namespace_hint} | scope={scope}"
            )
        line = self._truncate(line, max(20, self.size.width - 6))
        self.query_one("#context", Static).update(line)

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _append_log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy = busy
        for button_id in (
            "#refresh",
            "#apply",
            "#all-keys",
            "#clear-keys",
            "#all-users",
            "#clear-users",
        ):
            self.query_one(button_id, Button).disabled = busy
        self._set_status(message)

    def _selected_indices(self, checkbox_class: str) -> list[int]:
        result: list[int] = []
        for checkbox in self.query(f".{checkbox_class}"):
            if checkbox.value and checkbox.name:
                try:
                    result.append(int(checkbox.name.split("-", 1)[1]))
                except ValueError:
                    continue
        return sorted(result)

    def _set_checkbox_values(self, checkbox_class: str, value: bool) -> int:
        total = 0
        for checkbox in self.query(f".{checkbox_class}"):
            checkbox.value = value
            total += 1
        return total

    def _truncate(self, value: str, max_len: int) -> str:
        if max_len <= 0:
            return ""
        if len(value) <= max_len:
            return value
        if max_len <= 3:
            return value[:max_len]
        return f"{value[: max_len - 3]}..."

    def _format_sources(self, sources: Iterable[str]) -> str:
        source_list = list(sources)
        if len(source_list) <= 2:
            return ", ".join(source_list)
        first_two = ", ".join(source_list[:2])
        return f"{first_two}, +{len(source_list) - 2} more"

    def _render_key_list(self) -> None:
        key_panel = self.query_one("#keys-list", VerticalScroll)
        key_panel.remove_children()

        for index, candidate in enumerate(self.key_candidates):
            comment = candidate.comment or "no comment"
            sources = self._format_sources(candidate.sources)
            label = (
                f"{candidate.key_type} | {comment} | {candidate.fingerprint[-16:]} | {sources}"
            )
            key_panel.mount(
                VisualCheckbox(label, name=f"key-{index}", classes="key-choice")
            )

    def _render_nodeuser_list(self) -> None:
        node_panel = self.query_one("#nodeusers-list", VerticalScroll)
        node_panel.remove_children()

        for index, nodeuser in enumerate(self.nodeusers):
            label = (
                f"{nodeuser.namespace}/{nodeuser.name} | user={nodeuser.username} | "
                f"keys={len(nodeuser.ssh_public_keys)}"
            )
            node_panel.mount(
                VisualCheckbox(label, name=f"node-{index}", classes="node-choice")
            )

    @work(thread=True, exclusive=True)
    def _refresh_worker(self) -> None:
        try:
            keys = discover_ssh_keys()
            nodeusers = list_nodeusers(
                custom_api=self.custom_api,
                namespace=self.namespace_filter,
            )
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._append_log,
                f"[red]Refresh failed:[/red] {exc}",
            )
            self.call_from_thread(
                self._set_busy,
                False,
                "Refresh failed. See log pane.",
            )
            return

        self.call_from_thread(self._replace_all_data, keys, nodeusers)
        self.call_from_thread(
            self._append_log,
            f"[green]Loaded[/green] {len(keys)} key(s), {len(nodeusers)} NodeUser resource(s).",
        )
        self.call_from_thread(
            self._set_busy,
            False,
            f"Ready: {len(keys)} key(s), {len(nodeusers)} NodeUser(s).",
        )

    def _replace_all_data(
        self,
        keys: list[SSHKeyCandidate],
        nodeusers: list[NodeUserResource],
    ) -> None:
        self.key_candidates = keys
        self.nodeusers = nodeusers
        self._render_key_list()
        self._render_nodeuser_list()

    @work(thread=True, exclusive=True)
    def _apply_worker(self, key_values: list[str], node_indices: list[int]) -> None:
        updated = 0
        total_added = 0

        try:
            for index in node_indices:
                nodeuser = self.nodeusers[index]
                added = patch_nodeuser_keys(self.custom_api, nodeuser, key_values)
                if added > 0:
                    updated += 1
                    total_added += added
                    self.call_from_thread(
                        self._append_log,
                        f"[green]Patched[/green] {nodeuser.fq_name}: +{added} key(s)",
                    )
                else:
                    self.call_from_thread(
                        self._append_log,
                        f"[yellow]No change[/yellow] {nodeuser.fq_name}: keys already present",
                    )

            latest = list_nodeusers(
                custom_api=self.custom_api,
                namespace=self.namespace_filter,
            )
            self.call_from_thread(self._replace_nodeusers, latest)
            self.call_from_thread(
                self._append_log,
                f"[bold green]Done[/bold green] updated {updated}/{len(node_indices)} "
                f"NodeUser(s), added {total_added} key entry(ies).",
            )
            self.call_from_thread(
                self._set_busy,
                False,
                f"Completed: updated {updated}/{len(node_indices)} NodeUser(s).",
            )
        except ApiException as exc:
            self.call_from_thread(
                self._append_log,
                (
                    f"[red]Kubernetes API error[/red] status={exc.status} "
                    f"reason={exc.reason} body={exc.body}"
                ),
            )
            self.call_from_thread(
                self._set_busy,
                False,
                "Kubernetes API error during patch. See log pane.",
            )
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._append_log,
                f"[red]Apply failed:[/red] {exc}",
            )
            self.call_from_thread(
                self._set_busy,
                False,
                "Apply failed. See log pane.",
            )

    def _replace_nodeusers(self, latest: list[NodeUserResource]) -> None:
        self.nodeusers = latest
        self._render_nodeuser_list()
