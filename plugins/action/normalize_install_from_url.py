
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



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          DownloadNormer(pluginref),
          DestNormer(pluginref),
          PreExistsTestNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)


class PreExistsTestNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(PreExistsTestNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['prexist_test']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)

        unpack = pcfg['destination']['unpacking']
        testcfg = {}

        destpath = pathlib.Path(pcfg['destination']['path'])

        if unpack['enabled']:
            csum = unpack.get('checksum', None)

            if csum:
                testcfg['file'] = str(destpath / csum['file'])
                testcfg['checksum'] = csum['checksum']

        else:
            # no unpacking involved, meaning destpath is equivalent
            # to our download artifact when it is installed
            csum = pcfg['download']['config'].get('checksum', None)

            if csum:
                testcfg['file'] = str(destpath)
                testcfg['checksum'] = csum

        my_subcfg['enabled'] = False

        if testcfg:
            my_subcfg['enabled'] = True

            tmp = merge_dicts(testcfg,
              setdefault_none(my_subcfg, 'config', {})
            )

            tmp['optional'] = True

            my_subcfg['config'] = tmp

        return my_subcfg



class DownloadNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          DownloadConfigNormer(pluginref),
        ]

        super(DownloadNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['download']

    @property
    def simpleform_key(self):
        return 'url'



class DownloadConfigNormer(NormalizerBase):

##    def __init__(self, pluginref, *args, **kwargs):
##        super(SudoMappingsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['config']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        my_subcfg['url'] = pcfg['url']
        return my_subcfg



class DestNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          DestUnpackNormer(pluginref),
          DestConfigNormer(pluginref),
        ]

        super(DestNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['destination']

    @property
    def simpleform_key(self):
        return 'path'

##    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
##        path = my_subcfg['config']['path']
##
##        # if path is marked as dir (ends with slash) and unpacking is
##        # unset, so we are dealing with a single file here, make sure
##        # final target path copies into dir, not uses dir path as
##        # final file path
##        if not my_subcfg['unpacking']['enabled'] and path[-1] == '/':
##            my_subcfg['path'] = path + '.'
##
##        return my_subcfg



class DestConfigNormer(NormalizerBase):

##    def __init__(self, pluginref, *args, **kwargs):
##        super(SudoMappingsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['config']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        state = 'file'

        if pcfg['unpacking']['enabled']:
            state = 'directory'

        my_subcfg['path'] = pcfg['path']
        my_subcfg['state'] = state
        return my_subcfg



class DestUnpackNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['unpacking']

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          DestUnpackConfigNormer(pluginref),
          UnpackFlatteningNormer(pluginref),
          (UnpackChecksumNormer, True),
        ]

        super(DestUnpackNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return '_simple_unpack_key'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        tmp = my_subcfg.pop(self.simpleform_key, False)
        empty = not my_subcfg
        my_subcfg['enabled'] = tmp or not empty

        return my_subcfg



class UnpackChecksumNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['checksum']

##    def __init__(self, pluginref, *args, **kwargs):
##        super(UnpackChecksumNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        my_subcfg['file'] = str(
          pathlib.Path(pcfg['path']) / my_subcfg['file']
        )

        return my_subcfg



class DestUnpackConfigNormer(NormalizerBase):

##    def __init__(self, pluginref, *args, **kwargs):
##        super(DestUnpackConfigNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['config']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        my_subcfg['dest'] = pcfg['path']
        my_subcfg['remote_src'] = True 
        return my_subcfg



class UnpackFlatteningNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          UnpackFlattenConfigNormer(pluginref),
        ]

        super(UnpackFlatteningNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['flatten']

    @property
    def simpleform_key(self):
        return 'level'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        tmp = my_subcfg.pop(self.simpleform_key, False)
        empty = not my_subcfg

        my_subcfg[self.simpleform_key] = tmp
        my_subcfg['enabled'] = tmp or not empty
        return my_subcfg



class UnpackFlattenConfigNormer(NormalizerBase):

##    def __init__(self, pluginref, *args, **kwargs):
##        super(DestUnpackConfigNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['config']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        my_subcfg['level'] = pcfg['level']

        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        my_subcfg['src'] = pcfg['config']['dest']
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
        return 'smabot_base_setup_install_from_url_args'

    @property
    def supports_merging(self):
        return False

