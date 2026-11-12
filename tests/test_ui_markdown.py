from jarvis.ui.widgets.chat_panel import render_markdown


def test_code_fence_becomes_pre_block() -> None:
    output = render_markdown("```python\nprint('hello')\n```")
    assert "<pre" in output
    assert "print(" in output
    assert "\\n" not in output.split("<pre", 1)[1]


def test_code_fence_escapes_html() -> None:
    output = render_markdown("```html\n<script>alert(1)</script>\n```")
    assert "&lt;script&gt;" in output
    assert "<script>" not in output


def test_inline_formatting_still_works() -> None:
    output = render_markdown("**bold** and `code` and [x](https://example.com)")
    assert "<b>bold</b>" in output
    assert "code" in output
    assert "&lt;b&gt;" not in output


def test_text_and_code_mix() -> None:
    output = render_markdown("before\n\n```\ncode\n```\n\nafter **yes**")
    assert output.index("before") < output.index("<pre")
    assert output.index("</pre>") < output.index("after")
    assert "<b>yes</b>" in output