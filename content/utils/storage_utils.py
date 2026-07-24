import os
import shutil
import tempfile
from contextlib import contextmanager

from django.core.files.storage import default_storage


@contextmanager
def local_path_from_storage(storage_name: str):
    if not storage_name:
        yield None
        return

    try:
        path = default_storage.path(storage_name)
        yield path
        return
    except Exception:
        pass

    suffix = os.path.splitext(storage_name)[1]
    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temp_path = temp_file.name
    temp_file.close()

    with default_storage.open(storage_name, "rb") as src, open(temp_path, "wb") as dst:
        shutil.copyfileobj(src, dst)

    try:
        yield temp_path
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
