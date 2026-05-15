import importlib.util
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_papers.py"
SPEC = importlib.util.spec_from_file_location("fetch_papers", SCRIPT)
fetch_papers = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = fetch_papers
SPEC.loader.exec_module(fetch_papers)


class FetchPapersTests(unittest.TestCase):
    def test_parse_retry_after_seconds(self) -> None:
        self.assertEqual(fetch_papers.parse_retry_after("12"), 12.0)

    def test_parse_retry_after_invalid(self) -> None:
        self.assertIsNone(fetch_papers.parse_retry_after("not a retry date"))

    def test_429_retry_delay_uses_retry_after_header(self) -> None:
        error = urllib.error.HTTPError(
            url="https://export.arxiv.org/api/query",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "45"},
            fp=None,
        )

        self.assertEqual(fetch_papers.retry_delay_seconds(error, attempt=1), 45.0)

    def test_main_keeps_existing_output_when_all_fetches_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            output.write_text('{"papers": []}\n', encoding="utf-8")

            with mock.patch.object(fetch_papers, "fetch_category", side_effect=RuntimeError("rate limited")):
                with mock.patch.object(fetch_papers.time, "sleep"):
                    with mock.patch("sys.argv", ["fetch_papers.py", "--output", str(output)]):
                        fetch_papers.main()

            self.assertEqual(output.read_text(encoding="utf-8"), '{"papers": []}\n')


if __name__ == "__main__":
    unittest.main()
