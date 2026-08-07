from importlib.metadata import version

from litestar_granian.cli import run_command


def test_litestar_granian_016_cli_contract() -> None:
    assert version("litestar-granian") == "0.16.0"
    options = {option for parameter in run_command.params for option in parameter.opts}
    assert {"--runtime-threads", "--granian-access-log", "--granian-access-log-fmt"} <= options
    assert {
        "--threads",
        "--threading-mode",
        "--log-access",
        "--log-access-format",
        "--log-access-fmt",
    }.isdisjoint(options)
