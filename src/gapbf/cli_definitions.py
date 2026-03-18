from typing import TypedDict

from rich.console import Console

from .Output import Output
from .PathHandler import ADBHandler, PathHandler, PrintHandler, TestHandler


class HandlerSpec(TypedDict):
    class_: type[PathHandler]
    help: str


console = Console()
output = Output(console)
handler_classes: dict[str, HandlerSpec] = {
    "a": {"class_": ADBHandler, "help": "Attempt decryption via ADB shell on Android device"},
    "p": {"class_": PrintHandler, "help": "Print attempted paths to the console"},
    "t": {"class_": TestHandler, "help": "Run mock brute force against test_path in config"},
}
