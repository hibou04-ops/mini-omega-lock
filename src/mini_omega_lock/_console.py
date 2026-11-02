# SPDX-License-Identifier: Apache-2.0
"""Keep terminal encoding handling separate from measurement objects and files."""

from __future__ import annotations

import codecs
import json
import sys
from typing import TextIO


def write_console(text: str, *, stream: TextIO | None = None, structured: str | None = None) -> None:
    """Write safely using the stream's existing encoding; never reconfigure it.

    UTF streams and in-memory captures retain their original representation.
    Restricted encodings receive ASCII JSON escapes or readable text with
    typographic punctuation normalized and unsupported characters escaped.
    """
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None)
    if encoding is not None:
        canonical = codecs.lookup(encoding).name
        if canonical not in {"utf-8", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"}:
            if structured == "json":
                text = json.dumps(json.loads(text), ensure_ascii=True, indent=2) + "\n"
            elif structured == "jsonl":
                text = "\n".join(json.dumps(json.loads(line), ensure_ascii=True) for line in text.splitlines()) + "\n"
            else:
                text = text.translate(str.maketrans({"—": "-", "–": "-", "…": "...", "‘": "'", "’": "'", "“": '"', "”": '"'}))
                text = text.encode(encoding, errors="backslashreplace").decode(encoding)
    stream.write(text)

