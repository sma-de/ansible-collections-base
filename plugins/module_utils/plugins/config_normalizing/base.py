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

from ansible.errors import AnsibleOptionsError##, AnsibleError, AnsibleModuleError, AnsibleAssertionError, AnsibleParserError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types
####from ansible.module_utils.common._collections_compat import MutableMapping
##from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import merge_dicts, get_subdict, get_subdicts, set_subdict, get_partdict
from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction##, MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert
from ansible_collections.smabot.base.plugins.action import merge_vars



class DefaultSetterBase(abc.ABC):

    def __init__(self, normalizer_fn=None, default_on_none=True):
        self.normalizer_fn = normalizer_fn
        self.default_on_none = default_on_none

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


class DefaultSetterAnsVar(DefaultSetterBase):

    def __init__(self, varname, pluginref, **kwargs):
        super(DefaultSetterAnsVar, self).__init__(**kwargs)
        self.ansvar_name = varname
        self.pluginref = pluginref

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        return self.pluginref.get_ansible_var(self.ansvar_name)


class DefaultSetterHostName(DefaultSetterAnsVar):

    def __init__(self, *args, **kwargs):
        super(DefaultSetterHostName, self).__init__(
            'inventory_hostname', *args, **kwargs
        )


class DefaultSetterMappinKey(DefaultSetterBase):

    def __init__(self, level=None, **kwargs):
        super(DefaultSetterMappinKey, self).__init__(**kwargs)

        if level is None:
            level = -1

        self.level = level

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        return cfgpath_abs[self.level]


class DefaultSetterOtherKey(DefaultSetterBase):

    def __init__(self, refkey, **kwargs):
        super(DefaultSetterOtherKey, self).__init__(**kwargs)
        self.refkey = refkey

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        ## note: obviously one must take care that refkey is 
        ##   set before key to default
        return my_subcfg[self.refkey]


class DefaultSetterFmtStrCfg(DefaultSetterBase):

    def __init__(self, fmtstr, **kwargs):
        super(DefaultSetterFmtStrCfg, self).__init__(**kwargs)
        self.fmtstr = fmtstr

    def _formatting_str(self, cfg):
        return self.fmtstr.format(**cfg)

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        return self._formatting_str(cfg)


class DefaultSetterFmtStrSubCfg(DefaultSetterFmtStrCfg):

    def __init__(self, *args, **kwargs):
        super(DefaultSetterFmtStrSubCfg, self).__init__(*args, **kwargs)

    def _get_defval(self, cfg, my_subcfg, cfgpath_abs):
        return self._formatting_str(my_subcfg)



class NormalizerBase(abc.ABC):

    def __init__(self, pluginref, default_setters=None, sub_normalizers=None):
        self.pluginref = pluginref
        self.sub_normalizers = sub_normalizers
        self.default_setters = default_setters or {}

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
            if k in my_subcfg: 
                ## normally only default when key is not set 
                ## yet, independend of any value
                if not v.default_on_none: continue

                ## if explicitly mandated, also default when key 
                ## is set but value is None
                if my_subcfg[k] is not None: continue

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

        display.vvv("Normalize config path: {}".format(cfgpath_abs))

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

    def __init__(self, *args, mapkey_lvl=None, **kwargs):
        self._add_defaultsetter(kwargs, 
           self.name_key, DefaultSetterMappinKey(level=mapkey_lvl)
        )

        super(NormalizerNamed, self).__init__(*args, **kwargs)

    @property
    def name_key(self):
        return 'name'



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
          'invars': [{ 
              'name': self.get_taskparam('config_ansvar'), 'optional': False
          }],
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

        ## do var merging / inheriting and defaulting, 
        ##   do this always before the normalisation
        if mv and ma:
            if isinstance(mv, collections.abc.Mapping):
                merge_dicts(ma, mv)

            tmp = []

            for iv in ma['invars']:
                if not isinstance(iv, collections.abc.Mapping):
                    ## assume simple name string

                    ## note: we assume here that any extra vars to merge 
                    ##   are optional on default, some kind of generic 
                    ##   defaults which may or may not be provided, if one 
                    ##   wants to define an extra var as mandatory, it 
                    ##   must be given as normalized dict form
                    iv = { 'name': iv, 'optional': True }

                tmp.append(iv)
                
            ma['invars'] = tmp

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


class ConfigNormalizerBaseMerger(ConfigNormalizerBase):

    def __init__(self, *args, 
        default_merge_vars=None, extra_merge_vars_ans=None, **kwargs
    ):
        super(ConfigNormalizerBaseMerger, self).__init__(*args, **kwargs)

        self._extra_merge_vars_ans = extra_merge_vars_ans or []
        self._default_merge_vars = default_merge_vars or []


    @property
    def merge_args(self):
        tmp = super(ConfigNormalizerBaseMerger, self).merge_args

        tmp['invars'] \
          += self.get_taskparam('extra_merge_vars') \
          + self._default_merge_vars

        return tmp


    @property
    def argspec(self):
        tmp = super(ConfigNormalizerBaseMerger, self).argspec

        tmp.update({
          'extra_merge_vars': {
             'type': [[]],  ## this means type is a list whith no tpe restrictions for list elements
             'defaulting': {
                'ansvar': self._extra_merge_vars_ans,
                'fallback': [],
             },
          }
        })

        return tmp

