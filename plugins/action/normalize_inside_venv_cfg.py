
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import os

from ansible.errors import AnsibleOptionsError
##from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, \
  DefaultSetterConstant, \
  NormalizerBase

##from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY
##from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
          'keep_os_packages', DefaultSetterConstant(False)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          VenvCfgNormer(pluginref),
          PipCfgNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)


class VenvCfgNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
          'site_packages', DefaultSetterConstant(True)
        )

        self._add_defaultsetter(kwargs, 
          'keep', DefaultSetterConstant(False)
        )

        self._add_defaultsetter(kwargs, 
          'path', DefaultSetterConstant(None)
        )

        super(VenvCfgNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['venv']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        path = my_subcfg['path']

        if not path:
            # create tmpdir to use as venv
            tmp = self.pluginref.exec_module('ansible.builtin.tempfile',
                modargs={'state': 'directory', 'suffix': '.venv'}
            )

            path = tmp['path']
            my_subcfg['path'] = path

        my_subcfg['pybin'] = os.path.join(path, 'bin', 'python')
        return my_subcfg


class PipCfgNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
          'extra_packages', DefaultSetterConstant([])
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          PipOptsNormer(pluginref),
        ]

        super(PipCfgNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['pip']


class PipOptsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
          'virtualenv_command', DefaultSetterConstant(None)
        )

        super(PipOptsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['opts']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        tmp = self.get_parentcfg(cfg, cfgpath_abs)
        my_subcfg['name'] = tmp['extra_packages']

        tmp = self.get_parentcfg(cfg, cfgpath_abs, 2)
        tmp = tmp['venv']

        my_subcfg['virtualenv'] = tmp['path']
        my_subcfg['virtualenv_site_packages'] = tmp['site_packages']

        venv_cmd = my_subcfg['virtualenv_command']

        if not venv_cmd:
            defpy = self.pluginref.get_ansible_var(
              'ansible_python_interpreter'
            )

            venv_cmd = "{} -m venv".format(defpy)
            my_subcfg['virtualenv_command'] = venv_cmd

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
        return 'smabot_base_run_inside_venv_cfg'

    @property
    def supports_merging(self):
        return False

