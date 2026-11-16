"""Publish a complete fresh file without replacing an existing path."""
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


@contextmanager
def fresh_output(destination):
    destination = Path(destination)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w+b", dir=destination.parent, prefix=".certloom-", delete=False) as stream:
            temporary = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
