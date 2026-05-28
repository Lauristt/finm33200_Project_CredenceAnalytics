"""Local web UI for memo-level credibility reports."""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .config import ToolkitConfig
from .errors import error_payload
from .reporting import build_verification_report


DEFAULT_PORT = 8765


def run_server(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    config: ToolkitConfig | None = None,
) -> None:
    """Run the local report UI."""
    handler = _handler(config or ToolkitConfig.from_env())
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Credence Analytics UI running at http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Credence Analytics report UI.")
    parser.add_argument("--host", default=os.getenv("CREDIBILITY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", os.getenv("CREDIBILITY_PORT", DEFAULT_PORT))))
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()
    run_server(args.host, args.port, ToolkitConfig.from_env(args.env_file))


def _handler(config: ToolkitConfig):
    class CredenceHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/app"}:
                self._send(HTTPStatus.OK, HTML, "text/html; charset=utf-8")
                return
            if path == "/health":
                self._json({"status": "ok"})
                return
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/report/stream":
                self._stream_report()
                return
            if path != "/api/report":
                self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json()
                report = self._build_report(payload)
            except Exception as exc:
                self._json(error_payload(exc), HTTPStatus.BAD_REQUEST)
                return
            self._json(report)

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            return json.loads(body or "{}")

        def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _send(self, status: HTTPStatus, body: str | bytes, content_type: str) -> None:
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _stream_report(self) -> None:
            try:
                payload = self._read_json()
            except Exception as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            def emit(message: dict[str, Any]) -> None:
                data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
                self.wfile.write(data)
                self.wfile.flush()

            try:
                report = self._build_report(
                    payload,
                    progress_callback=lambda event: emit({"type": "trace", "event": event}),
                )
                emit({"type": "report", "report": report})
            except Exception as exc:
                emit({"type": "error", **error_payload(exc)})

        def _build_report(
            self,
            payload: dict[str, Any],
            progress_callback=None,
        ) -> dict[str, Any]:
            return build_verification_report(
                memo=_statement_from_payload(payload),
                tickers=_tickers_from_payload(payload),
                config=config,
                as_of_date=payload.get("as_of_date") or None,
                max_sources=int(payload.get("max_sources") or 8),
                mode=str(payload.get("mode") or "agentic"),
                prefetched_results=payload.get("prefetched_results") or None,
                progress_callback=progress_callback,
                tool_profile=str(payload.get("tool_profile") or "agent_core"),
                agent_max_steps=int(payload.get("agent_max_steps") or 12),
                audit=bool(payload.get("audit", True)),
            )

    return CredenceHandler


def _tickers_from_payload(payload: dict[str, Any]) -> list[str]:
    tickers = payload.get("tickers", "")
    if isinstance(tickers, list):
        return [str(ticker) for ticker in tickers]
    return [part.strip() for part in str(tickers).split(",") if part.strip()]


def _statement_from_payload(payload: dict[str, Any]) -> str:
    if "statement" in payload:
        return str(payload.get("statement") or "")
    return str(payload.get("memo", ""))


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Credence Analytics Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef3f3;
      --panel: #fbfcfd;
      --panel-cool: #f5f8f8;
      --terminal: #111b20;
      --terminal-2: #17262c;
      --ink: #11181d;
      --muted: #66737c;
      --line: #cbd5da;
      --line-strong: #aebec6;
      --teal: #0f766e;
      --cyan: #247f93;
      --teal-soft: #d9ece9;
      --amber: #a26a16;
      --red: #a63b43;
      --green: #227146;
      --shadow: 0 14px 34px rgba(17, 27, 32, 0.10);
      --shadow-tight: 0 5px 16px rgba(17, 27, 32, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(180deg, rgba(238, 243, 243, 0.94), rgba(247, 249, 249, 0.96) 42%, rgba(235, 240, 239, 0.98)),
        repeating-linear-gradient(0deg, rgba(18, 57, 63, 0.045) 0 1px, transparent 1px 42px),
        repeating-linear-gradient(90deg, rgba(18, 57, 63, 0.04) 0 1px, transparent 1px 42px),
        var(--bg);
      font-variant-numeric: tabular-nums;
    }
    .shell {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .topbar {
      height: 60px;
      border-bottom: 1px solid rgba(202, 218, 224, 0.22);
      background: rgba(17, 27, 32, 0.94);
      color: #edf4f3;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 0 22px;
      position: sticky;
      top: 0;
      z-index: 2;
      box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06), 0 12px 34px rgba(16, 27, 33, 0.16);
      backdrop-filter: blur(14px);
    }
    .topbar::after {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: -1px;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(39, 151, 141, 0.72), rgba(36, 127, 147, 0.55), transparent);
    }
    .chat {
      flex: 1;
      overflow: auto;
      padding: 26px 18px 150px;
    }
    .messages {
      width: min(1120px, 100%);
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }
    .brand {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 20px; font-weight: 760; }
    .brand h1 {
      display: inline-flex;
      align-items: center;
      gap: 11px;
    }
    .brand h1::before {
      content: "";
      width: 11px;
      height: 11px;
      border: 1px solid rgba(86, 206, 190, 0.82);
      background: linear-gradient(135deg, rgba(86, 206, 190, 0.85), rgba(17, 27, 32, 0));
      box-shadow: 0 0 0 4px rgba(86, 206, 190, 0.10);
      transform: rotate(45deg);
      flex: 0 0 auto;
    }
    h2 { font-size: 18px; }
    h3 { font-size: 15px; }
    .subtle { color: var(--muted); font-size: 13px; }
    label {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    textarea, input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfc;
      color: var(--ink);
      font: inherit;
      font-size: 14px;
      padding: 10px 11px;
      outline: none;
    }
    textarea { min-height: 120px; resize: vertical; line-height: 1.45; }
    input:focus, textarea:focus, select:focus { border-color: var(--teal); box-shadow: 0 0 0 3px var(--teal-soft); }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .actions { display: flex; gap: 10px; align-items: center; }
    button {
      border: 0;
      border-radius: 8px;
      background: var(--terminal);
      color: #fff;
      font: inherit;
      font-weight: 700;
      padding: 10px 14px;
      cursor: pointer;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.10), 0 7px 18px rgba(17, 27, 32, 0.14);
    }
    button:hover { background: #1a2a31; }
    button.secondary { background: #eef1f2; color: var(--ink); }
    button:disabled { opacity: 0.55; cursor: wait; }
    .status {
      font-size: 13px;
      color: var(--muted);
      min-height: 20px;
    }
    .sr-status {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .composer-wrap {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      padding: 18px;
      background: linear-gradient(180deg, rgba(238, 243, 243, 0), rgba(238, 243, 243, 0.95) 24%, var(--bg));
    }
    .composer {
      width: min(920px, 100%);
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
      background: rgba(251, 252, 253, 0.94);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 10px;
      backdrop-filter: blur(12px);
    }
    .composer textarea {
      min-height: 52px;
      max-height: 190px;
      resize: none;
      border: 0;
      padding: 7px 8px;
      background: transparent;
    }
    .composer textarea:focus { box-shadow: none; }
    .send-button {
      min-width: 82px;
      height: 42px;
      align-self: end;
    }
    .composer-wrap .status {
      width: min(920px, 100%);
      margin: 8px auto 0;
      padding-left: 3px;
    }
    .message {
      display: grid;
      gap: 10px;
    }
    .message-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
      text-transform: uppercase;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .message.user {
      justify-items: end;
    }
    .user-query {
      width: min(760px, 92%);
      justify-self: end;
      background: #e4efed;
      border: 1px solid #b9d6d1;
      border-radius: 8px;
      box-shadow: var(--shadow-tight);
      overflow: hidden;
    }
    .user-query summary {
      cursor: pointer;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      padding: 11px 13px;
      list-style: none;
    }
    .user-query summary::-webkit-details-marker { display: none; }
    .user-query summary::after {
      content: "Expand";
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
      text-transform: uppercase;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .user-query[open] summary {
      border-bottom: 1px solid #b9d6d1;
    }
    .user-query[open] summary::after { content: "Collapse"; }
    .user-query-title {
      min-width: 0;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      font-weight: 650;
      line-height: 1.35;
    }
    .user-bubble {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      padding: 12px 14px;
      line-height: 1.45;
    }
    .assistant-card {
      display: grid;
      gap: 14px;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric, .section, .entity {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .metric {
      position: relative;
      padding: 14px;
      background: linear-gradient(180deg, #ffffff, var(--panel-cool));
      overflow: hidden;
    }
    .metric::before {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      top: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--teal), var(--cyan));
    }
    .metric .value {
      font-size: 24px;
      font-weight: 780;
      margin-top: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .section { padding: 16px; margin-bottom: 16px; }
    .entity { margin-bottom: 18px; overflow: hidden; }
    .entity-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 15px 16px;
      border-bottom: 1px solid rgba(202, 218, 224, 0.28);
      background: linear-gradient(135deg, var(--terminal), var(--terminal-2));
      color: #eef5f4;
    }
    .entity-head .subtle { color: #aebfc5; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 720;
      background: #edf1f2;
      color: var(--ink);
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .pill.good { background: #dff0e6; color: var(--green); }
    .pill.warn { background: #fff0d8; color: var(--amber); }
    .pill.bad { background: #f7dddd; color: var(--red); }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      vertical-align: top;
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
    }
    th { color: var(--muted); font-size: 12px; background: var(--panel-cool); }
    .claim-text { max-width: 460px; line-height: 1.35; }
    .bar {
      height: 8px;
      width: 92px;
      background: #e4e8eb;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 5px;
    }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--teal), var(--cyan)); }
    .evidence {
      padding: 14px 16px 16px;
      display: grid;
      gap: 8px;
    }
    .entity-list {
      padding: 12px 0 0;
    }
    .asset-group {
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfc;
      overflow: hidden;
    }
    .asset-group:first-child { margin-top: 0; }
    .asset-group summary.asset-group-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 11px 12px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      cursor: pointer;
      list-style: none;
      background: linear-gradient(180deg, #ffffff, var(--panel-cool));
    }
    .asset-group summary.asset-group-title::-webkit-details-marker { display: none; }
    .asset-group summary.asset-group-title::after {
      content: "Expand";
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
      margin-left: auto;
    }
    .asset-group[open] summary.asset-group-title {
      border-bottom: 1px solid var(--line);
    }
    .asset-group[open] summary.asset-group-title::after { content: "Collapse"; }
    .asset-group-count { margin-left: auto; padding-right: 10px; white-space: nowrap; }
    .asset-group-items {
      display: grid;
      gap: 8px;
      padding: 10px;
    }
    .evidence-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfc;
      font-size: 13px;
    }
    .claim-list {
      display: grid;
      gap: 12px;
      padding: 14px 16px 16px;
    }
    .claim-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      overflow: hidden;
      box-shadow: var(--shadow-tight);
    }
    .claim-card.needs-review {
      border-color: #e3bd74;
      box-shadow: inset 3px 0 0 var(--amber);
    }
    .claim-card-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      padding: 13px 14px;
      background: linear-gradient(180deg, #fbfcfd, #f3f6f6);
      border-bottom: 1px solid var(--line);
    }
    .claim-card-title {
      display: grid;
      gap: 4px;
      min-width: 0;
    }
    .claim-card-title strong {
      line-height: 1.35;
    }
    .claim-status {
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: flex-end;
      flex-shrink: 0;
    }
    .review-badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 720;
      background: #fff0d8;
      color: var(--amber);
      white-space: nowrap;
    }
    .claim-grid {
      display: grid;
      grid-template-columns: minmax(210px, 0.8fr) minmax(0, 1.2fr) minmax(0, 1.05fr);
      gap: 12px;
      padding: 14px;
    }
    .claim-field {
      display: grid;
      gap: 6px;
      align-content: start;
      min-width: 0;
    }
    .claim-field-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
    }
    .source-box, .quote-box, .match-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-cool);
      padding: 10px;
      font-size: 13px;
      line-height: 1.45;
      min-height: 82px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
    }
    .quote-box {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .source-title {
      font-weight: 720;
      margin-bottom: 3px;
    }
    .source-link {
      color: var(--teal);
      text-decoration: none;
      font-weight: 650;
      overflow-wrap: anywhere;
    }
    .source-link:hover { text-decoration: underline; }
    .claim-foot {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      align-items: center;
      padding: 0 14px 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .mini-meter {
      display: inline-flex;
      align-items: center;
      gap: 7px;
    }
    .trace-panel {
      border-top: 1px solid var(--line);
      padding: 14px 16px 16px;
      background: #fff;
    }
    details.trace-panel {
      padding: 0;
    }
    details.trace-panel > summary {
      list-style: none;
      cursor: pointer;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }
    details.trace-panel > summary::-webkit-details-marker { display: none; }
    details.trace-panel > summary::after {
      content: "Collapse";
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    details.trace-panel:not([open]) > summary {
      border-bottom: 0;
    }
    details.trace-panel:not([open]) > summary::after {
      content: "Expand";
    }
    .trace-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 0;
    }
    .trace-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(240px, 0.65fr);
      gap: 12px;
      padding: 14px 16px 16px;
    }
    .trace-list {
      display: grid;
      gap: 8px;
    }
    .trace-step {
      border-left: 3px solid var(--teal);
      border-radius: 6px;
      background: var(--panel-cool);
      padding: 9px 10px;
      font-size: 13px;
    }
    .trace-step.warn { border-left-color: var(--amber); }
    .trace-step.bad { border-left-color: var(--red); }
    .trace-step-top {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 4px;
    }
    .trace-meta {
      width: 100%;
      max-height: 190px;
      overflow: auto;
      margin: 8px 0 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f5f8f8;
      padding: 9px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.4;
    }
    details.trace-details summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      margin-top: 5px;
    }
    .live-trace {
      background: var(--panel);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .live-trace > summary.trace-head {
      display: grid;
      grid-template-columns: minmax(140px, 1fr) auto minmax(68px, 1fr);
      align-items: center;
      background: linear-gradient(135deg, var(--terminal), var(--terminal-2));
      color: #edf4f3;
      border-bottom: 1px solid rgba(202, 218, 224, 0.22);
    }
    .live-trace > summary.trace-head::after {
      justify-self: end;
      color: #aebfc5;
    }
    .live-progress {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      justify-content: center;
      min-width: min(360px, 42vw);
      color: #dcefed;
      font-size: 13px;
      font-weight: 650;
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .live-progress.done .pulse-dot,
    .live-progress.error .pulse-dot {
      animation: none;
    }
    .pulse-dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: #56cebe;
      box-shadow: 0 0 0 0 rgba(34, 128, 111, 0.35);
      animation: pulse 1.25s ease-out infinite;
      flex: 0 0 auto;
    }
    .activity-bar {
      position: relative;
      width: 68px;
      height: 6px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(220, 239, 237, 0.20);
      flex: 0 0 auto;
    }
    .activity-bar::after {
      content: "";
      position: absolute;
      inset: 0;
      width: 38%;
      border-radius: inherit;
      background: #56cebe;
      animation: scan 1.05s ease-in-out infinite;
    }
    .live-progress.done .activity-bar::after,
    .live-progress.error .activity-bar::after {
      animation: none;
      width: 100%;
    }
    .live-progress.error .pulse-dot,
    .live-progress.error .activity-bar::after {
      background: var(--red);
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(34, 128, 111, 0.34); }
      70% { box-shadow: 0 0 0 9px rgba(34, 128, 111, 0); }
      100% { box-shadow: 0 0 0 0 rgba(34, 128, 111, 0); }
    }
    @keyframes scan {
      0% { transform: translateX(-110%); }
      50% { transform: translateX(82%); }
      100% { transform: translateX(230%); }
    }
    .live-trace .trace-panel {
      border-top: 0;
    }
    .report-text {
      width: 100%;
      min-height: 320px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    .markdown-report {
      display: grid;
      gap: 12px;
    }
    .markdown-body {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      background: #ffffff;
      line-height: 1.55;
      overflow: auto;
    }
    .markdown-body h1 {
      font-size: 22px;
      margin: 0 0 14px;
    }
    .markdown-body h2 {
      font-size: 18px;
      margin: 18px 0 9px;
      padding-top: 8px;
      border-top: 1px solid var(--line);
    }
    .markdown-body h2:first-child { margin-top: 0; padding-top: 0; border-top: 0; }
    .markdown-body h3 {
      font-size: 15px;
      margin: 16px 0 8px;
    }
    .markdown-body p {
      margin: 8px 0;
    }
    .markdown-body ul {
      margin: 8px 0 12px;
      padding-left: 21px;
    }
    .markdown-body li {
      margin: 4px 0;
    }
    .markdown-body code {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-cool);
      padding: 1px 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }
    .markdown-body pre {
      margin: 10px 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-cool);
      padding: 10px;
      overflow: auto;
    }
    .markdown-body pre code {
      border: 0;
      background: transparent;
      padding: 0;
    }
    .markdown-body a {
      color: var(--teal);
      text-decoration: none;
      font-weight: 650;
    }
    .markdown-body a:hover { text-decoration: underline; }
    .markdown-table-wrap {
      width: 100%;
      overflow: auto;
      margin: 10px 0 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .markdown-body .markdown-table-wrap table {
      min-width: 760px;
      border: 0;
    }
    details.raw-markdown summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }
    .empty {
      border: 1px dashed #c7ced3;
      border-radius: 8px;
      padding: 40px 20px;
      text-align: center;
      color: var(--muted);
      background: rgba(251, 252, 253, 0.82);
      box-shadow: var(--shadow-tight);
    }
    .error { color: var(--red); font-weight: 650; }
    @media (max-width: 900px) {
      .chat { padding: 18px 12px 150px; }
      .summary { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .row { grid-template-columns: 1fr; }
      .trace-grid { grid-template-columns: 1fr; }
      .claim-grid { grid-template-columns: 1fr; }
      .live-trace > summary.trace-head {
        grid-template-columns: 1fr auto;
        gap: 8px;
      }
      .live-progress {
        grid-column: 1 / -1;
        grid-row: 2;
        justify-content: flex-start;
        min-width: 0;
        white-space: normal;
      }
      .composer-wrap { padding: 12px; }
      .composer { grid-template-columns: minmax(0, 1fr); }
      .send-button { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <h1>Credence Analytics Agent</h1>
      </div>
    </header>
    <span id="status" class="sr-status" aria-live="polite"></span>
    <main class="chat">
      <div id="report" class="messages">
        <div class="message assistant">
          <div class="empty">Credence report output will appear here.</div>
        </div>
      </div>
    </main>
    <form id="form" class="composer-wrap">
      <div class="composer">
        <label for="statement">Statement</label>
        <textarea id="statement" name="statement" rows="1" placeholder="Paste an investment note or financial statement for verification."></textarea>
        <button id="run" class="send-button" type="submit">Run</button>
      </div>
    </form>
  </div>
  <script>
    const form = document.getElementById("form");
    const runButton = document.getElementById("run");
    const statusEl = document.getElementById("status");
    const reportEl = document.getElementById("report");
    const statementEl = document.getElementById("statement");
    let liveTraceEvents = [];
    let liveTraceOpenDetails = new Set();

    statementEl.addEventListener("input", resizeComposer);
    statementEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
    resizeComposer();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const statement = statementEl.value.trim();
      if (!statement) {
        statusEl.textContent = "Empty input";
        statementEl.focus();
        return;
      }
      runButton.disabled = true;
      statementEl.disabled = true;
      statusEl.textContent = "Running";
      liveTraceEvents = [];
      liveTraceOpenDetails = new Set();
      reportEl.innerHTML = renderUserMessage(statement, true) + renderLiveTraceShell();
      const payload = {
        statement,
        mode: "multi_tool",
        tool_profile: "agent_core",
        agent_max_steps: 12,
        audit: true
      };
      try {
        const data = await runStreamingReport(payload);
        renderReport(data, statement);
        statusEl.textContent = "Ready";
      } catch (error) {
        reportEl.innerHTML = renderUserMessage(statement, true) + `<div class="message assistant"><div class="section error">${escapeHtml(error.message)}</div></div>`;
        statusEl.textContent = "Error";
      } finally {
        runButton.disabled = false;
        statementEl.disabled = false;
        statementEl.focus();
      }
    });

    async function runStreamingReport(payload) {
      const response = await fetch("/api/report/stream", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(formatError(data.error || "Request failed"));
      }
      if (!response.body) {
        const fallback = await fetch("/api/report", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await fallback.json();
        if (!fallback.ok) throw new Error(formatError(data.error || "Request failed"));
        return data;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalReport = null;
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const message = JSON.parse(line);
          if (message.type === "trace") {
            appendLiveTrace(message.event || {});
          } else if (message.type === "report") {
            finalReport = message.report;
          } else if (message.type === "error") {
            throw new Error(formatError(message.error || "Streaming report failed"));
          }
        }
      }
      if (buffer.trim()) {
        const message = JSON.parse(buffer);
        if (message.type === "report") finalReport = message.report;
        if (message.type === "error") throw new Error(formatError(message.error || "Streaming report failed"));
      }
      if (!finalReport) throw new Error("Report stream ended before a final report was returned.");
      return finalReport;
    }

    function formatError(error) {
      if (!error || typeof error === "string") return error || "Request failed";
      const message = error.message || "Request failed";
      const hint = error.hint ? ` Hint: ${error.hint}` : "";
      const code = error.code ? ` (${error.code})` : "";
      return `${message}${code}${hint}`;
    }

    function resizeComposer() {
      statementEl.style.height = "auto";
      statementEl.style.height = `${Math.min(statementEl.scrollHeight, 190)}px`;
    }

    function renderUserMessage(statement, open = false) {
      const preview = compactPreview(statement);
      return `
        <article class="message user">
          <div class="message-label">Question</div>
          <details class="user-query"${open ? " open" : ""}>
            <summary>
              <span class="user-query-title">${escapeHtml(preview)}</span>
            </summary>
            <div class="user-bubble">${escapeHtml(statement)}</div>
          </details>
        </article>
      `;
    }

    function compactPreview(value) {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      if (!text) return "Submitted question";
      return text.length > 120 ? `${text.slice(0, 117)}...` : text;
    }

    function renderLiveTraceShell() {
      return `
        <article class="message assistant" id="liveTraceMessage">
          <div class="message-label">Running</div>
          <details class="trace-panel live-trace">
            <summary class="trace-head">
              <h3>Trace</h3>
              <span class="live-progress" id="liveTraceProgress">
                <span class="pulse-dot" aria-hidden="true"></span>
                <span id="liveTraceStatus">Starting verification</span>
                <span class="activity-bar" aria-hidden="true"></span>
              </span>
            </summary>
            <div class="trace-grid">
              <div class="trace-list" id="liveTraceList">
                <div class="trace-step">
                  <div class="trace-step-top">
                    <strong>Starting</strong>
                    <span class="subtle">pending</span>
                  </div>
                  <div>Preparing the verification workflow.</div>
                </div>
              </div>
              <div>
                <h3>Stream</h3>
                <pre class="trace-meta" id="liveTraceRaw">[]</pre>
              </div>
            </div>
          </details>
        </article>
      `;
    }

    function appendLiveTrace(event) {
      liveTraceEvents.push(event);
      const list = document.getElementById("liveTraceList");
      const raw = document.getElementById("liveTraceRaw");
      const status = document.getElementById("liveTraceStatus");
      const progress = document.getElementById("liveTraceProgress");
      if (list) {
        rememberLiveTraceDetailState(list);
        list.innerHTML = liveTraceEvents.map((traceEvent, index) => renderTraceEvent(traceEvent, index, true)).join("");
        restoreLiveTraceDetailState(list);
      }
      if (raw) {
        raw.textContent = JSON.stringify(liveTraceEvents, null, 2);
      }
      if (status) {
        const last = liveTraceEvents[liveTraceEvents.length - 1] || {};
        const label = last.step ? `${formatStepName(last.step)} - ${last.status || "running"}` : "Running verification";
        status.textContent = `${label} (${liveTraceEvents.length} event${liveTraceEvents.length === 1 ? "" : "s"})`;
      }
      if (progress) progress.classList.remove("done", "error");
      const last = liveTraceEvents[liveTraceEvents.length - 1] || {};
      statusEl.textContent = last.step ? `${last.step}: ${last.status || "running"}` : "Running";
    }

    function setLiveTraceFinished(state, label) {
      const progress = document.getElementById("liveTraceProgress");
      const status = document.getElementById("liveTraceStatus");
      if (progress) {
        progress.classList.remove("done", "error");
        progress.classList.add(state);
      }
      if (status) status.textContent = label;
    }

    function formatStepName(step) {
      return String(step || "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, char => char.toUpperCase());
    }

    function renderReport(data, statement) {
      const summary = data.summary || {};
      const metrics = [
        ["Detected Entities", summary.detected_entity_count ?? summary.entity_count ?? 0],
        ["Asset Classes", summary.asset_class_count ?? 0],
        ["Fact Checks", summary.atomic_claim_count ?? 0],
        ["Not Fact-Checked", summary.skipped_claim_count ?? 0],
        ["Needs Review", summary.human_review_count ?? 0],
        ["Verification Confidence", fmtConfidence(summary.average_confidence)]
      ];
      const runs = (data.runs || []).map(renderEntity).join("");
      const errors = (data.errors || []).map(err => `<div class="section error">${escapeHtml(err.ticker)}: ${escapeHtml(err.error)}</div>`).join("");
      const extraction = renderEntityExtraction((data.input || {}).entity_extraction || {});
      const markdown = data.report_markdown || "";
      reportEl.innerHTML = `
        ${renderUserMessage(statement, false)}
        <article class="message assistant">
          <div class="message-label">Verification Report</div>
          <div class="assistant-card">
            <div class="summary">
              ${metrics.map(([label, value]) => `<div class="metric"><div class="subtle">${label}</div><div class="value">${escapeHtml(value)}</div></div>`).join("")}
            </div>
            ${extraction}
            ${errors}
            ${runs || '<div class="empty">No report rows.</div>'}
            <div class="section markdown-report">
              <h2>Rendered Report</h2>
              <div class="markdown-body">${renderMarkdown(markdown)}</div>
              <details class="raw-markdown">
                <summary>Raw Markdown</summary>
                <textarea class="report-text" readonly>${escapeHtml(markdown)}</textarea>
              </details>
            </div>
          </div>
        </article>
      `;
    }

    function renderMarkdown(markdown) {
      const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
      const html = [];
      let inList = false;
      let inCode = false;
      let codeLines = [];

      const closeList = () => {
        if (inList) {
          html.push("</ul>");
          inList = false;
        }
      };
      const closeCode = () => {
        if (inCode) {
          html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
          codeLines = [];
          inCode = false;
        }
      };

      for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        const trimmed = line.trim();

        if (trimmed.startsWith("```")) {
          if (inCode) closeCode();
          else {
            closeList();
            inCode = true;
            codeLines = [];
          }
          continue;
        }
        if (inCode) {
          codeLines.push(line);
          continue;
        }
        if (!trimmed) {
          closeList();
          continue;
        }

        const heading = line.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
          closeList();
          const level = Math.min(6, heading[1].length);
          html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
          continue;
        }

        if (line.includes("|") && index + 1 < lines.length && isMarkdownTableSeparator(lines[index + 1])) {
          closeList();
          const headers = splitMarkdownTableRow(line);
          const rows = [];
          index += 2;
          while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
            rows.push(splitMarkdownTableRow(lines[index]));
            index += 1;
          }
          index -= 1;
          html.push(
            `<div class="markdown-table-wrap"><table><thead><tr>${headers.map(cell => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
          );
          continue;
        }

        const bullet = line.match(/^\s*-\s+(.+)$/);
        if (bullet) {
          if (!inList) {
            html.push("<ul>");
            inList = true;
          }
          html.push(`<li>${renderInlineMarkdown(bullet[1])}</li>`);
          continue;
        }

        closeList();
        html.push(`<p>${renderInlineMarkdown(line)}</p>`);
      }

      closeList();
      closeCode();
      return html.join("");
    }

    function isMarkdownTableSeparator(line) {
      return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
    }

    function splitMarkdownTableRow(line) {
      return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
    }

    function renderInlineMarkdown(value) {
      let html = escapeHtml(value);
      html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_match, label, url) => {
        const safeUrl = escapeHtml(url);
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      });
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      return html;
    }

    function renderEntityExtraction(extraction) {
      const entities = extraction.entities || [];
      if (!entities.length) return "";
      const groups = extraction.asset_groups || groupEntitiesByAssetClass(entities);
      const groupHtml = Object.entries(groups)
        .filter(([_assetClass, items]) => (items || []).length)
        .map(([assetClass, items]) => `
          <details class="asset-group">
            <summary class="asset-group-title">
              <span>${escapeHtml(assetClassLabel(assetClass))}</span>
              <span class="asset-group-count">${escapeHtml(items.length)} item${items.length === 1 ? "" : "s"}</span>
            </summary>
            <div class="asset-group-items">
              ${(items || []).map(renderDetectedEntity).join("")}
            </div>
          </details>
        `).join("");
      return `
        <div class="section">
          <h2>Detected Asset Classes</h2>
          <div class="evidence entity-list">
            ${groupHtml}
          </div>
        </div>
      `;
    }

    function renderDetectedEntity(entity) {
      const ticker = entity.ticker || "";
      const symbol = entity.symbol || "";
      const name = entity.name || "";
      const primary = ticker || symbol || name;
      const displayName = name && name !== primary ? `<div>${escapeHtml(name)}</div>` : "";
      const type = entity.entity_type ? `<div class="subtle">${escapeHtml(entityTypeLabel(entity.entity_type))}</div>` : "";
      return `
        <div class="evidence-item">
          <strong>${escapeHtml(primary)}</strong>
          ${displayName}
          ${type}
        </div>
      `;
    }

    function groupEntitiesByAssetClass(entities) {
      return (entities || []).reduce((groups, entity) => {
        const key = entity.asset_class || "other";
        if (!groups[key]) groups[key] = [];
        groups[key].push(entity);
        return groups;
      }, {});
    }

    function assetClassLabel(assetClass) {
      const labels = {
        single_name_equity: "Single-name equities",
        equity_index: "Equity indexes",
        equity_index_future: "Equity index futures",
        fund_etf: "Funds and ETFs",
        commodity: "Commodities",
        commodity_future: "Commodity futures",
        fx: "FX",
        rates: "Rates",
        credit: "Credit",
        macro_indicator: "Macro indicators",
        crypto: "Crypto",
        fixed_income: "Fixed income",
        volatility_index: "Volatility indexes",
        other: "Other"
      };
      return labels[assetClass] || String(assetClass || "Other").replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase());
    }

    function entityTypeLabel(entityType) {
      return String(entityType || "").replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase());
    }

    function renderEntity(run) {
      const conclusion = run.overall_conclusion || {};
      const entity = run.entity_resolution || {};
      const audit = run.audit_trace || {};
      const selections = ((run.metadata || {}).source_selection || []).map(renderSourceSelection).join("");
      const checkedResults = (run.atomic_claims || []).filter(isFactCheckedResult);
      const skippedResults = (run.atomic_claims || []).filter(result => !isFactCheckedResult(result));
      const claims = checkedResults.map(result => renderClaimCard(result, run)).join("");
      const skippedClaims = renderSkippedClaims(skippedResults);
      const trace = renderAgentTrace(audit);
      const evidence = (run.evidence || []).slice(0, 8).map(item => `
        <div class="evidence-item">
          <strong>${escapeHtml(item.source_tier || "")}</strong>
          ${escapeHtml(item.title || "")}
          <div class="subtle">${escapeHtml(item.domain || "")} - ${escapeHtml(item.published_at || "undated")}</div>
        </div>
      `).join("");
      return `
        <section class="entity">
          <div class="entity-head">
            <div>
              <h2>${escapeHtml(run.ticker || "")}</h2>
            </div>
            <span class="pill ${pillClass(conclusion.overall_label)}">${escapeHtml(conclusion.overall_label || "n/a")}</span>
          </div>
          ${selections ? `<details class="trace-panel"><summary class="trace-head"><h3>Selected Sources</h3><span class="subtle">Evidence sources</span></summary><div class="evidence">${selections}</div></details>` : ""}
          <div class="claim-list">
            <h3>Claim Checks</h3>
            ${claims || '<div class="subtle">No fact-checkable claims found.</div>'}
          </div>
          ${skippedClaims}
          <details class="trace-panel">
            <summary class="trace-head"><h3>Sources Used For This Entity</h3><span class="subtle">Sources used</span></summary>
            <div class="evidence">${evidence || '<div class="subtle">No sources.</div>'}</div>
          </details>
          ${trace}
        </section>
      `;
    }

    function isFactCheckedResult(result) {
      const type = (result.atomic_claim || {}).argument_type;
      return result.verdict !== "not_applicable" && !["forecast", "opinion_analysis"].includes(type);
    }

    function renderSkippedClaims(results) {
      if (!results.length) return "";
      return `
        <details class="trace-panel">
          <summary class="trace-head"><h3>Not Fact-Checked</h3><span class="subtle">Opinions and forecasts</span></summary>
          <div class="evidence">
            ${results.map(result => {
              const claim = result.atomic_claim || {};
              return `
                <div class="evidence-item">
                  <strong>${escapeHtml(claim.argument_type || "not_applicable")}</strong>
                  <div>${escapeHtml(claim.text || "")}</div>
                  <div class="subtle">Skipped because this is not a historical factual claim.</div>
                </div>
              `;
            }).join("")}
          </div>
        </details>
      `;
    }

    function renderAgentTrace(audit) {
      const events = audit.events || [];
      const replay = audit.replayable_inputs || {};
      const sourceNotes = audit.source_notes || [];
      if (!events.length && !Object.keys(replay).length && !sourceNotes.length) return "";
      return `
        <details class="trace-panel">
          <summary class="trace-head">
            <h3>Agent Trace</h3>
            <span class="subtle">${escapeHtml(audit.trace_id || "trace unavailable")}</span>
          </summary>
          <div class="trace-grid">
            <div class="trace-list">
              ${events.map(renderTraceEvent).join("") || '<div class="subtle">No trace events.</div>'}
            </div>
            <div>
              <h3>Replay</h3>
              <pre class="trace-meta">${escapeHtml(JSON.stringify(replay, null, 2))}</pre>
              ${sourceNotes.length ? `<div class="subtle">${escapeHtml(sourceNotes.join(", "))}</div>` : ""}
            </div>
          </div>
        </details>
      `;
    }

    function rememberLiveTraceDetailState(list) {
      list.querySelectorAll("details.trace-details[data-detail-key]").forEach(detail => {
        const key = detail.getAttribute("data-detail-key");
        if (!key) return;
        if (detail.open) liveTraceOpenDetails.add(key);
        else liveTraceOpenDetails.delete(key);
      });
    }

    function restoreLiveTraceDetailState(list) {
      list.querySelectorAll("details.trace-details[data-detail-key]").forEach(detail => {
        const key = detail.getAttribute("data-detail-key");
        if (key && liveTraceOpenDetails.has(key)) detail.open = true;
      });
    }

    function renderTraceEvent(event, index, preserveOpen = false) {
      const status = String(event.status || "").toLowerCase();
      const statusClass = status.includes("review") || status.includes("warn") ? "warn" : (status.includes("fail") || status.includes("error") ? "bad" : "");
      const outputs = event.outputs && Object.keys(event.outputs).length ? JSON.stringify(event.outputs, null, 2) : "";
      const detailKey = `event-${index}-${event.step || "step"}`;
      const detailOpen = preserveOpen && liveTraceOpenDetails.has(detailKey) ? " open" : "";
      return `
        <div class="trace-step ${statusClass}">
          <div class="trace-step-top">
            <strong>${escapeHtml(index + 1)}. ${escapeHtml(event.step || "step")}</strong>
            <span class="subtle">${escapeHtml(event.status || "n/a")}</span>
          </div>
          <div>${escapeHtml(event.summary || "")}</div>
          ${outputs ? `<details class="trace-details" data-detail-key="${escapeHtml(detailKey)}"${detailOpen}><summary>Outputs</summary><pre class="trace-meta">${escapeHtml(outputs)}</pre></details>` : ""}
        </div>
      `;
    }

    function renderSourceSelection(selection) {
      const sources = (selection.selected_sources || []).join(", ") || "n/a";
      return `
        <div class="evidence-item">
          <strong>${escapeHtml(selection.claim_id || "claim")}</strong>
          <div>${escapeHtml(sources)}</div>
          ${selection.rationale ? `<div class="subtle">${escapeHtml(selection.rationale)}</div>` : ""}
        </div>
      `;
    }

    function renderClaimCard(result, run) {
      const claim = result.atomic_claim || {};
      const components = result.confidence_components || {};
      const confidence = Number(components.final_confidence || 0);
      const source = bestSourceForClaim(result, run.evidence || []);
      const facts = factsForClaim(result, run.canonical_facts || []);
      const match = consistencySummary(result);
      const review = humanReviewSummary(result);
      const needsReview = Boolean(result.human_review_required || (result.review_reasons || []).length);
      return `
        <article class="claim-card ${needsReview ? "needs-review" : ""}">
          <div class="claim-card-head">
            <div class="claim-card-title">
              <span class="subtle">${escapeHtml(claim.claim_id || "claim")}</span>
              <strong>${escapeHtml(claim.text || "")}</strong>
            </div>
            <div class="claim-status">
              <span class="pill ${pillClass(result.verdict)}">${escapeHtml(verdictLabel(result.verdict))}</span>
              ${needsReview ? '<span class="review-badge">Human Review</span>' : ""}
            </div>
          </div>
          <div class="claim-grid">
            <div class="claim-field">
              <div class="claim-field-label">Data Source Checked</div>
              <div class="source-box">${renderSourceBox(source)}</div>
            </div>
            <div class="claim-field">
              <div class="claim-field-label">What The Source Says</div>
              <div class="quote-box">${renderSourceSays(source, facts)}</div>
            </div>
            <div class="claim-field">
              <div class="claim-field-label">Does It Match The Claim?</div>
              <div class="match-box">${match}</div>
            </div>
          </div>
          <div class="claim-foot">
            <span class="mini-meter">Verification confidence ${fmtConfidence(confidence)} <span class="bar"><span style="width:${Math.max(0, Math.min(100, confidence * 100))}%"></span></span></span>
            <span>${review}</span>
          </div>
        </article>
      `;
    }

    function bestSourceForClaim(result, evidence) {
      const keys = new Set(result.evidence_keys || []);
      const urls = new Set(result.evidence_urls || []);
      if (!keys.size && !urls.size) return null;
      return evidence.find(item => keys.has(evidenceKey(item))) || evidence.find(item => urls.has(item.url)) || null;
    }

    function factsForClaim(result, facts) {
      const ids = new Set(result.canonical_fact_ids || []);
      return facts.filter(fact => ids.has(fact.fact_id)).filter(isDisplayableFact).slice(0, 4);
    }

    function isDisplayableFact(fact) {
      const name = String(fact.fact_name || "");
      if (!name) return false;
      if (/^SEC Company Facts\b/i.test(name)) return false;
      if ((fact.unit || fact.currency || "").toString().toUpperCase() === "") {
        const numeric = Number(fact.value);
        if (Number.isFinite(numeric) && numeric >= 1900 && numeric <= 2200) return false;
      }
      return fact.value !== null && fact.value !== undefined && fact.value !== "";
    }

    function evidenceKey(item) {
      return `${item.source_tier || ""}:${item.domain || ""}:${item.published_at || "undated"}`;
    }

    function renderSourceBox(source) {
      if (!source) return '<span class="subtle">No displayable source was found.</span>';
      const title = source.title || source.domain || source.url || "Source";
      const tier = source.source_tier || "n/a";
      const date = source.published_at || "undated";
      const domain = source.domain || "";
      const url = source.url || "";
      return `
        <div class="source-title">${escapeHtml(tier)} - ${escapeHtml(title)}</div>
        <div class="subtle">${escapeHtml(domain)} - ${escapeHtml(date)}</div>
        ${url ? `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open source</a>` : ""}
      `;
    }

    function renderSourceSays(source, facts) {
      const factLines = (facts || []).map(fact => {
        const value = formatFactValue(fact.value, fact.unit || fact.currency);
        const period = humanFactPeriod(fact.report_period || fact.observation_date);
        return `${humanFactName(fact.fact_name || "Fact")}: ${value}${period ? " for " + period : ""}`;
      });
      const sourceLines = source && source.text ? humanSourceLines(source.text) : [];
      const parts = [];
      if (factLines.length) {
        parts.push(`<div><strong>Structured values</strong><br>${factLines.map(escapeHtml).join("<br>")}</div>`);
      }
      if (sourceLines.length && !factLines.length) {
        parts.push(`<div><strong>Source excerpt</strong><br>${sourceLines.map(escapeHtml).join("<br>")}</div>`);
      } else if (sourceLines.length) {
        parts.push(
          `<details class="raw-markdown"><summary>More source values</summary><div>${sourceLines.slice(0, 4).map(escapeHtml).join("<br>")}</div></details>`
        );
      }
      return parts.join("<br>") || '<span class="subtle">No displayable source excerpt is attached to this claim.</span>';
    }

    function humanSourceLines(text) {
      const rawParts = String(text || "").split(";").map(item => item.trim()).filter(Boolean);
      const converted = rawParts.map(humanSecFactLine).filter(Boolean);
      if (converted.length) return converted.slice(0, 5);
      const fallback = excerpt(text, 300);
      return fallback ? [fallback] : [];
    }

    function humanSecFactLine(line) {
      const match = String(line || "").match(/^(.+?) \(([^)]+)\) for (fiscal quarter|fiscal year) ending (\d{4}-\d{2}-\d{2}): (-?\d+(?:\.\d+)?) \(form ([^)]+)\)$/);
      if (!match) return "";
      const [_all, concept, unit, periodKind, endDate, rawValue, form] = match;
      const label = humanFactName(concept);
      const value = formatFactValue(rawValue, unit);
      const period = `${periodKind} ended ${formatDateLabel(endDate)}`;
      return `${label}: ${value} for ${period} (${form})`;
    }

    function humanFactName(name) {
      const labels = {
        RevenueFromContractWithCustomerExcludingAssessedTax: "Revenue",
        SalesRevenueNet: "Revenue",
        Revenues: "Revenue",
        CostOfRevenue: "Cost of revenue",
        CostOfGoodsAndServicesSold: "Cost of revenue",
        GrossProfit: "Gross profit",
        OperatingIncomeLoss: "Operating income",
        NetIncomeLoss: "Net income",
        EarningsPerShareBasic: "Basic EPS",
        EarningsPerShareDiluted: "Diluted EPS",
        Assets: "Total assets",
        Liabilities: "Total liabilities",
        StockholdersEquity: "Shareholders' equity",
        CashAndCashEquivalentsAtCarryingValue: "Cash and equivalents",
        CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents: "Cash and equivalents",
        NetCashProvidedByUsedInOperatingActivities: "Operating cash flow",
        PaymentsToAcquirePropertyPlantAndEquipment: "Capital expenditures",
        ResearchAndDevelopmentExpense: "Research and development expense",
        SellingGeneralAndAdministrativeExpense: "SG&A expense",
        CommonStocksIncludingAdditionalPaidInCapital: "Common stock and paid-in capital",
      };
      if (labels[name]) return labels[name];
      return String(name || "Fact")
        .replace(/([a-z])([A-Z])/g, "$1 $2")
        .replace(/And/g, "and")
        .replace(/\bUsd\b/g, "USD")
        .trim();
    }

    function humanFactPeriod(period) {
      const text = String(period || "").trim();
      if (!text) return "";
      const fyQuarter = text.match(/^(\d{4})\s+(Q[1-4])/i);
      if (fyQuarter) return `FY${fyQuarter[1]} ${fyQuarter[2].toUpperCase()}`;
      const dateOnly = text.match(/^\d{4}-\d{2}-\d{2}$/);
      if (dateOnly) return `period ended ${formatDateLabel(text)}`;
      return text.replace(/\s+CY\d{4}Q[1-4]\b/i, "");
    }

    function formatFactValue(value, unit) {
      if (value === null || value === undefined || value === "") return "n/a";
      const numeric = Number(value);
      const unitText = String(unit || "").toUpperCase();
      if (!Number.isFinite(numeric)) return String(value);
      const compact = compactNumber(numeric);
      if (unitText === "USD") return `$${compact}`;
      if (unitText === "SHARES") return `${compact} shares`;
      if (unitText) return `${compact} ${unit}`;
      return compact;
    }

    function compactNumber(value) {
      const number = Number(value);
      const sign = number < 0 ? "-" : "";
      const abs = Math.abs(number);
      const format = (divisor, suffix) => `${sign}${trimTrailingZeros((abs / divisor).toFixed(abs >= divisor * 100 ? 0 : 1))}${suffix}`;
      if (abs >= 1e12) return format(1e12, "T");
      if (abs >= 1e9) return format(1e9, "B");
      if (abs >= 1e6) return format(1e6, "M");
      if (abs >= 1e3) return format(1e3, "K");
      return trimTrailingZeros(abs.toFixed(2));
    }

    function trimTrailingZeros(value) {
      return String(value).replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
    }

    function formatDateLabel(value) {
      const text = String(value || "");
      const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!match) return text;
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return `${months[Number(match[2]) - 1]} ${Number(match[3])}, ${match[1]}`;
    }

    function consistencySummary(result) {
      const verdict = verdictLabel(result.verdict);
      const issues = result.issues || [];
      const lines = [`<strong>${escapeHtml(verdict)}</strong>`];
      const numericSummary = naturalNumericSummary(result.numeric_derivation, issues);
      if (numericSummary) {
        lines.push(escapeHtml(numericSummary));
        return lines.join("<br>");
      }
      if (issues.length) {
        lines.push(escapeHtml(naturalIssueSummary(issues)));
      } else if (String(result.verdict || "").includes("support")) {
        lines.push("The source values or description broadly match the claim.");
      } else {
        lines.push("The current source is not enough to fully confirm this claim.");
      }
      return lines.join("<br>");
    }

    function naturalNumericSummary(derivation, issues) {
      const matchSummary = numericMatchParts(derivation, issues);
      if (!matchSummary.confirmed.length && !matchSummary.unconfirmed.length) {
        return naturalFormulaSummary(derivation);
      }
      const confirmed = matchSummary.confirmed.length
        ? `The source confirms ${joinHumanList(matchSummary.confirmed)}.`
        : "";
      const unconfirmed = matchSummary.unconfirmed.length
        ? `It does not clearly confirm ${joinHumanList(matchSummary.unconfirmed)} in this excerpt.`
        : "";
      if (confirmed && unconfirmed) {
        return `${confirmed} ${unconfirmed} That is why this claim is marked as partially consistent.`;
      }
      if (confirmed) {
        return `${confirmed} The displayed evidence supports the numeric part of the claim.`;
      }
      return `${unconfirmed || "The displayed evidence is related, but it is not enough to verify the numeric claim."}`;
    }

    function numericMatchParts(derivation, issues) {
      const confirmed = [];
      const unconfirmed = [];
      if (derivation && derivation.expression === "numeric_match_summary") {
        confirmed.push(...parseMatchedValues(derivation.inputs?.matched_values));
        unconfirmed.push(...parseUnmatchedValues(derivation.inputs?.unmatched_values));
      }
      (issues || []).forEach(issue => {
        const text = String(issue || "");
        if (text.startsWith("matched ")) {
          confirmed.push(...parseMatchedValues(text.replace(/^matched\s+/, "")));
        }
        if (text.startsWith("unmatched claim numbers:")) {
          unconfirmed.push(...parseUnmatchedValues(text.replace(/^unmatched claim numbers:\s*/, "")));
        }
      });
      return {
        confirmed: uniqueStrings(confirmed).slice(0, 3),
        unconfirmed: uniqueStrings(unconfirmed).slice(0, 3),
      };
    }

    function parseMatchedValues(value) {
      const text = String(value || "").trim();
      if (!text || text === "none") return [];
      return text.split(";").map(item => item.trim()).filter(Boolean).map(item => {
        const [claimValue, sourceValue] = item.split("->").map(part => part && part.trim());
        const display = claimValue || sourceValue || item;
        return `the claimed value ${humanClaimValue(display, sourceValue)}`;
      });
    }

    function parseUnmatchedValues(value) {
      const text = String(value || "").trim();
      if (!text || text === "none") return [];
      const dateFragments = [];
      const values = [];
      text.split(",").map(item => item.trim()).filter(Boolean).forEach(item => {
        if (/^\d{1,2}$/.test(item)) {
          dateFragments.push(item);
        } else {
          values.push(humanClaimValue(item));
        }
      });
      const output = values.map(item => `the claimed ${claimValueKind(item)} ${item}`);
      if (dateFragments.length && !values.length) {
        output.push("the exact date or period detail");
      } else if (dateFragments.length) {
        output.push("the date or period detail");
      }
      return output;
    }

    function humanClaimValue(value, sourceValue) {
      const text = String(value || "").trim();
      const sourceText = String(sourceValue || "").trim();
      const moneyText = text.match(/\$?\s*(-?\d+(?:\.\d+)?)\s*(billion|million|trillion|bn|mm|m|b|t)?/i);
      if (text.includes("$") && moneyText) {
        const number = Number(moneyText[1]);
        const scale = (moneyText[2] || "").toLowerCase();
        if (Number.isFinite(number)) {
          if (["trillion", "t"].includes(scale)) return `$${trimTrailingZeros(number.toFixed(1))}T`;
          if (["billion", "bn", "b"].includes(scale)) return `$${trimTrailingZeros(number.toFixed(1))}B`;
          if (["million", "mm", "m"].includes(scale)) return `$${trimTrailingZeros(number.toFixed(1))}M`;
        }
      }
      if (/^-?\d+(\.\d+)?%$/.test(text)) return text;
      const sourceNumber = Number(sourceText.replace(/,/g, ""));
      if (Number.isFinite(sourceNumber) && Math.abs(sourceNumber) >= 1e6 && text.includes("$")) {
        return `$${compactNumber(sourceNumber)}`;
      }
      return text;
    }

    function claimValueKind(value) {
      const text = String(value || "").toLowerCase();
      if (text.includes("%")) return "percentage";
      if (text.includes("$")) return "amount";
      return "value";
    }

    function naturalFormulaSummary(derivation) {
      if (!derivation) return "";
      if (derivation.expression && derivation.expression.includes("current - prior")) {
        const result = derivation.result === null || derivation.result === undefined ? "" : `${(Number(derivation.result) * 100).toFixed(2)}%`;
        const status = derivation.passed ? "matches" : "does not match";
        return result
          ? `Recomputing the growth rate from the stored values gives ${result}, which ${status} the claim.`
          : "The growth-rate check could not be recomputed from the displayed values.";
      }
      if (derivation.passed === true) return "The numeric calculation is consistent with the stored evidence.";
      if (derivation.passed === false) return "The numeric calculation does not match the stored evidence.";
      return "";
    }

    function naturalIssueSummary(issues) {
      const readable = readableIssues(issues).filter(Boolean);
      if (!readable.length) return "The current source is not enough to fully confirm this claim.";
      return `The verifier found ${joinHumanList(readable.slice(0, 3))}.`;
    }

    function readableIssues(issues) {
      return (issues || []).map(issue => {
        const text = String(issue || "");
        if (text.startsWith("matched ")) {
          return text.replace(/^matched /, "a matching claim value: ");
        }
        if (text.startsWith("unmatched claim numbers:")) {
          const values = parseUnmatchedValues(text.replace(/^unmatched claim numbers:\s*/, ""));
          return values.length ? `${joinHumanList(values)} is not clearly shown in this source` : "some claimed numbers are not clearly shown in this source";
        }
        if (text === "ambiguous_unit_currency_or_period") {
          return "the unit, currency, or period is ambiguous";
        }
        return text;
      });
    }

    function humanReviewSummary(result) {
      const reasons = result.review_reasons || [];
      if (!result.human_review_required && !reasons.length) return "Human review: not required";
      return `Human review: required because ${escapeHtml(reasons.map(reviewReasonLabel).join(", ") || "a confidence guardrail was triggered")}`;
    }

    function verdictLabel(value) {
      const text = String(value || "").toLowerCase();
      if (text.includes("contradict")) return "Inconsistent";
      if (text.includes("not_applicable")) return "Not fact-checkable";
      if (text.includes("insufficient") || text.includes("not_found") || text.includes("weak")) return "Insufficient evidence";
      if (text.includes("partial")) return "Partially consistent";
      if (text.includes("support") || text.includes("verified")) return "Consistent";
      return value || "n/a";
    }

    function reviewReasonLabel(value) {
      const labels = {
        no_official_primary_source: "no official primary source was found",
        non_official_sources_only: "only non-official sources were available",
        official_source_conflict: "official sources conflict",
        amended_or_restatement_or_vintage_revision: "an amendment, restatement, or vintage revision is present",
        low_entity_resolution_confidence: "entity resolution is uncertain",
        low_retrieval_sufficiency: "retrieved evidence is not sufficient",
        ambiguous_unit_currency_or_period: "the unit, currency, or period is ambiguous",
        explanation_claim_needs_human_review: "the explanatory claim needs human judgment",
      };
      return labels[value] || value;
    }

    function excerpt(value, maxLength) {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      if (text.length <= maxLength) return text;
      return `${text.slice(0, maxLength - 1)}...`;
    }

    function uniqueStrings(values) {
      return [...new Set((values || []).map(value => String(value || "").trim()).filter(Boolean))];
    }

    function joinHumanList(values) {
      const items = uniqueStrings(values);
      if (!items.length) return "";
      if (items.length === 1) return items[0];
      if (items.length === 2) return `${items[0]} and ${items[1]}`;
      return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
    }

    function fmtConfidence(value) {
      if (value === null || value === undefined || value === "n/a") return "n/a";
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric.toFixed(2) : String(value);
    }

    function pillClass(value) {
      const text = String(value || "").toLowerCase();
      if (text.includes("very") || text.includes("high") || text.includes("support")) return "good";
      if (text.includes("review") || text.includes("medium") || text.includes("partial") || text.includes("mixed")) return "warn";
      if (text.includes("low") || text.includes("contradict") || text.includes("insufficient") || text.includes("weak")) return "bad";
      return "";
    }

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
