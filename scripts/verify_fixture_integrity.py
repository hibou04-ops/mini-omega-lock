"""SHA-256 integrity check for ``benchmarks/golden_cases/*.json``.

The manifest at ``benchmarks/golden_cases/manifest.json`` records a
SHA-256 over the canonical-JSON form of each case file. Tampering with
a case (accidental save in a different encoding, deliberate edit,
trailing-newline drift) trips this script.

Run modes::

    python scripts/verify_fixture_integrity.py            # verify, exit 1 on mismatch
    python scripts/verify_fixture_integrity.py --write    # (re)build manifest

Canonical form: ``json.dumps(obj, sort_keys=True, indent=2,
ensure_ascii=False)`` + trailing ``"\n"``, encoded UTF-8. The
canonicalisation is on the *parsed* JSON object so file-level
whitespace differences (e.g. trailing blank lines) are squashed; the
checksum reflects the data, not the formatting.

Boundary statement: this script provides **fixture integrity**. It is
not an append-only audit trail and it is not a hash chain across
commits. Git history is the only chronological record. See
``docs/examples.md`` for the explicit limitation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = REPO_ROOT / "benchmarks" / "golden_cases"
MANIFEST = CASES_DIR / "manifest.json"


def _canonical_bytes(obj: dict) -> bytes:
    """Render the parsed JSON object to canonical bytes."""
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _hash_case(path: Path) -> str:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(_canonical_bytes(parsed)).hexdigest()


def _list_case_files() -> list[Path]:
    if not CASES_DIR.exists():
        return []
    return sorted(p for p in CASES_DIR.glob("*.json") if p.name != "manifest.json")


def _build_manifest() -> dict:
    files = _list_case_files()
    digests: dict[str, str] = {}
    for path in files:
        digests[path.name] = _hash_case(path)
    return {
        "format": "mini-omega-lock fixture-integrity v1",
        "canonicalisation": (
            "json.dumps(parsed, sort_keys=True, indent=2, ensure_ascii=False) + '\\n'; UTF-8"
        ),
        "files": digests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help="(Re)build manifest.json from the current case files.",
    )
    args = parser.parse_args(argv)

    case_files = _list_case_files()
    if not case_files:
        print(
            f"no fixture files in {CASES_DIR.relative_to(REPO_ROOT)} — "
            "nothing to verify or write",
            file=sys.stderr,
        )
        return 1

    if args.write:
        manifest = _build_manifest()
        MANIFEST.write_text(
            json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"wrote {MANIFEST.relative_to(REPO_ROOT)} "
            f"with {len(manifest['files'])} entries"
        )
        return 0

    if not MANIFEST.exists():
        print(
            f"missing manifest: {MANIFEST.relative_to(REPO_ROOT)} — "
            "run with --write to create it",
            file=sys.stderr,
        )
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recorded = manifest.get("files", {})
    actual = {p.name: _hash_case(p) for p in case_files}

    missing = set(recorded) - set(actual)
    extra = set(actual) - set(recorded)
    drift = {
        name: (recorded[name], actual[name])
        for name in sorted(set(recorded) & set(actual))
        if recorded[name] != actual[name]
    }

    if not (missing or extra or drift):
        print(
            f"fixture integrity verified ({len(actual)} files; "
            f"format={manifest.get('format', '?')!r})"
        )
        return 0

    print("Fixture integrity check FAILED", file=sys.stderr)
    for name in sorted(missing):
        print(f"  manifest references missing file: {name}", file=sys.stderr)
    for name in sorted(extra):
        print(
            f"  file not listed in manifest: {name} (run --write to add)",
            file=sys.stderr,
        )
    for name, (expected, got) in drift.items():
        print(
            f"  hash drift: {name}\n      expected: {expected}\n      actual:   {got}",
            file=sys.stderr,
        )
    print(
        "\nIf the change was intentional, update the manifest with:\n"
        "  python scripts/verify_fixture_integrity.py --write\n"
        "and commit both the fixture(s) and manifest.json in the same commit.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
