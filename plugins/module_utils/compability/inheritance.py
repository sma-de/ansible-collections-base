#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import sys


def get_abc_baseclass():
    if sys.version_info >= (3, 4):
        return abc.ABC

    return abc.ABCMeta('ABC', (), {})

