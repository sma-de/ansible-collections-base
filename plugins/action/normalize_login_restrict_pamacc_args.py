
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy
import os

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, NormalizerBase, NormalizerNamed, DefaultSetterConstant

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.pambased_login_restrictor import \
  PamBasedLoginRestrictorNormer, AllowDenyBaseNormer, AllowDenyItemBaseNormer

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, merge_dicts, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class ConfigRootNormalizer(PamBasedLoginRestrictorNormer):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          AllowNormer(pluginref),
          DenyNormer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


    @property
    def postrule_pamlist_user_rulecnt(self):
        # note: as we use pamlist based role for user access
        #   control atm we must additionaly consider the
        #   rules created by that role
        #
        # TODO: would obviously be better to source this number directly from subrole
        return 2


    def rulecnt(self, cfg, my_subcfg, cfgpath_abs):
        return super().rulecnt(cfg, my_subcfg, cfgpath_abs)\
             + self.postrule_pamlist_user_rulecnt


    def _get_specific_pamrules(self, cfg, my_subcfg, cfgpath_abs):
        postrule = my_subcfg['pam_rules']['postrule']['config']

        return [{
          'type': 'auth',
          'control': 'required',
          'module_path': 'pam_access.so',

          ##
          ## note: as long as we use another role (pamlist role) to
          ##   handle user name based access we need use a 2nd
          ##   "lower anchor" rule for positioning this rule to
          ##   avoid reruns of the role to additional add copies
          ##   of the pam rule here (being not idempotent)
          ##
          'state': 'before',
          'refrule': postrule,
        }]


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg = super(ConfigRootNormalizer, self)._handle_specifics_postsub(
          cfg, my_subcfg, cfgpath_abs
        )

        ## copy for other pam role is basically identical, but
        ## obviously without our exports and also without groups
        ## which are handled by pam-access
        tmp = copy.deepcopy(my_subcfg)

        tmp.pop('_exports')

        for x in ['allow', 'deny']:
            t2 = tmp.get(x, None)

            if not t2:
                continue

            t2.pop('groups', None)

            if x == 'allow':
                # make sure that group base access check is skipped
                # if user is already explicitly allowed by user
                # name access list
                t2['pam_rule'] = {
                  'config': {
                    'control': '[success=1 default=ignore]',
                  }
                }

        # as we handle local-users already in this role we always disable
        # any special handling in called subrole
        tmp['local_users'] = {
          'disabled': True,
        }

        # we do pamlist based user access control before pamaccess
        # based group based acccess because we want to be able
        # to explicitly blacklist specific users for a otherwise
        # generally allowed group
        prl = tmp.setdefault('pam_rules', {})
        t2 = my_subcfg['_exports']['pam_rules'][0]

        if t2['state'] == 'absent':
            t2 = {
              'type': t2['type'],
              'control': t2['control'],
              'module_path': t2['module_path'],
            }

        else:
            t2 = {
              'type': t2['new_type'],
              'control': t2['new_control'],
              'module_path': t2['new_module_path'],
            }

        prl['prerule'] = { 'config': t2 }

        my_subcfg['_exports']['pam_lists_users'] = tmp
        return my_subcfg


class AllowDenyItemNormer(AllowDenyItemBaseNormer):

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        group = self.item_type == 'group'

        export_cfg = []

        dom = my_subcfg.get('domain', None)
        tmp = my_subcfg['name']

        if dom:
            # note: at least for ad domains domain\name is the only variant working (for us)
            # note.2: does atm only work for groups, not users
            tmp = dom + '\\' + tmp

        if group:
            # seems not perse technically necessary but recommended to
            # put groups into brackets to distinguish them from users
            tmp = '(' + tmp + ')'

        export_cfg.append(tmp)

        # TODO: allow customisation of pam-acc source field??
        export_cfg.append('ALL')

        my_subcfg['_export'] = export_cfg
        return my_subcfg


class AllowDenySubBaseNormer(AllowDenyBaseNormer):

    @property
    def item_class(self):
        return AllowDenyItemNormer

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        ##pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        ##enabled = pcfg['enabled']

        allow = self.config_path[-1] == 'allow'

        # TODO: allow custom overwrites here??? 
        destdir = '/etc/security/access.d'
        destfile_pattern = '20_ansible_smabot_allow_{}'

        if not allow:
            # note: as first match wins it is absolutely
            #   important that deny file is parsed before allow file!
            destfile_pattern = '10_ansible_smabot_deny_{}'

        export_filecfgs = []

        #
        # note: we actually dont handle users with pam access
        #   atm directly because we dont get it to work for
        #   all cases (e.g.: ad domain users), instead we
        #   forward to pam list for users
        #
        ##for x in ['users', 'groups']:
        for x in ['groups']:
            items = my_subcfg.get(x, None)

            if not items:
                continue

            export_content = [
              "",
              "##",
              "## file autogenerated by ansible, do not change it manually!",
              "##",
              "",
            ]

            pfx = '+'

            if not allow:
                pfx = '-'

            for ik, iv in items.items():
                export_content.append(':'.join([pfx] + iv['_export']))

            if allow:
                export_content.append("")
                export_content.append("# the following last line is fundamentally important,")
                export_content.append("# without it any user not matched in this file would")
                export_content.append("# not be restricted in any way making the whole")
                export_content.append("# allowance stuff above pointless")
                export_content.append("-:ALL:ALL")

            export_content.append("")

            # TODO: optionally allow to overwrite file properties??
            export_cfg = { 'type': x[:-1], 'config': {
              'content': '\n'.join(export_content),
              'dest': os.path.normpath(destdir + '/' + destfile_pattern.format(x) + '.conf'),

              # note: these files dont contain any real secrets, but
              #   as changing them controls who and who cannot login
              #   to a system it chould obviously only be writeable by root
              'owner': 'root',
              'group': 'root',
              'mode':  '0644',
            }}

            export_filecfgs.append(export_cfg)

        my_subcfg['_export'] = export_filecfgs
        return my_subcfg


class AllowNormer(AllowDenySubBaseNormer):

    @property
    def config_path(self):
        return ['allow']


class DenyNormer(AllowDenySubBaseNormer):

    @property
    def config_path(self):
        return ['deny']


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
        return 'smabot_base_login_restrict_pamacc_args'

