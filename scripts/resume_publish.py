"""Publish a validated résumé generation as one application directory."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


class PublicationError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def publication_lock(output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / f".{output.name}.resume.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def previous_pdf(output: Path, requested: str | None, base_generation: str | None = None, *, require_base: bool = False) -> str:
    if not output.exists():
        if base_generation:
            raise PublicationError("the expected published generation is missing")
        return requested or "resume.pdf"
    if not output.is_dir():
        raise PublicationError("resume output must be a directory")
    manifest = output / "validation.json"
    if manifest.is_symlink() or (manifest.exists() and not manifest.is_file()):
        raise PublicationError("validation.json is not a regular file")
    existing = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    primary = existing.get("primary_pdf")
    if base_generation and base_generation != existing.get("generation"):
        raise PublicationError("published generation changed; rebuild the draft against the current model")
    if existing.get("generation"):
        if existing.get("valid") is not True or not isinstance(primary, str):
            raise PublicationError("last published generation has an invalid manifest")
        expected_outputs = existing.get("outputs", {})
        for name, entry in expected_outputs.items():
            artifact = output / name
            if (Path(name).name != name or artifact.is_symlink() or not artifact.is_file()
                    or digest(artifact) != entry.get("sha256")):
                raise PublicationError(f"last published generation failed integrity check for {name}")
        for name in ("resume.json", primary):
            if name not in expected_outputs:
                raise PublicationError("last published generation has an incomplete manifest")
        report = output / "validation.md"
        if report.is_symlink() or not report.is_file() or digest(report) != existing.get("report_sha256"):
            raise PublicationError("last published Markdown report failed integrity check")
        if require_base and not base_generation:
            raise PublicationError("updating a published bundle requires --base-generation")
        if requested and requested != primary:
            raise PublicationError(f"published PDF path is {primary}; update that path")
        return primary

    pdfs = sorted(path.name for path in output.glob("*.pdf"))
    if len(pdfs) > 1 and requested is None:
        raise PublicationError("multiple existing PDFs; identify the existing file with --pdf-name")
    if requested and pdfs and requested not in pdfs:
        raise PublicationError("choose an existing PDF path with --pdf-name")
    return requested or (pdfs[0] if pdfs else "resume.pdf")


def exchange_directories(staged: Path, output: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        operation = libc.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = operation(os.fsencode(staged), os.fsencode(output), 0x00000002)  # RENAME_SWAP
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        operation = libc.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = operation(-100, os.fsencode(staged), -100, os.fsencode(output), 2)  # AT_FDCWD, RENAME_EXCHANGE
    else:
        raise PublicationError("this platform cannot atomically replace a résumé bundle")
    if result != 0:
        code = ctypes.get_errno() or errno.EIO
        raise PublicationError(f"atomic résumé replacement failed: {os.strerror(code)}")


def require_atomic_update(output: Path) -> None:
    """Probe the actual destination filesystem without writing to the live bundle."""
    if not output.exists():
        return
    parent = output.parent
    if output.stat().st_dev != parent.stat().st_dev or output.is_mount():
        raise PublicationError("resume update refused: the bundle is a separate mount")
    try:
        with tempfile.TemporaryDirectory(prefix=".ekb-exchange-probe-", dir=parent) as temporary:
            probe = Path(temporary)
            left = probe / "staging" / "left"
            right = probe / "right"
            left.mkdir(parents=True)
            right.mkdir()
            (left / "before").touch()
            (right / "after").touch()
            exchange_directories(left, right)
            if not (left / "after").is_file() or not (right / "before").is_file():
                raise PublicationError("exchange probe did not swap both directory contents")
    except (OSError, PublicationError) as exc:
        raise PublicationError(
            f"resume update refused before staging; existing bundle retained. "
            f"Atomic directory exchange could not be verified at {parent}: {exc}"
        ) from exc


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(staged: Path, output: Path, managed: set[str]) -> None:
    if output.exists():
        for entry in output.iterdir():
            if entry.name in managed:
                if entry.is_symlink() or not entry.is_file():
                    raise PublicationError(f"cannot replace {entry.name}: expected a regular file")
                continue
            target = staged / entry.name
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, target, symlinks=True, copy_function=os.link)
            else:
                os.link(entry, target, follow_symlinks=False)
    for name in managed:
        with (staged / name).open("rb") as handle:
            os.fsync(handle.fileno())
    sync_directory(staged)
    if output.exists():
        exchange_directories(staged, output)
    else:
        os.rename(staged, output)
    # The directory swap is already the commit point. A subsequent sync error
    # cannot turn the committed generation into a reported failed update.
    try:
        sync_directory(output.parent)
    except OSError as exc:
        print(f"EKB Resume: bundle published, but the filesystem sync failed: {exc}", file=sys.stderr)
