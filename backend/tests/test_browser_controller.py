import pytest

from app.browser_controller import BrowserController, _to_playwright_key

PAGE_HTML = """<!doctype html>
<html><head><title>Rove Test Page</title></head>
<body style="margin:0">
<input id="box" style="width:600px;height:60px;font-size:20px">
</body></html>
"""


@pytest.fixture
def page_url(tmp_path):
    html_file = tmp_path / "page.html"
    html_file.write_text(PAGE_HTML)
    return f"file://{html_file}"


@pytest.fixture
def controller():
    controller = BrowserController(headless=True)
    controller.launch()
    yield controller
    controller.close()


def test_navigate_sets_url_and_title(controller, page_url) -> None:
    controller.navigate(page_url)
    assert controller.current_url == page_url
    assert controller.page_title == "Rove Test Page"


def test_click_then_type_reaches_focused_input(controller, page_url) -> None:
    controller.navigate(page_url)
    box = controller.page.locator("#box").bounding_box()
    controller.click(int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))

    controller.type("hello rove")

    assert controller.page.locator("#box").input_value() == "hello rove"


def test_scroll_and_keypress_do_not_raise(controller, page_url) -> None:
    controller.navigate(page_url)
    controller.scroll("down", amount=2)
    controller.keypress("cmd+a")


def test_wait_blocks_for_roughly_the_given_duration(controller, page_url) -> None:
    controller.navigate(page_url)
    controller.wait(0.1)


def test_screenshot_returns_png_bytes(controller, page_url) -> None:
    controller.navigate(page_url)
    data = controller.screenshot()
    assert data.startswith(b"\x89PNG")


def test_get_active_application_reflects_launch_state() -> None:
    controller = BrowserController(headless=True)
    assert controller.get_active_application() is None
    controller.launch()
    try:
        assert controller.get_active_application() == "Chrome"
    finally:
        controller.close()


def test_open_and_focus_application_not_supported(controller) -> None:
    with pytest.raises(NotImplementedError):
        controller.open_application("Finder")
    with pytest.raises(NotImplementedError):
        controller.focus_application("Finder")


def test_using_controller_before_launch_raises() -> None:
    controller = BrowserController(headless=True)
    with pytest.raises(RuntimeError):
        controller.navigate("about:blank")


@pytest.mark.parametrize(
    "keys, expected",
    [
        ("cmd+t", "Meta+T"),
        ("ctrl+shift+a", "Control+Shift+A"),
        ("Enter", "Enter"),
        ("cmd+Enter", "Meta+Enter"),
    ],
)
def test_to_playwright_key_translation(keys, expected) -> None:
    assert _to_playwright_key(keys) == expected
