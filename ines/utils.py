# -*- coding: utf-8 -*-
# Copyright (C) Hugo Branquinho. All rights reserved.
#
# @author Hugo Branquinho <hugobranq@gmail.com>

import datetime
from json import dumps
from os import getpid
from os import stat as os_stat
from uuid import uuid4
import warnings

from ines.convert import make_sha256


NOW_DATE = datetime.datetime.now
PROCESS_ID = getpid()


class WarningDict(dict):
    def __init__(self, message='Duplicate item "{key}" with value "{value}"'):
        self.message = message

    def __setitem__(self, key, value):
        if key in self:
            warnings.warn(
                self.message.format(key=key, value=value),
                UserWarning,
                stacklevel=2)

        super(WarningDict, self).__setitem__(key, value)

    def update(self, *args, **kwargs):
        if args:
            if len(args) > 1:
                raise TypeError('update expected at most 1 arguments, '
                                'got %d' % len(args))

            for key, value in dict(args[0]).items():
                self[key] = value

        for key, value in kwargs.items():
            self[key] = value

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]


class MissingDict(dict):
    _base_type = dict

    def __missing__(self, key):
        self[key] = self._base_type()
        return self[key]


class MissingList(MissingDict):
    _base_type = list


class InfiniteDict(dict):
    @property
    def _base_type(self):
        return InfiniteDict


def make_unique_hash():
    key = '.'.join((
        uuid4().hex,
        str(NOW_DATE()),
        str(PROCESS_ID)))
    return make_sha256(key)


def last_read_file_time(path):
    try:
        last_read_time = int(os_stat(file_path).st_atime)
    except OSError:
        pass
    else:
        return last_read_time


def format_json_response_values(status, key, message, **kwargs):
    values = {
        'status': status,
        'property': key,
        'message': message}
    if kwargs:
        values.update(kwargs)
    return values


def format_json_response(*args, **kwargs):
    return dumps(format_json_response_values(*args, **kwargs))
