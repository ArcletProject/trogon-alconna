from trogon import tui
from arclet.alconna import Alconna, CommandMeta

alc = Alconna(
    "trogon",
    meta=CommandMeta(
        description="A CLI framework for Arclet",
        usage="trogon [command] [options] [arguments]",
        example="trogon help",
    ),
)
tui(alc)

alc.parse("trogon tui")