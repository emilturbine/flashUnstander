"""Versioned, lossless cache whose entries belong to a conversation."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from os import environ, utime
from pathlib import Path
from threading import Lock
from time import time

from PySide6.QtCore import QIODevice, QSaveFile
from PySide6.QtGui import QImage


CACHE_VERSION = "surface-v1"
CACHE_LIMIT_BYTES = 192 * 1024 * 1024


class DetailTextureCache:
    def __init__(self, directory=None):
        if directory is None:
            local = Path(environ.get("LOCALAPPDATA", str(Path.home())))
            directory = local / "flashUnstander" / "texture-cache"
        self.root = Path(directory)
        self.directory = self.root / CACHE_VERSION
        self._pending = set()
        self._retired = set()
        self._lock = Lock()
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="texture-cache")

    @staticmethod
    def _owner(conversation_id):
        return sha256(conversation_id.encode("utf-8")).hexdigest()

    def _path(self, owner, key):
        return self.directory / owner / ("-".join(map(str, key)) + ".png")

    def load(self, conversation_id, key, width, height):
        owner = self._owner(conversation_id)
        with self._lock:
            if owner in self._retired:
                return None
        path = self._path(owner, key)
        if not path.is_file():
            return None
        image = QImage(str(path))
        if image.isNull() or (image.width(), image.height()) != (width, height):
            return None
        try:
            stamp = time()
            if stamp - path.stat().st_mtime > 3600:
                utime(path, (stamp, stamp))
        except OSError:
            pass
        return image

    def store(self, conversation_id, entries):
        owner = self._owner(conversation_id)
        with self._lock:
            if owner in self._retired:
                return
            batch = [(key, image) for key, image in entries if (owner, key) not in self._pending]
            if not batch:
                return
            self._pending.update((owner, key) for key, _ in batch)
            self._writer.submit(self._write, owner, batch)

    def delete(self, conversation_id):
        owner = self._owner(conversation_id)
        with self._lock:
            self._retired.add(owner)
            self._writer.submit(self._remove_owner, self.directory / owner)

    def retain(self, conversation_ids):
        owners = {self._owner(identifier) for identifier in conversation_ids}
        self._writer.submit(self._remove_orphans, owners)

    def _write(self, owner, entries):
        try:
            directory = self.directory / owner
            directory.mkdir(parents=True, exist_ok=True)
            family = "-".join(map(str, entries[0][0][:2])) + "-"
            committed = False
            for key, image in entries:
                output = QSaveFile(str(self._path(owner, key)))
                if output.open(QIODevice.OpenModeFlag.WriteOnly):
                    if image.save(output, "PNG", 85):
                        committed = output.commit() or committed
                    else:
                        output.cancelWriting()
            # Keep one material generation per planet even if its slot changed.
            if committed:
                for path in directory.glob("*.png"):
                    if not path.name.startswith(family):
                        path.unlink(missing_ok=True)
                self._trim()
        except OSError:
            pass
        finally:
            with self._lock:
                self._pending.difference_update((owner, key) for key, _ in entries)

    @staticmethod
    def _is_owner(directory):
        return (directory.is_dir() and not directory.is_symlink() and len(directory.name) == 64
                and all(c in "0123456789abcdef" for c in directory.name))

    @staticmethod
    def _remove_owner(directory):
        try:
            if directory.is_symlink():
                return
            for path in directory.glob("*.png"):
                path.unlink(missing_ok=True)
            directory.rmdir()
        except OSError:
            pass

    def _remove_orphans(self, owners):
        try:
            for version in self.root.glob("surface-v*"):
                if not version.is_dir() or version.is_symlink():
                    continue
                current = version == self.directory
                for directory in version.iterdir():
                    if self._is_owner(directory) and (not current or directory.name not in owners):
                        self._remove_owner(directory)
                if not current and not any(version.iterdir()):
                    version.rmdir()
            self._trim()
        except OSError:
            pass

    def _trim(self):
        groups = {}
        for path in self.directory.glob("*/*.png"):
            if not self._is_owner(path.parent):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            mtime, size = groups.get(path.parent, (0., 0))
            groups[path.parent] = (max(mtime, stat.st_mtime), size + stat.st_size)
        remaining = sum(size for _, size in groups.values())
        for directory, (_, size) in sorted(groups.items(), key=lambda entry: entry[1][0]):
            if remaining <= CACHE_LIMIT_BYTES:
                break
            self._remove_owner(directory)
            if not directory.exists():
                remaining -= size
