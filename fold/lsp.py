"""Sensepin language server. Diagnostics are the compiler's first error."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import foldc

LINE = re.compile(r"line (\d+): (.*)")


def send(payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, value = line.decode("ascii").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def diagnostic(text: str, message: str) -> dict:
    match = LINE.search(message)
    if match is None:
        line_no = 1
        detail = message
    else:
        line_no = int(match.group(1))
        detail = match.group(2)
    rows = text.splitlines()
    index = max(0, line_no - 1)
    width = len(rows[index]) if index < len(rows) else 1
    return {
        "range": {
            "start": {"line": index, "character": 0},
            "end": {"line": index, "character": max(width, 1)},
        },
        "severity": 1,
        "source": "sensepin",
        "message": detail,
    }


def uri_path(uri: str) -> Path | None:
    if not uri.startswith("file:"):
        return None
    path = unquote(urlparse(uri).path)
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path)


def publish(uri: str, text: str) -> None:
    items: list[dict] = []
    origin = uri_path(uri)
    if origin is None or not origin.is_file():
        origin = None
    try:
        foldc.compile_text(text, origin)
    except foldc.FoldError as exc:
        items.append(diagnostic(text, str(exc)))
    except RecursionError:
        items.append(diagnostic(text, "source is too deep"))
    send(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": items},
        }
    )


def main() -> None:
    documents: dict[str, str] = {}
    while True:
        message = read_message()
        if message is None:
            return
        method = message.get("method")
        number = message.get("id")
        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": number,
                    "result": {"capabilities": {"textDocumentSync": 1}},
                }
            )
            continue
        if method == "shutdown":
            send({"jsonrpc": "2.0", "id": number, "result": None})
            continue
        if method == "exit":
            return
        if method == "textDocument/didOpen":
            document = message["params"]["textDocument"]
            documents[document["uri"]] = document["text"]
            publish(document["uri"], document["text"])
            continue
        if method == "textDocument/didChange":
            document = message["params"]["textDocument"]
            text = message["params"]["contentChanges"][0]["text"]
            documents[document["uri"]] = text
            publish(document["uri"], text)
            continue
        if method == "textDocument/didSave":
            document = message["params"]["textDocument"]
            text = documents.get(document["uri"], "")
            publish(document["uri"], text)
            continue
        if number is not None:
            send({"jsonrpc": "2.0", "id": number, "result": None})


if __name__ == "__main__":
    main()
