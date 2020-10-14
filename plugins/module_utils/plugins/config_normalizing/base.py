#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import collections
import uuid

##from ansible.errors import AnsibleOptionsError##, AnsibleError, AnsibleModuleError, AnsibleAssertionError, AnsibleParserError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types
####from ansible.module_utils.common._collections_compat import MutableMapping
##from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import merge_dicts, get_subdict, get_subdicts, set_subdict, get_partdict
from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction##, MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert
from ansible_collections.smabot.base.plugins.action import merge_vars



class DefaultSetterBase(abc.ABC):

    def __init__(self, normalizer_fn=None):
        self.normalizer_fn = normalizer_fn

    def __call__(self, *args, **kwargs):
        tmp = self._get_defval(*args, **kwargs)

        normfn = self.normalizer_fn

        if normfn:
            tmp = normfn(tmp) 

        return tmp

    @abc.abstractmethod
    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        pass


class DefaultSetterConstant(DefaultSetterBase):

    def __init__(self, value, **kwargs):
        super(DefaultSetterConstant, self).__init__(**kwargs)
        self.my_value = value

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        return self.my_value


class DefaultSetterMappinKey(DefaultSetterBase):

    def __init__(self, **kwargs):
        super(DefaultSetterMappinKey, self).__init__(**kwargs)

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        return cfgpath_abs[-1]


class NormalizerBase(abc.ABC):

    def __init__(self, pluginref, default_setters=None, sub_normalizers=None):
        self.pluginref = pluginref
        self.sub_normalizers = sub_normalizers
        self.default_setters = default_setters

    @property
    def config_path(self):
        ## the "path" / config key chain this normalizer is responsible for
        None

    @property
    def simpleform_key(self):
        return None

    def _add_defaultsetter(self, kwargs, defkey, defval):
        defsets = kwargs.setdefault('default_setters', {})
        defsets[defkey] = defval
        return kwargs

    def get_parentcfg(self, cfg, cfgpath_abs, level=1):
        return get_subdict(cfg, cfgpath_abs[: -level])

    def copy_from_parent(self, cfg, cfgpath_abs, copy_keys, **kwargs):
        pacfg = self.get_parentcfg(cfg, cfgpath_abs, **kwargs)
        return get_partdict(pacfg, *copy_keys)


    def __call__(self, *args, **kwargs):
        return self.normalize_config(*args, **kwargs)


    def _handle_default_setters(self, cfg, my_subcfg, cfgpath_abs):
        defsets = self.default_setters

        if not defsets:
            return my_subcfg

        for (k, v) in iteritems(defsets):

            ## as the name implies default_setters are only active 
            ## when key is not set explicitly
            if k in my_subcfg: continue

            my_subcfg[k] = v(cfg, my_subcfg, cfgpath_abs)
        
        return my_subcfg


    def _handle_sub_normalizers(self, cfg, my_subcfg, cfgpath_abs):
        subnorms = self.sub_normalizers

        if not subnorms:
            return my_subcfg

        for sn in subnorms:
            sn(my_subcfg, cfg, cfgpath_abs)

        return my_subcfg


    ## can be overwritten in sub classes
    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        return my_subcfg

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        return my_subcfg

    def _simple_to_dict(self, cfg, my_subcfg, cfgpath_abs):
        if isinstance(my_subcfg, collections.abc.Mapping):
            return my_subcfg

        sk = self.simpleform_key

        if not sk:
            raise AnsibleOptionsError(
               "As no simpleform_key is specified sub-config for"\
               " keypath '{}' must be a dictionary".format(
                   '.'.join(cfgpath_abs)
               )
            )

        my_subcfg = { sk: my_subcfg }
        return my_subcfg


    def normalize_config(self, config, global_cfg=None, cfgpath_abs=None):
        cfgpath = self.config_path
        global_cfg = global_cfg or config
        cfgpath_abs = cfgpath_abs or []

        ## note: we cannot iterate "inplace" here, as we also modify 
        ##   the dict inside the loop, we solve this by tmp saving 
        ##   iterator first as list
        sub_dicts = list(get_subdicts(config, cfgpath, 
            default_empty=True, allow_nondict_leaves=True
        ))

        for (subcfg, subpath) in sub_dicts:

            sp_abs = cfgpath_abs[:]

            if subpath:
                sp_abs += subpath

            subcfg = self._simple_to_dict(global_cfg, subcfg, sp_abs)

            if subpath:
                set_subdict(config, subpath, subcfg)

            subcfg = self._handle_default_setters(global_cfg, subcfg, sp_abs)
            subcfg = self._handle_specifics_presub(global_cfg, subcfg, sp_abs)
            subcfg = self._handle_sub_normalizers(global_cfg, subcfg, sp_abs)
            subcfg = self._handle_specifics_postsub(global_cfg, subcfg, sp_abs)

            if subpath:
                set_subdict(config, subpath, subcfg)

        return config


class NormalizerNamed(NormalizerBase):

    def __init__(self, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           self.name_key, DefaultSetterMappinKey()
        )

        super(NormalizerNamed, self).__init__(*args, **kwargs)

    @property
    @abc.abstractmethod
    def name_key(self):
        pass



class ConfigNormalizerBase(BaseAction):

    def __init__(self, normalizer, *args, **kwargs):
        self.normalizer = normalizer
        super(ConfigNormalizerBase, self).__init__(*args, **kwargs)


    @property
    @abc.abstractmethod
    def my_ansvar(self):
        pass

    @property
    def supports_merging(self):
        return True

    @property
    def merge_args(self):
        return {
          'invars': [self.get_taskparam('config_ansvar')],
        }


    @property
    def argspec(self):
        tmp = super(ConfigNormalizerBase, self).argspec

        tmp.update({
          'config': ([collections.abc.Mapping], {}),
          'config_ansvar': (list(string_types), self.my_ansvar),
        })

        if self.supports_merging:
            tmp['merge_vars'] = ([bool, collections.abc.Mapping], True)

        return tmp


    def _handle_merging(self, cfg):
        if not self.supports_merging:
            return cfg

        ma = self.merge_args
        mv = self.get_taskparam('merge_vars')

        if mv and ma:
            ## do var merging / inheriting and defaulting, 
            ##   do this always before the normalisation
            if isinstance(mv, collections.abc.Mapping):
                merge_dicts(ma, mv)

            ma['result_var'] = merge_vars.MAGIG_KEY_TOPLVL
            ma['update_facts'] = False

            ans_vspace = None

            if cfg:
                ## caller explicitly provided a cfg as param, use 
                ##   it instead of getting the config from specified 
                ##   cfgvars, as var merging always operates on ansvars 
                ##   not directly on values, we will create a tmp ansvar 
                ##   for our cfg, use uuid as name to avoid clashes
                tmp = str(uuid.uuid4())
                ma['invars'][0] = tmp
                ans_vspace[tmp] = cfg

            cfg = self.run_other_action_plugin(merge_vars.ActionModule, 
              ans_varspace=ans_vspace, plugin_args=ma
            )

        return cfg['merged_var']


    def run_specific(self, result):
        cfg = self.get_taskparam('config')
        cfgvar = self.get_taskparam('config_ansvar')

        if not cfgvar and not cfg:
            raise AnsibleOptionsError(
              "if param 'config_ansvar' is unset, param 'config' must be set"
            )

        cfg = self._handle_merging(cfg)

        if not cfg:
            ## no merging and no explicit cfg param, obtain 
            ##   cfg from defined cfgvar
            cfg = self.get_ansible_var(cfgvar)

        ## do domain specific normalization
        ansible_assert(self.normalizer, 
          "bad normalizer module: normalizer class hierarchy undefined"
        )

        cfg = self.normalizer(cfg)

        ## return merged "normaly" a custom value of result dict
        result['normalized'] = cfg

        ## update ansible var directly
        if cfgvar:
            self.set_ansible_vars(**{cfgvar: cfg})

        return result

