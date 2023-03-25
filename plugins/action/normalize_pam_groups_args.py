
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy
import re

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, NormalizerBase, NormalizerNamed, DefaultSetterConstant

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.pam_rules_base import \
  PamRulesNormer, order_pamrules_list

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, merge_dicts, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          CfgEntriesNormer(pluginref),
          PamRulesNormerExt(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)



class CfgEntriesNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          CfgEntryInstNormer(pluginref),
        ]

        super(CfgEntriesNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['config_entries']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        explst = []

        for k,v in my_subcfg['entries'].items():
            nv = copy.deepcopy(v)
            nv['groups'] = ' '.join(nv['groups'])

            explst.append(nv)

        my_subcfg['_explist'] = explst
        return my_subcfg


class CfgEntryInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        super(CfgEntryInstNormer, self).__init__(pluginref, *args, **kwargs)

        self.default_setters['services'] = DefaultSetterConstant('*')
        self.default_setters['ttys'] = DefaultSetterConstant('*')
        self.default_setters['users'] = DefaultSetterConstant('*')
        self.default_setters['times'] = DefaultSetterConstant('Al0000-2400')
        self.default_setters['comment'] = DefaultSetterConstant('')


    @property
    def config_path(self):
        return ['entries', SUBDICT_METAKEY_ANY]

    @property
    def name_key(self):
        return 'groups'


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        g = my_subcfg['groups']

        ## normalize groups to list
        if isinstance(g, string_types):
            g = re.sub(r'\s*,s\*', ' ', g)
            g = re.split(r'\s+', g)

        my_subcfg['groups'] = g
        return my_subcfg


class PamRulesNormerExt(PamRulesNormer):

    ## note: in principle this can have a pre and post rule configured, but we dont normalize them atm, so noop here
    def __init__(self, pluginref, *args, **kwargs):
        ##subnorms = kwargs.setdefault('sub_normalizers', [])
        ##subnorms += [
        ##  PamPreRuleNormer(pluginref),
        ##  PamPostRuleNormer(pluginref),
        ##]

        super(PamRulesNormerExt, self).__init__(
           pluginref, *args, **kwargs
        )


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        super(PamRulesNormerExt, self)._handle_specifics_presub(
           cfg, my_subcfg, cfgpath_abs
        )

        grc = setdefault_none(my_subcfg, 'grouprule', {})
        grc = setdefault_none(grc, 'config', {})

        setdefault_none(grc, 'type', 'auth')
        setdefault_none(grc, 'control', 'optional')
        setdefault_none(grc, 'module_path', 'pam_group.so')

        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        prerule = my_subcfg.get('prerule', {}).get('config', None)
        postrule = my_subcfg.get('postrule', {}).get('config', None)

        rules = []
        rules.append(my_subcfg['grouprule']['config'])

        rules = order_pamrules_list(rules, my_subcfg['pamfile'],
          pre_rule=prerule, post_rule=postrule
        )

        my_subcfg['_exportlst'] = rules
        return my_subcfg


class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self),
            *args,
##            default_merge_vars=['smabot_win_inet_basics_args_defaults'],
##            extra_merge_vars_ans=['extra_smabot_win_inet_basics_args_config_maps'],
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_base_pam_groups_args'

