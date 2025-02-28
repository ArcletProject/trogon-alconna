from __future__ import annotations

import os
import shlex
from pathlib import Path
from webbrowser import open as open_url

from rich.console import Console
from rich.highlighter import ReprHighlighter
from rich.text import Text
from textual import log, events, on
from textual.app import ComposeResult, App, AutopilotCallbackType
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import (
    Tree,
    Label,
    Static,
    Button,
    Footer,
)
from textual.widgets.tree import TreeNode

from trogon.detect_run_string import detect_run_string
from trogon.introspect import (
    introspect_click_app,
    CommandSchema,
)
from trogon.run_command import UserCommandData
from trogon.widgets.command_info import CommandInfo
from trogon.widgets.command_tree import CommandTree
from trogon.widgets.form import CommandForm
from trogon.widgets.multiple_choice import NonFocusableVerticalScroll

from arclet.alconna import Alconna

try:
    from importlib import metadata  # type: ignore
except ImportError:
    # Python < 3.8
    import importlib_metadata as metadata  # type: ignore


class CommandBuilder(Screen):
    COMPONENT_CLASSES = {"version-string", "prompt", "command-name-syntax"}

    BINDINGS = [
        Binding(key="ctrl+r", action="close_and_run", description="Close & Run"),
        Binding(
            key="ctrl+t", action="focus_command_tree", description="Focus Command Tree"
        ),
        Binding(key="ctrl+o", action="show_command_info", description="Command Info"),
        Binding(key="ctrl+s", action="focus('search')", description="Search"),
        Binding(key="f1", action="about", description="About"),
    ]

    def __init__(
        self,
        cli: Alconna,
        app_name: str,
        command_name: str,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(name, id, classes)
        self.command_data = None
        self.cli = cli
        self.command_schemas = introspect_click_app(cli)
        self.app_name = app_name
        self.command_name = command_name

        try:
            self.version = metadata.version(self.app_name)
        except Exception:
            self.version = None

        self.highlighter = ReprHighlighter()

    def compose(self) -> ComposeResult:
        tree = CommandTree("Commands", self.command_schemas, self.command_name)

        title_parts = [Text(self.app_name, style="b")]
        if self.version:
            version_style = self.get_component_rich_style("version-string")
            title_parts.extend(["\n", (f"v{self.version}", version_style)])  # type: ignore

        title = Text.assemble(*title_parts)

        sidebar = Vertical(
            Label(title, id="home-commands-label"),
            tree,
            id="home-sidebar",
        )
        # if self.is_grouped_cli:
        #     # If the root of the click app is a Group instance, then
        #     #  we display the command tree to users and focus it.
        #     tree.focus()
        # else:
        #     # If the click app is structured using a single command,
        #     #  there's no need for us to display the command tree.
        sidebar.display = False

        yield sidebar

        with Vertical(id="home-body"):
            with Horizontal(id="home-command-description-container") as vs:
                vs.can_focus = False
                yield Static(self.app_name or "", id="home-command-description")

            scrollable_body = VerticalScroll(
                Static(""),
                id="home-body-scroll",
            )
            scrollable_body.can_focus = False
            yield scrollable_body
            yield Horizontal(
                NonFocusableVerticalScroll(
                    Static("", id="home-exec-preview-static"),
                    id="home-exec-preview-container",
                ),
                # Vertical(
                #     Button.success("Close & Run", id="home-exec-button"),
                #     id="home-exec-preview-buttons",
                # ),
                id="home-exec-preview",
            )

        yield Footer()

    def action_close_and_run(self) -> None:
        self.app.execute_on_exit = True  # type: ignore
        self.app.exit()

    def action_about(self) -> None:
        from .widgets.about import AboutDialog

        self.app.push_screen(AboutDialog())

    async def on_mount(self, event: events.Mount) -> None:
        await self._refresh_command_form()

    async def _refresh_command_form(self, node: TreeNode[CommandSchema] | None = None):
        if node is None:
            try:
                command_tree = self.query_one(CommandTree)
                node = command_tree.cursor_node
            except NoMatches:
                return

        assert node is not None
        self.selected_command_schema = node.data
        self._update_command_description(node)
        self._update_execution_string_preview(
            self.selected_command_schema, self.command_data  # type: ignore
        )
        await self._update_form_body(node)

    @on(Tree.NodeHighlighted)
    async def selected_command_changed(
        self, event: Tree.NodeHighlighted[CommandSchema]
    ) -> None:
        """When we highlight a node in the CommandTree, the main body of the home page updates
        to display a form specific to the highlighted command."""
        await self._refresh_command_form(event.node)

    @on(CommandForm.Changed)
    def update_command_data(self, event: CommandForm.Changed) -> None:
        self.command_data = event.command_data
        self._update_execution_string_preview(
            self.selected_command_schema, self.command_data  # type: ignore
        )

    def _update_command_description(self, node: TreeNode[CommandSchema]) -> None:
        """Update the description of the command at the bottom of the sidebar
        based on the currently selected node in the command tree."""
        description_box = self.query_one("#home-command-description", Static)
        description_text = node.data.description or ""  # type: ignore
        description_text = description_text.lstrip()

        description_text = f"[b]{self.app_name}[/]\n{description_text}"
        # description_text = f"[b]{node.label if self.is_grouped_cli else self.app_name}[/]\n{description_text}"
        description_box.update(description_text)

    def _update_execution_string_preview(
        self, command_schema: CommandSchema, command_data: UserCommandData
    ) -> None:
        """Update the preview box showing the command string to be executed"""
        if self.command_data is not None:
            command_name_syntax_style = self.get_component_rich_style(
                "command-name-syntax"
            )
            prefix = Text(f"{self.app_name} ", command_name_syntax_style)
            new_value = command_data.to_cli_string(include_root_command=False)
            highlighted_new_value = Text.assemble(prefix, self.highlighter(new_value))
            prompt_style = self.get_component_rich_style("prompt")
            preview_string = Text.assemble(("$ ", prompt_style), highlighted_new_value)
            self.query_one("#home-exec-preview-static", Static).update(preview_string)

    async def _update_form_body(self, node: TreeNode[CommandSchema]) -> None:
        # self.query_one(Pretty).update(node.data)
        parent = self.query_one("#home-body-scroll", VerticalScroll)
        for child in parent.children:
            await child.remove()

        # Process the metadata for this command and mount corresponding widgets
        command_schema = node.data
        command_form = CommandForm(
            command_schema=command_schema, command_schemas=self.command_schemas
        )
        await parent.mount(command_form)
        # if not self.is_grouped_cli:
        command_form.focus()


class Trogon(App):
    CSS_PATH = Path(__file__).parent / "trogon.scss"

    def __init__(
        self,
        cli: Alconna,
        app_name: str | None = None,
        command_name: str = "tui",
    ) -> None:
        super().__init__()
        self.cli = cli
        self.post_run_command: list[str] = []
        self.execute_on_exit = False
        self.app_name = app_name or detect_run_string()
        self.command_name = command_name

    def on_mount(self):
        self.push_screen(CommandBuilder(self.cli, self.app_name, self.command_name))

    @on(Button.Pressed, "#home-exec-button")
    def on_button_pressed(self):
        self.execute_on_exit = True
        self.exit()

    def run(
        self,
        *,
        headless: bool = False,
        size: tuple[int, int] | None = None,
        auto_pilot: AutopilotCallbackType | None = None,
    ) -> None:
        try:
            super().run(headless=headless, size=size, auto_pilot=auto_pilot)
        finally:
            if self.post_run_command:
                console = Console()
                if self.post_run_command and self.execute_on_exit:
                    console.print(
                        f"Running [b cyan]{self.app_name} {' '.join(shlex.quote(s) for s in self.post_run_command)}[/]"
                    )

                    split_app_name = shlex.split(self.app_name)
                    program_name = shlex.split(self.app_name)[0]
                    arguments = [*split_app_name, *self.post_run_command]
                    os.execvp(program_name, arguments)

    @on(CommandForm.Changed)
    def update_command_to_run(self, event: CommandForm.Changed):
        include_root_command = True
        self.post_run_command = event.command_data.to_cli_args(include_root_command)

    def action_focus_command_tree(self) -> None:
        try:
            command_tree = self.query_one(CommandTree)
        except NoMatches:
            return

        command_tree.focus()

    def action_show_command_info(self) -> None:
        command_builder = self.query_one(CommandBuilder)
        self.push_screen(CommandInfo(command_builder.selected_command_schema))  # type: ignore

    def action_visit(self, url: str) -> None:
        """Visit the given URL, via the operating system.

        Args:
            url: The URL to visit.
        """
        open_url(url)

def tui(alc: Alconna, name: str | None = None, command: str = "tui"):
    alc.subcommand(name=command, help_text="Run the TUI for the application")

    @alc.bind()
    def wrapped_tui(subcommands: dict):
        if command in subcommands:
            Trogon(alc, app_name=name, command_name=command).run()
