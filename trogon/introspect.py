from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, NewType

# import click
# from click import BaseCommand, ParamType
from arclet.alconna import Alconna, Option, Subcommand, Args, Field, MultiVar, KeyWordVar, OptionResult, SubcommandResult
from arclet.alconna.action import Action, store, ActType
from nepattern import BasePattern




@dataclass
class ArgumentSchema:
    name: str
    type: BasePattern
    field: Field
    parent: "OptionSchema | CommandSchema"
    notice: str | None = None
    optional: bool = False

    @property
    def key(self):
        return f"{self.parent.key}_{self.name}"

@dataclass
class KeyWordArgumentSchema(ArgumentSchema):
    sep: str = "="

@dataclass
class MultiVarArgumentSchema(ArgumentSchema):
    nargs: int | str = "+"
    keyword: bool = False


@dataclass
class OptionSchema:
    name: str
    aliases: list[str]
    arguments: list[ArgumentSchema]
    description: str
    dest: str
    parent: "CommandSchema"
    action: Action = store
    default: OptionResult | None = None

    @property
    def key(self):
        return f"{self.parent.key}_{self.name}"

    @property
    def action_str(self):
        if self.action is store:
            return None
        if self.action.type is ActType.APPEND:
            return f"append({self.action.value})"
        if self.action.type is ActType.COUNT:
            return "count"
        if self.action.type is ActType.STORE:
            if self.action.value is True:
                return "store_true"
            if self.action.value is False:
                return "store_false"
            return f"store({self.action.value})"



@dataclass
class CommandSchema:
    name: CommandName
    command: str
    functions: list[Callable[..., Any | None]]
    description: str | None = None
    usage: str | None = None
    example: str | None = None
    options: list[OptionSchema] = field(default_factory=list)
    arguments: list[ArgumentSchema] = field(default_factory=list)
    subcommands: dict["CommandName", "CommandSchema"] = field(default_factory=dict)
    default: SubcommandResult | None = None
    parent: "CommandSchema | None" = None

    @property
    def key(self):
        if self.parent is None:
            return self.name
        return f"{self.parent.key}_{self.name}"

    @property
    def path_from_root(self) -> list["CommandSchema"]:
        node = self
        path = [self]
        while True:
            node = node.parent
            if node is None:
                break
            path.append(node)  # type: ignore
        return list(reversed(path))



def introspect_click_app(alc: Alconna) -> dict[CommandName, CommandSchema]:
    """
    Introspect a Alconna instance and build a data structure containing
    information about all commands, options, arguments, and subcommands,
    including the docstrings and command function references.

    This function recursively processes each command and its subcommands
    (if any), creating a nested dictionary that includes details about
    options, arguments, and subcommands, as well as the docstrings and
    command function references.

    Args:
        alc (arclet.alconna.core.Alconna): The command instance.

    Returns:
        Dict[str, CommandData]: A nested dictionary containing the Alconna instance's
        structure. The structure is defined by the CommandData TypedDict and its related
        TypedDicts (OptionData and ArgumentData).
    """

    def process_command(
        cmd_name: CommandName, cmd_obj: Alconna
    ) -> CommandSchema:
        cmd_data = CommandSchema(
            name=cmd_name,
            command=cmd_obj.header_display,
            functions=list(cmd_obj._executors),
            description=cmd_obj.meta.description,
            usage=cmd_obj.meta.usage,
            example=cmd_obj.meta.example,
            options=[],
            arguments=[],
            subcommands={},
        )

        def process_args(args: Args, parent: OptionSchema | CommandSchema):
            for arg in args:
                if isinstance(arg.value, KeyWordVar):
                    parent.arguments.append(
                        KeyWordArgumentSchema(
                            name=arg.name,
                            type=arg.value.base,
                            field=arg.field,
                            parent=parent,
                            notice=arg.notice,
                            optional=arg.optional,
                            sep=arg.value.sep,
                        )
                    )
                elif isinstance(arg.value, MultiVar):
                    parent.arguments.append(
                        MultiVarArgumentSchema(
                            name=arg.name,
                            type=arg.value.base.base,
                            field=arg.field,
                            parent=parent,
                            notice=arg.notice,
                            optional=arg.optional,
                            nargs=arg.value.flag,
                            keyword=True,
                        ) if isinstance(arg.value.base, KeyWordVar) else MultiVarArgumentSchema(
                            name=arg.name,
                            type=arg.value.base,
                            field=arg.field,
                            parent=parent,
                            notice=arg.notice,
                            optional=arg.optional,
                            nargs=arg.value.flag,
                        )
                    )
                else:
                    parent.arguments.append(
                        ArgumentSchema(
                            name=arg.name,
                            type=arg.value,
                            parent=parent,
                            field=arg.field,
                            notice=arg.notice,
                            optional=arg.optional,
                        )
                    )

        process_args(cmd_obj.args, cmd_data)

        def process_option(option: Option, parent: CommandSchema):
            parent.options.append(
                OptionSchema(
                    name=option.name,
                    aliases=list(option.aliases),
                    arguments=[],
                    parent=parent,
                    description=option.help_text,
                    dest=option.dest,
                    action=option.action,
                    default=option.default,
                )
            )
            process_args(option.args, parent.options[-1])

        def process_subcommand(subcommand: Subcommand, parent: CommandSchema):
            subcommand_name = CommandName(subcommand.name)
            parent.subcommands[subcommand_name] = CommandSchema(
                name=subcommand_name,
                command=subcommand_name,
                functions=[],
                description=subcommand.help_text,
                options=[],
                arguments=[],
                subcommands={},
                default=subcommand.default,
                parent=parent,
            )
            process_args(subcommand.args, parent.subcommands[subcommand_name])
            for opt in subcommand.options:
                if isinstance(opt, Subcommand):
                    process_subcommand(opt, parent.subcommands[subcommand_name])
                else:
                    process_option(opt, parent.subcommands[subcommand_name])

        for opt in cmd_obj.options:
            if isinstance(opt, Subcommand):
                process_subcommand(opt, cmd_data)
            else:
                process_option(opt, cmd_data)

        return cmd_data

    data: dict[CommandName, CommandSchema] = {}

    cmd_name = CommandName(f"{alc.namespace}_{alc.name}")
    data[cmd_name] = process_command(cmd_name, alc)

    return data


CommandName = NewType("CommandName", str)
