
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


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



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SourcesInstNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg['_export_lst'] = []
        return my_subcfg



class SourcesInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
           (SourcesInstSigningNormer, True),
        ]

        self._add_defaultsetter(kwargs,
          'custom_vars', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'attributes', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        super(SourcesInstNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def name_key(self):
        return 'apt_file'

    @property
    def config_path(self):
        return ['sources', SUBDICT_METAKEY_ANY]


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        ## collect all variables and template source line with them
        cvars = my_subcfg['custom_vars']
        attr = my_subcfg['attributes']

        signing = setdefault_none(my_subcfg, 'signing', False)

        if signing:
            attr["signed-by"] = signing['dest']

        tmp = []

        for k,v in attr.items():
            tmp.append("{}={}".format(k,v))

        if tmp:
            tmp = '[' + ' '.join(tmp) + ']'
        else:
            tmp = ''

        sl = my_subcfg['source_line'].format(
           attributes=tmp, **cvars
        )

        c = my_subcfg['config']
        c['repo'] = sl

        setdefault_none(c, 'state', 'present')

        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        pcfg['_export_lst'].append(my_subcfg)

        return my_subcfg



class SourcesInstSigningNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['signing']

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        super(SourcesInstSigningNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return 'src_url'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        dest = my_subcfg.get('dest', None)

        if not dest:
            dest = cfgpath_abs[-2] + '.asc'

        dest = pathlib.PurePath(dest)

        if not dest.is_absolute():
            dest = pathlib.PurePath('/etc/apt/keyrings') / dest

        dest = str(dest)
        my_subcfg['dest'] = dest

        c = my_subcfg['config']
        c['url'] = my_subcfg['src_url']
        c['dest'] = dest

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
        return 'smabot_base_custom_apt_sources_args'

    @property
    def supports_merging(self):
        return False

