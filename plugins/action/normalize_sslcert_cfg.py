
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import os

from ansible.errors import AnsibleOptionsError
from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, \
  DefaultSetterConstant, \
  NormalizerBase, \
  NormalizerNamed

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.proxy import ConfigNormerProxy
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY
from ansible_collections.smabot.base.plugins.action import command_which

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


CONFIG_KEYWORD_AUTODETECT = 'autodetect'


class SslCertCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SslCertNormEcoSystems(pluginref),
        ]

        super(SslCertCfgNormalizer, self).__init__(pluginref, *args, **kwargs)


class SslCertNormEcoSystems(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SslCertNormEcoJava(pluginref),
          SslCertNormEcoPython(pluginref),
        ]

        super(SslCertNormEcoSystems, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['eco_systems']


class SslCertNormEcoSysABC(NormalizerBase):

    def __init__(self, *args, **kwargs):
        super(SslCertNormEcoSysABC, self).__init__(*args, **kwargs)

    @abc.abstractmethod
    def _handle_specifics_presub_specific(self, cfg, my_subcfg, cfgpath_abs, auto_detect):
        pass

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        active = my_subcfg.get('activate', CONFIG_KEYWORD_AUTODETECT)
        active_autodect = False

        if active == CONFIG_KEYWORD_AUTODETECT:
            active_autodect = True
            active = True
        else:
            active = to_bool(active)

        my_subcfg['activate'] = active

        if not active:
            ## explicitly disabled java cert handling, nothing more to do here
            return my_subcfg

        return self._handle_specifics_presub_specific(
            cfg, my_subcfg, cfgpath_abs, active_autodect
        )



class SslCertNormEcoJava(SslCertNormEcoSysABC):

    def __init__(self, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
          'active_only', DefaultSetterConstant(False)
        )

        super(SslCertNormEcoJava, self).__init__(*args, **kwargs)


    @property
    def config_path(self):
        return ['java']


    def _handle_specifics_presub_specific(self, 
        cfg, my_subcfg, cfgpath_abs, auto_detect
    ):
        jfact = self.pluginref.get_ansible_fact('java', None)

        if not jfact:
            # no java environment detected on target system, 
            # we are done here
            if not auto_detect:
                raise AnsibleOptionsError(
                   "Auto detect failed to find any java home but user"\
                   " explicitly activated java cert handling, either set"\
                   " 'activate' key to '{}' if this is acceptable or"\
                   " if you are sure that a java installation exist and"\
                   " should be cert handled make sure java_facts module"\
                   " is run before this and if this still does not help"\
                   " try some advanced configuration options for"\
                   " java_facts to help it succesfully detect your java"\
                   " environment (like for example try-paths)".format(
                       CONFIG_KEYWORD_AUTODETECT
                   )
                )

            ## auto detect mode and no java detected, noop
            my_subcfg['activate'] = False
            return my_subcfg

        jvms = []

        if my_subcfg['active_only']:
            ## only handle active jvm
            jvms.append(jfact['active'])
        else:
            ## handle all detected java environments
            jvms += jfact['installations']

        my_subcfg['_jvms'] = jvms
        return my_subcfg



class SslCertNormEcoPython(SslCertNormEcoSysABC):

    def __init__(self, *args, **kwargs):
        super(SslCertNormEcoPython, self).__init__(*args, **kwargs)

    @property
    def config_path(self):
        return ['python']

    def _handle_specifics_presub_specific(self, cfg, my_subcfg, cfgpath_abs, auto_detect):
        pybin = my_subcfg.get('python_binary', None)

        if pybin:
            return my_subcfg

        mres = self.pluginref.run_other_action_plugin(command_which.ActionModule,
          plugin_args={'cmd': ['python', 'python3', 'python2']}, ignore_error=True
        )

        pybin_by_which = None

        if not mres.get('failed', False):
            pybin_by_which = mres['linksrc']

        if not pybin_by_which:
            if not auto_detect:
                raise AnsibleOptionsError(
                   "Auto detect failed to find any python binary but user"\
                   " explicitly activated python cert handling, either set"\
                   " 'activate' key to '{}' if this is acceptable or give"\
                   " an explicit python binary path with the 'python_binary' key"\
                   " if you are sure that a python installation exist and"\
                   " should be cert handled.".format(CONFIG_KEYWORD_AUTODETECT)
                )

            my_subcfg['activate'] = False
            return my_subcfg

        my_subcfg['python_binary'] = pybin_by_which
        return my_subcfg


class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            SslCertCfgNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'handle_system_certs_args'

    @property
    def supports_merging(self):
        return False

