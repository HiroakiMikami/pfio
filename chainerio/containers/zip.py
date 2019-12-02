from chainerio.container import Container
from chainerio.io import open_wrapper
import io
import logging
import os
import sys
import warnings
import zipfile

from chainerio._typing import Optional
from typing import Type, Callable, Any

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


class ZipContainer(Container):
    def __init__(self, base_handler, base):
        Container.__init__(self, base_handler, base)
        self._check_zip_file_name(base)

        logger.info("using zip container for {}".format(base))
        self.zip_file_obj = None
        self.type = "zip"

    def _check_zip_file_name(self, base):
        assert not "" == base and None is not base,\
            "No zip base file assigned"
        filename, file_extension = os.path.splitext(self.base)

    def _open_zip_file(self, mode='r'):
        mode = mode.replace("b", "")

        if self.zip_file_obj is None:
            zip_file = self.base_handler.open(self.base, "rb")
            if isinstance(self.base_handler, ZipContainer) \
                    and sys.version_info < (3, 7, ):
                # In Python < 3.7, the returned file object from zipfile.open,
                # i.e. ZipExtFile, is not seekable,
                # while in order to open as zip, the zipfile module requires
                # the given file object to be seekable, which makes
                # nested zip impossible.
                # As a workaround, in case of nested zip,  we read the
                # whole nested zipfile into BytesIO object,
                # which is a seekable file object, upon open.
                # However, it might cause performance and memory
                # issues when the zipfile is huge. A warning is generated
                # for user.

                warnings.warn('In Python < 3.7, '
                              'To support opening nested zip as container, '
                              'ChainerIO has to read '
                              'the entire nested zip upon open, '
                              'which might cause performance or '
                              'memory issues when the nested zip is huge.',
                              category=RuntimeWarning)
                zip_file = io.BytesIO(zip_file.read())

            self.zip_file_obj = zipfile.ZipFile(zip_file, mode)

    def _close_zip_file(self):
        if None is not self.zip_file_obj:
            self.zip_file_obj.close()
            self.zip_file_obj = None

    def _wrap_fileobject(self, file_obj: Type['IOBase'],
                         file_path: str, mode: str = 'rb',
                         buffering: int = -1,
                         encoding: Optional[str] = None,
                         errors: Optional[str] = None,
                         newline: Optional[str] = None,
                         closefd: bool = True,
                         opener: Optional[Callable[
                             [str, int], Any]] = None) -> Type['IOBase']:
        if 'b' not in mode:
            file_obj = io.TextIOWrapper(file_obj, encoding, errors, newline)
        return file_obj

    @open_wrapper
    def open(self, file_path, mode='r',
             buffering=-1, encoding=None, errors=None,
             newline=None, closefd=True, opener=None):

        file_path = os.path.normpath(file_path)
        self._open_zip_file(mode)

        # zip only supports open with r rU or U
        nested_file = self.zip_file_obj.open(file_path, "r")
        return nested_file

    def close(self):
        self._close_zip_file()

    def info(self):
        info_str = \
            "this is zip container with filename {} on {} filesystem".format(
                self.base, self.base_handler.type)
        return info_str

    def stat(self, path):
        path = os.path.normpath(path)
        self._open_zip_file()
        if path in self.zip_file_obj.namelist():
            actual_path = path
        elif (not path.endswith('/')
              and path + '/' in self.zip_file_obj.namelist()):
            # handles cases when path is a directory but without trailing slash
            # see issue $67
            actual_path = path + '/'
        else:
            raise FileNotFoundError(
                "{} is not found".format(path))

        return self.zip_file_obj.getinfo(actual_path)

    def list(self, path_or_prefix: str = "", recursive=False):
        self._open_zip_file()

        if path_or_prefix:
            path_or_prefix = os.path.normpath(path_or_prefix)
            # cannot move beyond root
            given_dir_list = path_or_prefix.split('/')
            if ("." in given_dir_list or ".." in given_dir_list
                    or {""} == set(given_dir_list)):
                given_dir_list = []
                path_or_prefix = ""
        else:
            given_dir_list = []

        if path_or_prefix:
            if not self.exists(path_or_prefix):
                raise FileNotFoundError(
                    "{} is not found".format(path_or_prefix))
            elif not self.isdir(path_or_prefix):
                raise NotADirectoryError(
                    "{} is not a directory".format(path_or_prefix))

        if recursive:
            for name in self.zip_file_obj.namelist():
                if name.startswith(path_or_prefix):
                    name = name[len(path_or_prefix):].strip("/")
                    if name:
                        yield name
        else:
            _list = set()
            for name in self.zip_file_obj.namelist():
                return_file_name = None
                current_dir_list = os.path.normpath(name).split('/')
                if not given_dir_list:
                    # if path_or_prefix is not given
                    return_file_name = current_dir_list[0]
                else:
                    if (current_dir_list
                            and len(current_dir_list) > len(given_dir_list)
                            and current_dir_list[:len(given_dir_list)] ==
                            given_dir_list):
                        return_file_name = current_dir_list[
                            len(given_dir_list):][0]

                if (return_file_name is not None
                        and return_file_name not in _list):
                    _list.add(return_file_name)
                    yield return_file_name

    def set_base(self, base):
        Container.reset_base_handler(self, base)

        if None is not self.tar_file_obj:
            self.zip_file_obj.close()
            self.zip_file_obj = None

    def isdir(self, file_path: str):
        if self.exists(file_path):
            stat = self.stat(file_path)
            if sys.version_info >= (3, 6, ):
                return stat.is_dir()
            else:
                # The `is_dir` function under `ZipInfo` object
                # is not available before Python 3.6.0
                return "/" == stat.filename[-1]
        else:
            return False

    def mkdir(self, file_path: str, mode=0o777, *args, dir_fd=None):
        raise io.UnsupportedOperation("zip does not support mkdir")

    def makedirs(self, file_path: str, mode=0o777, exist_ok=False):
        raise io.UnsupportedOperation("zip does not support makedirs")

    def exists(self, file_path: str):
        file_path = os.path.normpath(file_path)
        self._open_zip_file()
        namelist = self.zip_file_obj.namelist()
        return (file_path in namelist
                or file_path + "/" in namelist)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if None is not self.zip_file_obj:
            self.zip_file_obj.close()
            self.zip_file_obj = None

    def remove(self, file_path, recursive=False):
        raise io.UnsupportedOperation
