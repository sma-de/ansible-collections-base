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

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import AnsSpaceAndArgsPlugin


display = Display()


class BaseLookup(LookupBase, AnsSpaceAndArgsPlugin):

    def __init__(self, *args, **kwargs):
        LookupBase.__init__(self, *args, **kwargs)
        AnsSpaceAndArgsPlugin.__init__(self)


    def run_other_lookup_plugin(self, plugin_class, *terms, **kwargs):
        display.vv(
           "[LOOKUP_BASE] :: run other plugin '{}': {}".format(plugin_class, terms)
        )

        display.vvv(
           "[LOOKUP_BASE] :: run other plugin, kwargs: {}".format(kwargs)
        )

        def tmp = plugin_class(
          loader=self._loader, templar=self._templar
        )

        ## note: this must be set for plugin default method set_options 
        ##   to work, no idea how ansible sets this normally
        tmp._load_name = plugin_class.__module__
        return tmp.run(terms, variables=self._ansible_varspace, **kwargs)


    @abc.abstractmethod
    def run_specific(self, terms):
        pass


    def run(self, terms, variables=None, **kwargs):
        self._ansible_varspace = variables

        # handle args / params for this task
        self._handle_taskargs(self.argspec, kwargs, self._taskparams)

        return self.run_wrapper(terms)

