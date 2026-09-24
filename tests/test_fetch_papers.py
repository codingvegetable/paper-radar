import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_papers.py"
SPEC = importlib.util.spec_from_file_location("fetch_papers", SCRIPT)
fetch_papers = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = fetch_papers
SPEC.loader.exec_module(fetch_papers)


ATOM_FEED = b'''<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2609.12345v1</id>
    <title>Robot manipulation</title>
    <summary>A robot grasping experiment.</summary>
    <published>2026-09-23T12:00:00Z</published>
    <updated>2026-09-23T12:00:00Z</updated>
    <author><name>Test Author</name></author>
    <category term="cs.RO"/>
    <link rel="alternate" href="https://arxiv.org/abs/2609.12345v1"/>
    <link title="pdf" href="https://arxiv.org/pdf/2609.12345v1"/>
  </entry>
</feed>'''


def atom_response(body=ATOM_FEED):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = body
    return response


def http_error(code, headers=None):
    return urllib.error.HTTPError(
        "https://export.arxiv.org/api/query", code, "upstream error", headers or {}, None
    )


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

    def test_406_falls_back_to_post_with_the_same_query(self) -> None:
        with mock.patch.object(fetch_papers.urllib.request, "urlopen", side_effect=[http_error(406), atom_response()]) as request:
            with mock.patch.object(fetch_papers.time, "sleep") as sleep:
                papers = fetch_papers.fetch_category("manipulation", fetch_papers.CATEGORIES["manipulation"], 45, retries=1)

        get_request, post_request = [call.args[0] for call in request.call_args_list]
        self.assertEqual(get_request.get_method(), "GET")
        self.assertEqual(post_request.get_method(), "POST")
        self.assertEqual(post_request.full_url, "https://export.arxiv.org/api/query")
        self.assertEqual(
            urllib.parse.parse_qs(urllib.parse.urlparse(get_request.full_url).query),
            urllib.parse.parse_qs(post_request.data.decode("utf-8")),
        )
        self.assertEqual(post_request.get_header("Accept"), "application/atom+xml")
        sleep.assert_called_once_with(fetch_papers.MIN_REQUEST_INTERVAL_SECONDS)
        self.assertEqual(papers[0]["id"], "2609.12345v1")
        self.assertEqual(papers[0]["source_categories"], ["manipulation"])
        self.assertEqual(papers[0]["authors"], ["Test Author"])

    def test_post_retries_do_not_repeat_rejected_get(self) -> None:
        with mock.patch.object(fetch_papers.urllib.request, "urlopen", side_effect=[http_error(406), http_error(503), atom_response()]) as request:
            with mock.patch.object(fetch_papers.time, "sleep"):
                papers = fetch_papers.fetch_category("uav", fetch_papers.CATEGORIES["uav"], 45, retries=2)

        self.assertEqual([call.args[0].get_method() for call in request.call_args_list], ["GET", "POST", "POST"])
        self.assertEqual(len(papers), 1)

    def test_406_on_both_methods_fails_without_repeating_requests(self) -> None:
        with mock.patch.object(fetch_papers.urllib.request, "urlopen", side_effect=[http_error(406), http_error(406)]) as request:
            with mock.patch.object(fetch_papers.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "failed to fetch.*406"):
                    fetch_papers.fetch_category("uav", fetch_papers.CATEGORIES["uav"], 45, retries=4)
        self.assertEqual(request.call_count, 2)

    def test_429_still_waits_before_retrying_get(self) -> None:
        with mock.patch.object(fetch_papers.urllib.request, "urlopen", side_effect=[http_error(429, {"Retry-After": "45"}), atom_response()]) as request:
            with mock.patch.object(fetch_papers.time, "sleep") as sleep:
                fetch_papers.fetch_category("uav", fetch_papers.CATEGORIES["uav"], 45, retries=2)
        sleep.assert_called_once_with(45.0)
        self.assertEqual([call.args[0].get_method() for call in request.call_args_list], ["GET", "GET"])

    def test_error_responses_are_not_accepted_as_papers(self) -> None:
        error_feed = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <id>http://arxiv.org/api/errors#incorrect_id_format</id>
          <title>Error</title><summary>incorrect id format</summary>
        </entry></feed>'''
        for body in (error_feed, b"<html>Service unavailable</html>", b"invalid XML"):
            with self.subTest(body=body):
                with mock.patch.object(fetch_papers.urllib.request, "urlopen", return_value=atom_response(body)):
                    with self.assertRaises(RuntimeError):
                        fetch_papers.fetch_category("uav", fetch_papers.CATEGORIES["uav"], 45, retries=1)

    def test_valid_empty_atom_feed_is_not_a_transport_failure(self) -> None:
        with mock.patch.object(fetch_papers.urllib.request, "urlopen", return_value=atom_response(b'<feed xmlns="http://www.w3.org/2005/Atom"/>')):
            self.assertEqual(fetch_papers.fetch_category("uav", fetch_papers.CATEGORIES["uav"], 45, retries=1), [])

    def test_main_keeps_existing_output_when_all_fetches_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            output.write_text('{"papers": []}\n', encoding="utf-8")

            with mock.patch.object(fetch_papers, "fetch_category", side_effect=RuntimeError("rate limited")):
                with mock.patch.object(fetch_papers.time, "sleep"):
                    with mock.patch("sys.argv", ["fetch_papers.py", "--output", str(output)]):
                        fetch_papers.main()

            self.assertEqual(output.read_text(encoding="utf-8"), '{"papers": []}\n')

    def run_main(self, output, incoming, *extra_args):
        with mock.patch.object(fetch_papers, "fetch_category", side_effect=incoming):
            with mock.patch.object(fetch_papers.time, "sleep"):
                with mock.patch("sys.argv", ["fetch_papers.py", "--output", str(output), *extra_args]):
                    fetch_papers.main()

    def paper(self, published=None):
        return {
            "id": "2609.12345v1",
            "title": "Robot manipulation",
            "abstract": "A robot grasping experiment.",
            "published": published or fetch_papers.utc_now_iso(),
            "source_categories": ["manipulation"],
        }

    def test_strict_mode_fails_and_preserves_output_on_total_or_partial_failure(self) -> None:
        scenarios = (
            [RuntimeError("HTTP 406")] * 4,
            [[self.paper()], RuntimeError("HTTP 406"), [], []],
        )
        for incoming in scenarios:
            with self.subTest(incoming=incoming), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "papers.json"
                old = b'{"updated_at":"2026-09-16T00:00:00Z","papers":[{"id":"old"}]}\n'
                output.write_bytes(old)
                with self.assertRaisesRegex(SystemExit, "Failed categories"):
                    self.run_main(output, incoming, "--fail-when-stale")
                self.assertEqual(output.read_bytes(), old)

    def test_no_recent_papers_never_overwrite_existing_data(self) -> None:
        for strict in (False, True):
            with self.subTest(strict=strict), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "papers.json"
                output.write_bytes(b'{"papers":[{"id":"old"}]}\n')
                incoming = [[self.paper("2000-01-01T00:00:00Z")], [], [], []]
                if strict:
                    with self.assertRaisesRegex(SystemExit, "No recent papers"):
                        self.run_main(output, incoming, "--fail-when-stale")
                else:
                    self.run_main(output, incoming)
                self.assertEqual(output.read_bytes(), b'{"papers":[{"id":"old"}]}\n')

    def test_strict_mode_rejects_empty_results_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            with self.assertRaisesRegex(SystemExit, "No papers were fetched"):
                self.run_main(output, [[], [], [], []], "--fail-when-stale")
            self.assertFalse(output.exists())

    def test_successful_fetch_writes_new_timestamp_and_deduplicated_papers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            output.write_text('{"updated_at":"2000-01-01T00:00:00Z","papers":[]}', encoding="utf-8")
            self.run_main(output, [[self.paper()], [self.paper()], [], []], "--fail-when-stale")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertNotEqual(payload["updated_at"], "2000-01-01T00:00:00Z")
            self.assertEqual(len(payload["papers"]), 1)
            self.assertEqual(payload["papers"][0]["id"], "2609.12345v1")
            self.assertIn("manipulation", payload["papers"][0]["category_keys"])


if __name__ == "__main__":
    unittest.main()
