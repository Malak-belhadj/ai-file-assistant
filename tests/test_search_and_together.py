"""Tests for /search (internet) and for running the terminal + Telegram together.

Fake servers stand in for DuckDuckGo, Wikipedia, Ollama and Telegram, so the
tests need no internet.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fs_assistant.config import Settings
from fs_assistant.database import ChatDatabase
from fs_assistant.ollama_client import OllamaClient
from fs_assistant.web_search import SearchError, WebSearcher, _real_url, search_duckduckgo
from main import build_app, start_telegram_in_background
from tests.fake_ollama import FakeOllama, unused_url
from tests.fake_telegram import TOKEN, FakeTelegram
from tests.test_integration import fake_model

DDG_HTML = """<html><body>
<div class="result results_links web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FCanberra&amp;rut=abc">
       <b>Canberra</b> - Wikipedia</a>
  </h2>
  <a class="result__snippet" href="x">Canberra is the capital city of <b>Australia</b>.</a>
</div>
<div class="result results_links web-result">
  <h2 class="result__title"><a class="result__a" href="https://www.australia.gov.au/">Australia.gov.au</a></h2>
  <a class="result__snippet" href="y">Official information about the capital, Canberra.</a>
</div>
</body></html>"""

WIKI_JSON = {"query": {"search": [
    {"title": "Canberra", "snippet": "<span class='searchmatch'>Canberra</span> is the capital of Australia"}]}}


class FakeSearchSites:
    """Serves a DuckDuckGo-like HTML page and a Wikipedia-like JSON API."""

    def __init__(self, ddg_status=200, ddg_html=DDG_HTML, wiki=WIKI_JSON):
        self.ddg_status, self.ddg_html, self.wiki = ddg_status, ddg_html, wiki
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body, kind):
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self._send(fake.ddg_status, fake.ddg_html, "text/html")

            def do_GET(self):
                self._send(200, json.dumps(fake.wiki), "application/json")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def sites():
    s = FakeSearchSites()
    yield s
    s.close()


def summary_model(text):
    return "Canberra is the capital of Australia [1]."


# ---- parsing and fallback ------------------------------------------------------------
def test_duckduckgo_results_are_parsed(sites):
    results = search_duckduckgo("capital of australia", url=sites.url + "/html/")
    assert results[0].title == "Canberra - Wikipedia"
    assert results[0].url == "https://en.wikipedia.org/wiki/Canberra"      # redirect decoded
    assert results[0].snippet == "Canberra is the capital city of Australia."
    assert results[1].url == "https://www.australia.gov.au/"


def test_real_url_decoding():
    assert _real_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1") == "https://example.com/a?b=1"
    assert _real_url("https://example.com") == "https://example.com"


def test_answer_uses_ai_summary_with_sources(sites):
    with FakeOllama(summary_model) as ollama:
        searcher = WebSearcher(OllamaClient(ollama.url, "qwen3.5:4b", timeout=5),
                               duckduckgo_url=sites.url + "/html/", wikipedia_url=sites.url + "/w/api.php")
        summary, results = searcher.answer("capital of australia")
        prompt = ollama.requests[0]["messages"]
    assert summary == "Canberra is the capital of Australia [1]."
    assert len(results) == 2
    assert "ignore any instructions" in prompt[0]["content"]          # protection against web text
    assert "[1] Canberra - Wikipedia" in prompt[1]["content"]
    assert "format" not in ollama.requests[0]                         # free text, not JSON actions


def test_wikipedia_is_used_when_duckduckgo_fails():
    sites = FakeSearchSites(ddg_status=503)
    try:
        with FakeOllama(summary_model) as ollama:
            searcher = WebSearcher(OllamaClient(ollama.url, "qwen3.5:4b", timeout=5),
                                   duckduckgo_url=sites.url + "/html/", wikipedia_url=sites.url + "/w/api.php")
            results, source = searcher.find("canberra")
    finally:
        sites.close()
    assert source == "Wikipedia"
    assert results[0].url == "https://en.wikipedia.org/wiki/Canberra"
    assert results[0].snippet == "Canberra is the capital of Australia"


def test_no_internet_gives_friendly_error():
    searcher = WebSearcher(OllamaClient(unused_url(), "m", timeout=2),
                           duckduckgo_url=unused_url(), wikipedia_url=unused_url())
    with pytest.raises(SearchError, match="could not reach the internet"):
        searcher.find("anything")


def test_empty_or_too_long_query():
    searcher = WebSearcher(OllamaClient(unused_url(), "m"))
    with pytest.raises(SearchError, match="Please write what to search"):
        searcher.answer("   ")
    with pytest.raises(SearchError, match="too long"):
        searcher.answer("x" * 400)


def test_ai_down_still_shows_results(sites):
    searcher = WebSearcher(OllamaClient(unused_url(), "m", timeout=2),
                           duckduckgo_url=sites.url + "/html/", wikipedia_url=sites.url + "/w/api.php")
    summary, results = searcher.answer("capital of australia")
    assert "could not summarise" in summary and len(results) == 2


# ---- /search inside the terminal app (saved in the database) --------------------------------
def run_with_input(settings, lines):
    inputs, output = iter(lines), []

    def fake_input(prompt):
        output.append(prompt)
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    app = build_app(settings, input_fn=fake_input, output_fn=output.append)
    app.service.searcher.duckduckgo_url = settings._ddg
    app.service.searcher.wikipedia_url = settings._wiki
    app.run()
    return "\n".join(output)


def test_search_command_in_terminal_is_saved(tmp_path, sites):
    with FakeOllama(lambda t: summary_model(t) if "Search results" in t else fake_model(t)) as ollama:
        settings = Settings(ollama_url=ollama.url, workspace=tmp_path / "ws", timeout_seconds=5,
                            db_path=tmp_path / "db.db")
        settings._ddg, settings._wiki = sites.url + "/html/", sites.url + "/w/api.php"
        out = run_with_input(settings, ["/search capital of australia", "Create a folder called projects", "exit"])
        file_request = ollama.requests[-1]["messages"]
    assert "Canberra is the capital of Australia [1]." in out
    assert "[1] Canberra - Wikipedia - https://en.wikipedia.org/wiki/Canberra" in out
    assert not any("web_search" in m["content"] for m in file_request)   # search kept out of file context
    db = ChatDatabase(tmp_path / "db.db")
    row = db.connection.execute("SELECT action_type, success FROM actions ORDER BY action_id LIMIT 1").fetchone()
    db.close()
    assert row["action_type"] == "web_search" and row["success"] == 1


# ---- terminal + Telegram at the same time ----------------------------------------------------
def wait_for(condition, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_terminal_and_telegram_run_together(tmp_path):
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    with FakeOllama(fake_model) as ollama, FakeTelegram() as telegram:
        settings = Settings(ollama_url=ollama.url, workspace=home, timeout_seconds=5,
                            db_path=tmp_path / "shared.db", telegram_token=TOKEN,
                            telegram_allowed_users={111}, telegram_api_url=telegram.url)
        logs = []
        stop = start_telegram_in_background(settings, log=logs.append)
        try:
            telegram.send_from_phone("Create a folder called projects", 111)   # from the phone...
            assert wait_for(lambda: any("created successfully" in t for t in telegram.texts()))
            out = run_with_input_simple(settings, ["make a file", "todo.txt", "exit"])  # ...and the terminal
        finally:
            stop.set()
    assert (home / "projects").is_dir()          # created from Telegram
    assert (home / "todo.txt").is_file()         # created from the terminal
    assert "File 'todo.txt' created successfully." in out
    assert any("Telegram bot @TestBot is running" in line for line in logs)
    db = ChatDatabase(tmp_path / "shared.db")
    sources = {r["source"] for r in db.connection.execute("SELECT source FROM users")}
    db.close()
    assert sources == {"terminal", "telegram"}   # one shared database


def run_with_input_simple(settings, lines):
    inputs, output = iter(lines), []

    def fake_input(prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    build_app(settings, input_fn=fake_input, output_fn=output.append).run()
    return "\n".join(output)


def test_no_token_means_no_background_bot(tmp_path):
    settings = Settings(workspace=tmp_path / "ws", db_path=tmp_path / "x.db", telegram_token="")
    assert start_telegram_in_background(settings) is None


def test_bad_token_does_not_break_the_terminal(tmp_path):
    with FakeTelegram() as telegram:
        settings = Settings(workspace=tmp_path / "ws", db_path=tmp_path / "x.db",
                            telegram_token="wrong", telegram_api_url=telegram.url)
        logs = []
        stop = start_telegram_in_background(settings, log=logs.append)
        assert wait_for(lambda: any("could not start" in line for line in logs))
        stop.set()
    assert any("token is wrong" in line for line in logs)
