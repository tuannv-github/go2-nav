"""Length-prefixed named-pipe (FIFO) frames for the eth0 <-> ext odom relay."""

from __future__ import annotations

import errno
import os
import stat
import struct

_HDR = struct.Struct('!I')
_MAX = 1024 * 1024


def ensure_fifo(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        os.mkfifo(path, 0o666)
    except FileExistsError:
        mode = os.stat(path).st_mode
        if not stat.S_ISFIFO(mode):
            raise RuntimeError(f'{path} exists and is not a named pipe') from None


def _open_rdwr(path: str) -> int:
    # O_RDWR: open does not block; reader does not EOF if writer restarts.
    return os.open(path, os.O_RDWR | os.O_NONBLOCK)


class FifoWriter:
    def __init__(self, path: str) -> None:
        self.path = path
        ensure_fifo(path)
        self._fd = -1

    def write(self, payload: bytes) -> bool:
        n = len(payload)
        if n == 0 or n > _MAX:
            return False
        if self._fd < 0:
            try:
                self._fd = _open_rdwr(self.path)
            except OSError:
                return False
        frame = _HDR.pack(n) + payload
        try:
            sent = os.write(self._fd, frame)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EPIPE, errno.ENXIO):
                self.close()
                return False
            raise
        if sent != len(frame):
            self.close()
            return False
        return True

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


class FifoReader:
    def __init__(self, path: str) -> None:
        self.path = path
        ensure_fifo(path)
        self._fd = _open_rdwr(path)
        self._buf = bytearray()

    def read_messages(self) -> list[bytes]:
        try:
            chunk = os.read(self._fd, 65536)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return []
            raise
        if chunk:
            self._buf.extend(chunk)
        out: list[bytes] = []
        while True:
            if len(self._buf) < _HDR.size:
                break
            n = _HDR.unpack_from(self._buf, 0)[0]
            if n == 0 or n > _MAX:
                self._buf.clear()
                break
            need = _HDR.size + n
            if len(self._buf) < need:
                break
            out.append(bytes(self._buf[_HDR.size:need]))
            del self._buf[:need]
        return out

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
