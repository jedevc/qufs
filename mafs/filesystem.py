import fuse

import os
import stat
import sys
import errno

import time

from . import router
from . import file

class FileSystem(fuse.Operations):
    def __init__(self):
        self.files = {}
        self.router = router.Router()
        self.list_router = router.Router()
        self.open_files = {}

        self.fh = 0

        self.timestamp = time.time()

    # Filesystem methods
    # ==================

    def getattr(self, path, fi=None):
        result = self.router.lookup(path)
        if result:
            if result.data:
                # file
                return result.data.stat(path, result.parameters)
            else:
                # directory
                uid, gid, _ = fuse.fuse_get_context()
                return {
                    'st_atime': self.timestamp,
                    'st_ctime': self.timestamp,
                    'st_mtime': self.timestamp,

                    'st_gid': gid,
                    'st_uid': uid,

                    'st_mode': stat.S_IFDIR | 0o755,
                    'st_nlink': 1,
                    'st_size': 0
                }

        # file not found
        raise fuse.FuseOSError(errno.ENOENT)

    def readdir(self, path, fi):
        dirs = ['.', '..']

        ls = self.list_router.lookup(path)
        if ls and ls.data:
            contents = ls.data(path, ls.parameters)
            dirs.extend(contents)
        else:
            contents = self.router.list(path)
            if contents and contents.data:
                dirs.extend(contents.data)

        return dirs

    def readlink(self, path):
        result = self.router.lookup(path)
        if result:
            return result.data.get(path, result.parameters)

    def truncate(self, path, length, fi=None):
        pass

    # File methods
    # ============

    def open(self, path, fi):
        # forbid append operation
        if fi.flags & os.O_APPEND == os.O_APPEND:
            return -1

        result = self.router.lookup(path)
        if result and result.data:
            fi.fh = self.fh
            self.fh += 1
            fi.direct_io = True

            self.open_files[fi.fh] = file.File(result.data, [path, result.parameters], fi.flags)

            return 0
        else:
            return -1

    def read(self, path, length, offset, fi):
        return self.open_files[fi.fh].read(length, offset)

    def write(self, path, data, offset, fi):
        return self.open_files[fi.fh].write(data, offset)

    def release(self, path, fi):
        file = self.open_files.pop(fi.fh)
        file.release()

    # Callbacks
    # =========

    def _create_file(self, path, *args, **kwargs):
        if path in self.files:
            return self.files[path]
        else:
            fd = file.FileData(*args, **kwargs)
            self.files[path] = fd
            self.router.add(path, fd)
            return fd

    def onread(self, path, callback, encoding='utf-8'):
        f = self._create_file(path)
        f.onread(callback, encoding)

    def onreadlink(self, path, callback):
        f = self._create_file(path, ftype=stat.S_IFLNK)
        f.onget(callback)

    def onwrite(self, path, callback, encoding='utf-8'):
        f = self._create_file(path)
        f.onwrite(callback, encoding)

    def onlist(self, path, callback):
        self.list_router.add(path, callback)

    def onstat(self, path, callback):
        f = self._create_file(path)
        f.onstat(callback)
