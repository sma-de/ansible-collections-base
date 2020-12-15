
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import os

from ansible.errors import AnsibleOptionsError
from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBase, NormalizerBase, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.proxy import ConfigNormerProxy
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY
from ansible_collections.smabot.base.plugins.action import command_which

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


VARSDIR_DEFAULT_NAME = 'vars.d'


class ExpandVarDirsNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
          'role_paths', DefaultSetterConstant(True)
        )

        super(ExpandVarDirsNormalizer, self).__init__(pluginref, *args, **kwargs)


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        reslist = []

        tmplist = my_subcfg.get('extra_dirs', None) or []

        if my_subcfg['role_paths']:
            # if role_paths flag is set, check all parent roles for var dirs
            tmp = self.pluginref.get_ansible_var(
               'ansible_parent_role_paths', default=None
            ) or []

            for d in tmp:
                tmplist.append(d + '/' + VARSDIR_DEFAULT_NAME)

        # filter out dirs, which do not exist
        for d in tmplist:
            tmp = self.pluginref.exec_module('ansible.builtin.stat', 
                modargs={'path': d}
            )

            if tmp['stat']['exists'] and tmp['stat']['isdir']:
                reslist.append(d)

        my_subcfg['_dirlist'] = reslist
        return my_subcfg


class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            ExpandVarDirsNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'expand_vardirs_args'

    @property
    def supports_merging(self):
        return False

    @property
    def allow_empty(self):
        return True

