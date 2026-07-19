import hashlib
import json
import pathlib
import unittest
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image
from renderer import app
from tools.release_version import next_version, release_kind


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


NOW = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)


class ParserContract(unittest.TestCase):
    def fixture_json(self, name):
        return json.loads((FIXTURES / name).read_text())

    def test_claude_fixture(self):
        result = app.parse_claude_usage(
            self.fixture_json("claude-usage.json"), now=NOW
        )
        self.assertEqual(result["session_pct"], 42)
        self.assertEqual(result["week_pct"], 63)
        self.assertEqual(result["extra_pct"], 12)
        self.assertEqual(result["updated"], NOW.isoformat())

    def test_codex_fixture(self):
        result = app.parse_codex_usage(
            self.fixture_json("codex-usage.json"), now=NOW
        )
        self.assertEqual(
            [(item["label"], item["pct"]) for item in result["windows"]],
            [("5h", 25), ("7d", 50)],
        )
        self.assertEqual(result["credit_balance"], 17)
        self.assertEqual(result["updated"], NOW.isoformat())

    def test_opencode_fixture(self):
        result = app.parse_opencode_usage(
            (FIXTURES / "opencode-usage.html").read_text(), now=NOW
        )
        self.assertEqual(
            (result["fivehr_pct"], result["week_pct"], result["month_pct"]),
            (31, 53, 70),
        )
        self.assertEqual(result["updated"], NOW.isoformat())


class RenderContract(unittest.TestCase):
    def test_empty_fixture_render_is_deterministic_png(self):
        widgets = app.DASH_WIDGETS
        try:
            app.DASH_WIDGETS = []
            first = app.render(rotate=0)
            second = app.render(rotate=0)
        finally:
            app.DASH_WIDGETS = widgets
        self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(second).digest())
        image = Image.open(BytesIO(first))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.mode, "L")
        self.assertEqual(image.size, (app.KINDLE_W, app.KINDLE_H))


class ReleaseVersionContract(unittest.TestCase):
    TAGS = ["v0.1.0", "not-a-version", "v0.1.1"]

    def test_minor_is_default(self):
        self.assertEqual(next_version(self.TAGS, []), "v0.2.0")

    def test_explicit_bumps(self):
        self.assertEqual(next_version(self.TAGS, ["release:patch"]), "v0.1.2")
        self.assertEqual(next_version(self.TAGS, ["release:minor"]), "v0.2.0")
        self.assertEqual(next_version(self.TAGS, ["release:major"]), "v1.0.0")

    def test_none_skips_release(self):
        self.assertIsNone(next_version(self.TAGS, ["release:none"]))

    def test_conflicts_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "conflicting release labels"):
            release_kind(["release:patch", "release:major"])


if __name__ == "__main__":
    unittest.main()
