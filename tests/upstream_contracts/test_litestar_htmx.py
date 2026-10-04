"""Upstream contract verification for litestar-htmx 0.5.0."""

import inspect
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast, get_args

import litestar.plugins.htmx as litestar_plugins_htmx
import litestar_htmx
import litestar_htmx.request as htmx_request
import litestar_htmx.response as htmx_response
import litestar_htmx.types as htmx_types
import pytest
from litestar import Litestar, Request, get
from litestar.config.app import AppConfig
from litestar.exceptions import ImproperlyConfiguredException
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.testing import TestClient
from litestar_htmx import (
    ClientRedirect,
    ClientRefresh,
    EventAfterType,
    HTMXConfig,
    HTMXDetails,
    HTMXHeaders,
    HtmxHeaderType,
    HTMXPlugin,
    HTMXRequest,
    HTMXTemplate,
    HXLocation,
    HXStopPolling,
    LocationType,
    PushUrl,
    PushUrlType,
    ReplaceUrl,
    Reswap,
    ReSwapMethod,
    Retarget,
    TriggerEvent,
    TriggerEventType,
)
from litestar_vite import ComponentResponse, PathConfig, ViteConfig, VitePlugin, render_fragment
from litestar_vite.fragments import vite_fragment


def test_litestar_htmx_050_exports_and_plugin_reexports() -> None:
    """Verify public exports of litestar_htmx and compatibility re-exports in litestar.plugins.htmx."""
    assert version("litestar-htmx") == "0.5.0"
    expected_exports = {
        "ClientRedirect",
        "ClientRefresh",
        "EventAfterType",
        "HTMXConfig",
        "HTMXDetails",
        "HTMXHeaders",
        "HTMXPlugin",
        "HTMXRequest",
        "HTMXTemplate",
        "HXLocation",
        "HXStopPolling",
        "HtmxHeaderType",
        "LocationType",
        "PushUrl",
        "PushUrlType",
        "ReSwapMethod",
        "ReplaceUrl",
        "Reswap",
        "Retarget",
        "TriggerEvent",
        "TriggerEventType",
    }
    assert set(litestar_htmx.__all__) == expected_exports
    assert expected_exports.issubset(set(litestar_plugins_htmx.__all__))
    assert "_utils" in litestar_plugins_htmx.__all__
    for symbol in expected_exports:
        assert getattr(litestar_plugins_htmx, symbol) is getattr(litestar_htmx, symbol)


def test_litestar_htmx_050_plugin_and_config_contract() -> None:
    """Verify HTMXConfig defaults and HTMXPlugin.on_app_init behavior."""
    default_config = HTMXConfig()
    assert default_config.set_request_class_globally is True

    plugin = HTMXPlugin()
    assert plugin.config == default_config

    app_config = plugin.on_app_init(AppConfig())
    assert set(app_config.signature_types) == {
        HTMXRequest,
        ClientRedirect,
        ClientRefresh,
        HTMXTemplate,
        HXLocation,
        HXStopPolling,
        PushUrl,
        ReplaceUrl,
        Reswap,
        Retarget,
        TriggerEvent,
    }

    app_default = Litestar(route_handlers=[], plugins=[plugin])
    assert cast("Any", app_default).request_class is HTMXRequest

    class CustomRequest(HTMXRequest):
        """Custom HTMXRequest subclass."""

    app_preserved = Litestar(route_handlers=[], request_class=CustomRequest, plugins=[plugin])
    assert cast("Any", app_preserved).request_class is CustomRequest

    disabled_plugin = HTMXPlugin(config=HTMXConfig(set_request_class_globally=False))
    app_disabled = Litestar(route_handlers=[], plugins=[disabled_plugin])
    assert cast("Any", app_disabled).request_class is Request


def test_litestar_htmx_050_request_and_details_contract() -> None:
    """Verify HTMXRequest and HTMXDetails header parsing, URL resolution, and JSON decoding."""

    @get("/inspect")
    async def inspect_htmx(request: HTMXRequest) -> dict[str, Any]:
        assert isinstance(request.htmx, HTMXDetails)
        return {
            "is_htmx": bool(request.htmx),
            "boosted": request.htmx.boosted,
            "current_url": request.htmx.current_url,
            "current_url_abs_path": request.htmx.current_url_abs_path,
            "history_restore_request": request.htmx.history_restore_request,
            "prompt": request.htmx.prompt,
            "target": request.htmx.target,
            "trigger": request.htmx.trigger,
            "trigger_name": request.htmx.trigger_name,
            "triggering_event": request.htmx.triggering_event,
        }

    app = Litestar(route_handlers=[inspect_htmx], plugins=[HTMXPlugin()])
    with TestClient(app=app) as client:
        non_htmx = client.get("/inspect")
        assert non_htmx.status_code == 200
        assert non_htmx.json() == {
            "is_htmx": False,
            "boosted": False,
            "current_url": None,
            "current_url_abs_path": None,
            "history_restore_request": False,
            "prompt": None,
            "target": None,
            "trigger": None,
            "trigger_name": None,
            "triggering_event": None,
        }

        same_origin = client.get(
            "/inspect",
            headers={
                "HX-Request": "true",
                "HX-Boosted": "true",
                "HX-Current-URL": "http://testserver.local/items?page=2#top",
                "HX-History-Restore-Request": "true",
                "HX-Prompt": "hello%20world",
                "HX-Prompt-URI-AutoEncoded": "true",
                "HX-Target": "item-list",
                "HX-Trigger": "load-btn",
                "HX-Trigger-Name": "load",
                "Triggering-Event": '{"type":"click","detail":{"id":7}}',
            },
        )
        assert same_origin.status_code == 200
        assert same_origin.json() == {
            "is_htmx": True,
            "boosted": True,
            "current_url": "http://testserver.local/items?page=2#top",
            "current_url_abs_path": "/items?page=2#top",
            "history_restore_request": True,
            "prompt": "hello world",
            "target": "item-list",
            "trigger": "load-btn",
            "trigger_name": "load",
            "triggering_event": {"type": "click", "detail": {"id": 7}},
        }

        cross_origin_and_bad_event = client.get(
            "/inspect",
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "https://other.example/items",
                "Triggering-Event": "{invalid-json",
            },
        )
        assert cross_origin_and_bad_event.status_code == 200
        data = cross_origin_and_bad_event.json()
        assert data["current_url"] == "https://other.example/items"
        assert data["current_url_abs_path"] is None
        assert data["triggering_event"] is None


def test_litestar_htmx_050_response_helper_contract() -> None:
    """Verify signatures, status codes, and emitted headers across all HTMX response classes."""
    assert list(inspect.signature(TriggerEvent).parameters)[:4] == [
        "content",
        "name",
        "after",
        "params",
    ]
    assert list(inspect.signature(HXLocation).parameters)[:8] == [
        "redirect_to",
        "source",
        "event",
        "target",
        "select",
        "swap",
        "hx_headers",
        "values",
    ]
    assert list(inspect.signature(HTMXTemplate).parameters)[:6] == [
        "push_url",
        "re_swap",
        "re_target",
        "trigger_event",
        "params",
        "after",
    ]
    assert "replace_url" in inspect.signature(ReplaceUrl).parameters
    assert "push_url" in inspect.signature(PushUrl).parameters

    stop_polling = HXStopPolling()
    assert stop_polling.status_code == 286

    redirect = ClientRedirect("/login?next=/items")
    assert redirect.headers["HX-Redirect"] == "/login?next=/items"
    assert "Location" not in redirect.headers

    refresh = ClientRefresh()
    assert refresh.headers["HX-Refresh"] == "true"

    pushed = PushUrl("ok", "/items")
    assert pushed.status_code == 200
    assert pushed.headers["HX-Push-Url"] == "/items"
    assert PushUrl("ok", False).headers["HX-Push-Url"] == "false"
    assert PushUrl("ok", True).headers["HX-Push-Url"] == "false"

    replaced = ReplaceUrl("ok", "/items")
    assert replaced.status_code == 200
    assert replaced.headers["HX-Replace-Url"] == "/items"
    assert ReplaceUrl("ok", False).headers["HX-Replace-Url"] == "false"
    assert ReplaceUrl("ok", True).headers["HX-Replace-Url"] == "false"

    reswapped = Reswap("ok", "outerHTML")
    assert reswapped.headers["HX-Reswap"] == "outerHTML"

    retargeted = Retarget("ok", "#item-list")
    assert retargeted.headers["HX-Retarget"] == "#item-list"

    trig_receive = TriggerEvent("ok", "itemCreated", after="receive", params={"id": 42})
    assert json.loads(trig_receive.headers["HX-Trigger"]) == {"itemCreated": {"id": 42}}

    trig_settle = TriggerEvent("ok", "itemSettled", after="settle")
    assert json.loads(trig_settle.headers["HX-Trigger-After-Settle"]) == {"itemSettled": {}}

    trig_swap = TriggerEvent("ok", "itemSwapped", after="swap")
    assert json.loads(trig_swap.headers["HX-Trigger-After-Swap"]) == {"itemSwapped": {}}

    with pytest.raises(ImproperlyConfiguredException):
        TriggerEvent("ok", "badEvent", after=None)

    location = HXLocation(
        redirect_to="/items",
        source="#create-item",
        event="submit",
        target="#content",
        select="#item-list",
        swap="innerHTML",
        hx_headers={"X-View": "compact"},
        values={"created": "true"},
    )
    assert "Location" not in location.headers
    assert json.loads(location.headers["HX-Location"]) == {
        "path": "/items",
        "source": "#create-item",
        "event": "submit",
        "target": "#content",
        "select": "#item-list",
        "swap": "innerHTML",
        "hx_headers": {"X-View": "compact"},
        "values": {"created": "true"},
    }

    template = HTMXTemplate(
        template_name="partials/item-list.html",
        context={"items": []},
        push_url=False,
        re_swap="outerHTML",
        re_target="#item-list",
        trigger_event="itemsLoaded",
        params={"count": 0},
        after="receive",
    )
    assert template.headers["HX-Push-Url"] == "false"
    assert template.headers["HX-Reswap"] == "outerHTML"
    assert template.headers["HX-Retarget"] == "#item-list"
    assert json.loads(template.headers["HX-Trigger"]) == {"itemsLoaded": {"count": 0}}

    with pytest.raises(ImproperlyConfiguredException):
        HTMXTemplate(template_name="partials/item-list.html", trigger_event="itemsLoaded")


def test_litestar_htmx_050_types_and_headers_enum_contract() -> None:
    """Verify exported type aliases, TypedDict schemas, and HTMXHeaders enum values."""
    assert issubclass(HTMXRequest, Request)
    assert set(get_args(EventAfterType)) == {"receive", "settle", "swap", None}
    assert set(get_args(PushUrlType)) == {str, bool}
    assert set(get_args(ReSwapMethod)) == {
        "innerHTML",
        "outerHTML",
        "beforebegin",
        "afterbegin",
        "beforeend",
        "afterend",
        "delete",
        "none",
        None,
    }
    assert LocationType.__required_keys__ == frozenset(
        {
            "path",
            "source",
            "event",
            "target",
            "select",
            "swap",
            "values",
            "hx_headers",
        }
    )
    assert TriggerEventType.__required_keys__ == frozenset({"name", "params", "after"})
    assert HtmxHeaderType.__optional_keys__ == frozenset(
        {
            "location",
            "redirect",
            "refresh",
            "push_url",
            "replace_url",
            "re_swap",
            "re_target",
            "trigger_event",
        }
    )
    assert HTMXHeaders.REQUEST.value == "HX-Request"
    assert HTMXHeaders.BOOSTED.value == "HX-Boosted"
    assert HTMXHeaders.CURRENT_URL.value == "HX-Current-URL"
    assert HTMXHeaders.HISTORY_RESTORE_REQUEST.value == "HX-History-Restore-Request"
    assert HTMXHeaders.PROMPT.value == "HX-Prompt"
    assert HTMXHeaders.TARGET.value == "HX-Target"
    assert HTMXHeaders.TRIGGER_ID.value == "HX-Trigger"
    assert HTMXHeaders.TRIGGER_NAME.value == "HX-Trigger-Name"
    assert HTMXHeaders.TRIGGERING_EVENT.value == "Triggering-Event"
    assert HTMXHeaders.REDIRECT.value == "HX-Redirect"
    assert HTMXHeaders.REFRESH.value == "HX-Refresh"
    assert HTMXHeaders.PUSH_URL.value == "HX-Push-Url"
    assert HTMXHeaders.REPLACE_URL.value == "HX-Replace-Url"
    assert HTMXHeaders.RE_SWAP.value == "HX-Reswap"
    assert HTMXHeaders.RE_TARGET.value == "HX-Retarget"
    assert HTMXHeaders.LOCATION.value == "HX-Location"
    assert HTMXHeaders.TRIGGER_EVENT.value == "HX-Trigger"
    assert HTMXHeaders.TRIGGER_AFTER_SETTLE.value == "HX-Trigger-After-Settle"
    assert HTMXHeaders.TRIGGER_AFTER_SWAP.value == "HX-Trigger-After-Swap"

    assert set(htmx_request.__all__) == {"HTMXDetails", "HTMXHeaders", "HTMXRequest"}
    assert set(htmx_types.__all__) == {
        "EventAfterType",
        "HtmxHeaderType",
        "LocationType",
        "PushUrlType",
        "ReSwapMethod",
        "TriggerEventType",
    }
    assert set(htmx_response.__all__) == {
        "ClientRedirect",
        "ClientRefresh",
        "HTMXTemplate",
        "HXLocation",
        "HXStopPolling",
        "PushUrl",
        "ReplaceUrl",
        "Reswap",
        "Retarget",
        "TriggerEvent",
    }


def test_litestar_htmx_and_litestar_vite_0320_template_integration(tmp_path: Any) -> None:
    """Verify litestar-vite 0.32.0 template/htmx mode and Jinja integration alongside HTMXPlugin."""
    assert version("litestar-vite") == "0.32.0"
    assert render_fragment is vite_fragment

    htmx_alias_config = ViteConfig(mode="htmx")
    assert htmx_alias_config.mode == "template"
    assert htmx_alias_config.serves_own_html is True

    template_dir = Path(tmp_path) / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    resource_dir = Path(tmp_path) / "resources"
    resource_dir.mkdir(parents=True, exist_ok=True)

    vite = VitePlugin(
        config=ViteConfig(
            mode="template",
            paths=PathConfig(root=Path(tmp_path), resource_dir="resources"),
        )
    )
    templates = TemplateConfig(
        directory=template_dir,
        engine=JinjaTemplateEngine,
    )
    app = Litestar(
        route_handlers=[],
        plugins=[vite, HTMXPlugin()],
        template_config=templates,
    )
    assert cast("Any", app).request_class is HTMXRequest
    jinja_globals = templates.engine_instance.engine.globals
    for callable_name in ("vite_hmr", "vite", "vite_static", "vite_routes", "vite_fragment"):
        assert callable_name in jinja_globals

    comp_resp = ComponentResponse("components/Card.tsx", props={"id": 1}, mode="static")
    assert comp_resp.component == "components/Card.tsx"
    assert comp_resp.props == {"id": 1}
    assert comp_resp.mode == "static"
