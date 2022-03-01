
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
  setdefault_none, \
  SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SudoMappingsNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)



class SudoMappingsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SudoMappingInstNormer(pluginref),
        ]

        super(SudoMappingsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['mappings']



class SudoMappingInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        super(SudoMappingInstNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return [SUBDICT_METAKEY_ANY]

    @property
    def name_key(self):
        return 'cfgfile'

    @property
    def simpleform_key(self):
        return '_simple_user_spec'


    def _norm_userlist(self, ulist):
        return ','.join(ulist)

    def _norm_hostlist(self, hlist):
        return self._norm_userlist(hlist)


    def _norm_runas(self, runas):
        ansible_assert(False, "TODO: supporting runas")

    def _norm_cmdopts(self, options):
        ansible_assert(False, "TODO: supporting cmdspec options")

    def _norm_cmdtags(self, tags):
        return ' '.join(tags)


    def _norm_cmdspec(self, spec):
        res = []

        # optionally handle runas
        tmp = spec.get('runas', None)

        if tmp:
            res.append(self._norm_runas(tmp))

        # optionally handle options
        tmp = spec.get('options', None)

        if tmp:
            res.append(self._norm_cmdopts(tmp))

        # optionally handle tags
        tmp = spec.get('tags', None)

        if tmp:
            res.append(self._norm_cmdtags(tmp))

        cmd = setdefault_none(spec, 'cmd', 'ALL')
        res.append(cmd)

        return ' '.join(res)


    def _norm_cmdspecs(self, specs):
        tmp = []
        for s in specs:
            tmp.append(self._norm_cmdspec(s))

        return self._norm_userlist(tmp)


    def _norm_subspecs(self, subspec):
        hlist = setdefault_none(subspec, 'hosts', [])

        if not hlist:
            hlist.append('ALL')

        cmdspecs = setdefault_none(subspec, 'cmd_specs', [{}])

        return "{} = {}".format(self._norm_hostlist(hlist),
          self._norm_cmdspecs(cmdspecs)
        )


    def _norm_userspec(self, cfg, my_subcfg, cfgpath_abs, uspec):
        if not isinstance(uspec, collections.abc.Mapping):
            ## assume simple string form
            return {'_export': uspec}

        # create userspec sudo cfg line
        res = []
        res.append(self._norm_userlist(uspec['users']))

        subspecs = setdefault_none(uspec, 'subspecs', [{}])

        tmp = []
        for sub in subspecs:
            tmp.append(self._norm_subspecs(sub))

        ansible_assert(tmp, "Must at least set one subspec")
        res.append(' : '.join(tmp))

        uspec['_export'] = ' '.join(res)
        return uspec



    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        # normalize cfgfile
        cfgfile = pathlib.Path(my_subcfg['cfgfile'])

        if not cfgfile.is_absolute():
            cfgfile = pathlib.Path('/etc/sudoers.d/') / cfgfile

        my_subcfg['cfgfile'] = str(cfgfile)

        # normalize user specs
        uspecs = setdefault_none(my_subcfg, 'user_specs', [])
        tmp = my_subcfg.pop(self.simpleform_key, None)

        if tmp:
            uspecs.append(tmp)

        new_uspecs = []
        for u in uspecs:
            new_uspecs.append(self._norm_userspec(
               cfg, my_subcfg, cfgpath_abs, u)
            )

        my_subcfg['user_specs'] = new_uspecs
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
        return 'smabot_base_setup_sudo_args'

    @property
    def supports_merging(self):
        return False

