#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import re

##from ansible.errors import AnsibleError, AnsibleInternalError
from ansible.plugins.lookup import LookupBase
from ansible.module_utils._text import to_native, to_text
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import ArgsPlugin


display = Display()


class FilterBase(ArgsPlugin):

    def __init__(self, *args, **kwargs):
        super(FilterBase, self).__init__(*args, **kwargs)

    @property
    def name(self):
        return type(self).FILTER_ID

    @property
    def error_prefix(self):
        return self.name + ': '


    @abc.abstractmethod
    def run_specific(self, *args):
        pass


    def __call__(self, *args, **kwargs):
        # handle args / params for this task
        self._handle_taskargs(self.argspec, kwargs, self._taskparams)
        return self.run_wrapper(*args)

