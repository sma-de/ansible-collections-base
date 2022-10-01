
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

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


    def _get_specific_pamrules(self, cfg, my_subcfg, cfgpath_abs):
        defargs = {
          'type': 'auth',
          'module_path': 'pam_listfile.so',
        }

        res_rules = []

        # note: iteration order matters here, we need deny rules before allow rules
        for x in ['deny', 'allow']:

            yc = 1

            ##itemtypes = ['users', 'groups']
            itemtypes = ['users']

            for y in itemtypes:

                modargs = {
                  'sense': x,
                  'item': y[:-1],
                  'onerr': 'fail',
                }

                ## on default assume deny args
                new_rule = {
                  'control': 'required',
                }

                new_rule.update(defargs)

                if x == 'allow' and yc < len(itemtypes):
                    # when one allow list test matches skip all following ones
                    new_rule['control'] = '[success=1 default=ignore]'

                tmp = next(filter(
                  lambda l: l['type'] == modargs['item'],
                  my_subcfg[x]['_export']
                ))

                modargs['file'] = tmp['config']['dest']

                tmp = []

                for k,v in modargs.items():
                    tmp.append("{}={}".format(k,v))

                new_rule['module_arguments'] = tmp
                new_rule.update(my_subcfg[x].get('pam_rule', {}).get('config', {}))

                res_rules.append(new_rule)
                yc += 1

        return res_rules


class AllowDenyItemNormer(AllowDenyItemBaseNormer):

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        group = self.item_type == 'group'
        ansible_assert(not group, "pmalistfile for groups is atm unsupported, use pam_access for them")

        dom = my_subcfg.get('domain', None)
        tmp = my_subcfg['name']

        if dom:
            tmp += '@' + dom

        my_subcfg['_export'] = tmp
        return my_subcfg


class AllowDenySubBaseNormer(AllowDenyBaseNormer):

    @property
    def item_class(self):
        return AllowDenyItemNormer

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        allow = self.config_path[-1] == 'allow'

        # TODO: allow custom overwrites here??? 
        destdir = '/etc/security/listacc.d'
        destfile_pattern = '20_ansible_smabot_allow_{}'

        if not allow:
            destfile_pattern = '10_ansible_smabot_deny_{}'

        export_filecfgs = []

        #
        # note: we dont atm handle groups for list based access as pam_access seems preferable in this situation
        #
        ##for x in ['users', 'groups']:
        for x in ['users']:
            items = my_subcfg.get(x, {})

            export_content = []

            for ik, iv in items.items():
                export_content.append(iv['_export'])

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
        return 'smabot_base_login_restrict_pamlist_args'

