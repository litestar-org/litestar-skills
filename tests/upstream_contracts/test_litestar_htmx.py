import inspect
from importlib.metadata import version

from litestar_htmx import HTMXTemplate, HXLocation, ReplaceUrl, TriggerEvent


def test_litestar_htmx_050_response_helper_contract() -> None:
    assert version("litestar-htmx") == "0.5.0"
    assert list(inspect.signature(TriggerEvent).parameters)[:3] == [
        "content",
        "name",
        "after",
    ]
    assert "select" in inspect.signature(HXLocation).parameters
    assert "replace_url" in inspect.signature(ReplaceUrl).parameters
    assert "trigger_event" in inspect.signature(HTMXTemplate).parameters
