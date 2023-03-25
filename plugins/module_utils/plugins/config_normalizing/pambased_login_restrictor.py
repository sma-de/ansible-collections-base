
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import abc

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, NormalizerBase, NormalizerNamed, DefaultSetterConstant

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.pam_rules_base import \
  PamRulesNormer, order_pamrules_list

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, merge_dicts, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class PamBasedLoginRestrictorNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'enabled', DefaultSetterConstant(True)
        )

        ##self._add_defaultsetter(kwargs,
        ##   'local_users', DefaultSetterConstant(True)
        ##)

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          LocalUsersNormer(pluginref),
          PamRulesNormerExt(pluginref),
        ]

        super(PamBasedLoginRestrictorNormer, self).__init__(pluginref, *args, **kwargs)


    @abc.abstractmethod
    def _get_specific_pamrules(self, cfg, my_subcfg, cfgpath_abs):
        pass


    def rulecnt(self, cfg, my_subcfg, cfgpath_abs):
        return len(self._get_specific_pamrules(cfg, my_subcfg, cfgpath_abs))


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        enabled = my_subcfg['enabled']
        local_users = my_subcfg['local_users']

        ## handle pam config files
        file_cfgs_present = []
        file_cfgs_absent = []

        for x in ['allow', 'deny']:
            tmp = my_subcfg.get(x).get('_export')

            if not tmp:
                continue

            if enabled:
                file_cfgs_present += tmp
            else:
                for x in tmp:
                    file_cfgs_absent.append(
                      {'state': 'absent', 'path': x['dest']}
                    )

        ## handle pam rules
        pamfile = my_subcfg['pam_rules']['pamfile']
        prerule = my_subcfg['pam_rules']['prerule']['config']

        rules = []

        if local_users:
            nxt_rule = {
              'type': 'auth',

              'control': '[success={} default=ignore]'.format(
                 self.rulecnt(cfg, my_subcfg, cfgpath_abs)
              ),

              'module_path': 'pam_localuser.so',
              'state': 'after',
            }

            if local_users['enabled']:
                nxt_rule['state'] = 'absent'

            rules.append(nxt_rule)

        rules += self._get_specific_pamrules(cfg, my_subcfg, cfgpath_abs)

        rules = order_pamrules_list(rules, pamfile,
          pre_rule=prerule, enabled=enabled
        )

        my_subcfg['_exports'] = {
          'pam_cfgfiles_present': file_cfgs_present,
          'pam_cfgfiles_absent': file_cfgs_absent,
          'pam_rules': rules,
        }

        return my_subcfg


class LocalUsersNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'enabled', DefaultSetterConstant(True)
        )

        super(LocalUsersNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['local_users']

    @property
    def simpleform_key(self):
        return 'enabled'


class PamRulesNormerExt(PamRulesNormer):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          PamPreRuleNormer(pluginref),
          PamPostRuleNormer(pluginref),
        ]

        super(PamRulesNormerExt, self).__init__(
           pluginref, *args, **kwargs
        )


class PamPreRuleNormer(NormalizerBase):

    DISTRO_PAM_PRERULE_OVERWRITES = {
      ##"distro name as returned by ansible_distribution": "pam-file-name"
      ## TODO: fill when suporting another distro
    }

    @property
    def config_path(self):
        return ['prerule']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        prerule_defaults = self.DISTRO_PAM_PRERULE_OVERWRITES.get(
           self.pluginref.get_ansible_var('ansible_distribution'),

           # current default is based on modern ubuntu
           {
             'type': 'auth',
             'control': 'requisite',
             'module_path': 'pam_deny.so',
           },
        )

        rcfg = setdefault_none(my_subcfg, 'config', {})

        setdefault_none(rcfg,        'type', prerule_defaults['type'])
        setdefault_none(rcfg,     'control', prerule_defaults['control'])
        setdefault_none(rcfg, 'module_path', prerule_defaults['module_path'])

        return my_subcfg


class PamPostRuleNormer(NormalizerBase):

    DISTRO_PAM_RULE_OVERWRITES = {
      ##"distro name as returned by ansible_distribution": "pam-file-name"
      ## TODO: fill when suporting another distro
    }

    @property
    def config_path(self):
        return ['postrule']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        rule_defaults = self.DISTRO_PAM_RULE_OVERWRITES.get(
           self.pluginref.get_ansible_var('ansible_distribution'),

           # current default is based on modern ubuntu
           {
                    'type': 'auth',
                 'control': 'required',
             'module_path': 'pam_permit.so',
           },
        )

        rcfg = setdefault_none(my_subcfg, 'config', {})

        setdefault_none(rcfg,        'type', rule_defaults['type'])
        setdefault_none(rcfg,     'control', rule_defaults['control'])
        setdefault_none(rcfg, 'module_path', rule_defaults['module_path'])

        return my_subcfg


class AllowDenyItemBaseNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, item_type=None, **kwargs):
        self.item_type = item_type

        super(AllowDenyItemBaseNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return [self.item_type + 's', SUBDICT_METAKEY_ANY]


class AllowDenyBaseNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          self.item_class(pluginref, item_type='user'),
          self.item_class(pluginref, item_type='group'),
        ]

        super(AllowDenyBaseNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    @abc.abstractmethod
    def item_class(self):
        pass

