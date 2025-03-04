
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import copy
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

        if my_subcfg['apt_file']:
            c['filename'] = my_subcfg['apt_file']

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

        self._add_defaultsetter(kwargs,
          'de_armor', DefaultSetterConstant(False)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SourcesInstSignFingerPrintsNormer(pluginref),
        ]

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
        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        src_url = my_subcfg.get('src_url', None)
        fprints = my_subcfg['fingerprints']['fingerprints']

        dest = my_subcfg['dest']

        if fprints:
            dest = dest.split('.')

            ##
            ## note: file ending is very important here and magic!
            ##   if you have a keyring in gpg keybox format which
            ##   you will always have when importing keys from
            ##   fingerprints the filename must end with '.gpg'
            ##   or it will not be handled correctly by apt and
            ##   you will get "NO_PUBKEY" errors although the
            ##   file contains the needed keys!!!
            ##
            if dest[-1] != 'gpg':
                if len(dest) > 1:
                    dest[-1] = 'gpg'
                else:
                    dest.append('gpg')

            dest = '.'.join(dest)
            my_subcfg['dest'] = dest

        c = my_subcfg['config']
        c['dest'] = dest

        if src_url:
            c['url'] = src_url

        return my_subcfg



class SourcesInstSignFingerPrintsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          FingerPrintConfigDefaultsNormer(pluginref),
          SourcesInstSignFingerPrintInstNormer(pluginref),
        ]

        super(SourcesInstSignFingerPrintsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['fingerprints']

    @property
    def simpleform_key(self):
        return '_fingerprint'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        sf_print = my_subcfg.pop(self.simpleform_key, None)

        if sf_print:
            sm = setdefault_none(my_subcfg, 'fingerprints', {})
            sm[sf_print] = None

        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        cfg_defs = my_subcfg['config_defaults']

        exp_cfgs = []
        exp_cfg_def = {
          'key_ids': [],
          'config': cfg_defs,
        }

        for k, v in my_subcfg['fingerprints'].items():
            vc = v['config']

            if not vc:
                ## no custom settings for this fp, uses default config
                exp_cfg_def['key_ids'].append(v['fingerprint'])
                continue

            ## this fingerprint has custom export settings,
            ## make it its own command
            vc = merge_dicts(copy.deepcopy(cfg_defs), vc)

            exp_cfgs.append({
              'key_ids': [v['fingerprint']],
              'config': vc,
            })

        if exp_cfg_def['key_ids']:
            exp_cfgs.append(exp_cfg_def)

        if exp_cfgs:
            my_subcfg['_export_cfgs'] = exp_cfgs

        return my_subcfg



class FingerPrintConfigDefaultsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'keyserver', DefaultSetterConstant('hkp://keyserver.ubuntu.com:80')
        )

        super(FingerPrintConfigDefaultsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['config_defaults']



class SourcesInstSignFingerPrintInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        super(SourcesInstSignFingerPrintInstNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['fingerprints', SUBDICT_METAKEY_ANY]

    @property
    def name_key(self):
        return 'fingerprint'



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

