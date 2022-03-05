
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import pathlib

from ansible.errors import AnsibleOptionsError
##from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, \
  DefaultSetterConstant, \
  NormalizerBase, \
  NormalizerNamed

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import \
  get_subdict, \
  merge_dicts, \
  setdefault_none, \
  SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



def locale_builtin(locale):
    if locale.lower() == 'c':
        return True

    if locale.lower().startswith('c.'):
        return True

    return False


# split into builtin and not builtin locales
def split_locales(locale_lst):
    builtins = []
    not_builtins = []

    for l in locale_lst:
        if locale_builtin(l):
            builtins.append(l)
        else:
            not_builtins.append(l)

    return (builtins, not_builtins)



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'present', DefaultSetterConstant(['C.UTF-8'])
        )

        self._add_defaultsetter(kwargs,
          'absent', DefaultSetterConstant([])
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          OsPackagesNormer(pluginref),
          VarsNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        presents = my_subcfg['present']

        if presents:
            setdefault_none(my_subcfg, 'active', presents[0])

        return my_subcfg


class OsPackagesNormer(NormalizerBase):

##    def __init__(self, pluginref, *args, **kwargs):
##        super(PreExistsTestNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['os_packages']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)

        presents = pcfg['present']

        my_subcfg['enabled'] = False

        if presents:
            builtins, not_builtins = split_locales(presents)

            if not_builtins:
                # TODO: if we have at least one not builtin locale we need packages here, which are also distro dependend
                my_subcfg['enabled'] = True
                ansible_assert(False, "TODO: not-builtin locales not yet implemented")

        return my_subcfg



class VarsNormer(NormalizerBase):

##    def __init__(self, pluginref, *args, **kwargs):
##        subnorms = kwargs.setdefault('sub_normalizers', [])
##        subnorms += [
##          DownloadConfigNormer(pluginref),
##        ]
##
##        super(DownloadNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['vars']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)

        active = pcfg.get('active', None)

        if active:
            setdefault_none(my_subcfg, 'LANG', active)
            setdefault_none(my_subcfg, 'LANGUAGE', active)
            setdefault_none(my_subcfg, 'LC_ALL', active)

        return my_subcfg



class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            RootCfgNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_base_handle_locales_args'

    @property
    def supports_merging(self):
        return False

