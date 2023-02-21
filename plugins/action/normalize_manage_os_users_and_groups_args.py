
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, NormalizerBase, NormalizerNamed, DefaultSetterConstant

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, merge_dicts, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          StandardGroupInstNormer(pluginref),
          UserPersonalGroupsNormerPre(pluginref),
          UserInstNormer(pluginref),
          UserPersonalGroupInstNormerPost(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class UserPersonalGroupsNormerPre(NormalizerBase):

    @property
    def config_path(self):
        return ['groups', 'user_personal_groups']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ansible_assert(not my_subcfg,
           "invalid configuration: dont add any group config directly"\
           " to 'groups.user_personal_groups', use the 'personal_group'"\
           " subkey of the user section instead:\n{}".format(my_subcfg)
        )

        return my_subcfg


class GroupInstNormerBase(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'force_num_ids', DefaultSetterConstant(False)
        )

        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        super(GroupInstNormerBase, self).__init__(
           pluginref, *args, **kwargs
        )

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## handle own config
        c = my_subcfg['config']

        c['name'] = my_subcfg['name']
        setdefault_none(c, 'state', 'present')
        return my_subcfg


class StandardGroupInstNormer(GroupInstNormerBase):

    @property
    def config_path(self):
        return ['groups', 'groups', SUBDICT_METAKEY_ANY]


class UserPersonalGroupInstNormerPost(GroupInstNormerBase):

    @property
    def config_path(self):
        return ['groups', 'user_personal_groups', SUBDICT_METAKEY_ANY]

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        super(UserPersonalGroupInstNormerPost, self)._handle_specifics_presub(
          cfg, my_subcfg, cfgpath_abs
        )

        n = my_subcfg['name']

        pu = my_subcfg.get('personal_user', None)

        ansible_assert(pu,
           "invalid configuration for personal user group '{}':"\
           " No personal user attached".format(n)
        )

        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=3)

        all_users = pcfg['users']['users']
        uc = all_users.get(pu['name'], None)

        ansible_assert(uc,
           "invalid configuration for personal user group '{}':"\
           " attached personal user with name '{}' could not be"\
           " found inside user config section:\n{}".format(
               n, pu['name'], all_users
           )
        )

        return my_subcfg


class UserInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'force_num_ids', DefaultSetterConstant(False)
        )

        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'personal_group', DefaultSetterConstant({})
        )

        super(UserInstNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['users', 'users', SUBDICT_METAKEY_ANY]

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## handle own config
        c = my_subcfg['config']

        c['name'] = my_subcfg['name']
        setdefault_none(c, 'state', 'present')

        ## handle personal group
        pg = my_subcfg['personal_group']
        pg_name = setdefault_none(pg, 'name', my_subcfg['name'])

        setdefault_none(pg, 'force_num_ids', my_subcfg['force_num_ids'])

        uid = c.get('uid', None)

        if uid:
            setdefault_none(pg, 'gid', uid)

        tmp = copy.deepcopy(my_subcfg)
        tmp.pop('personal_group')

        pg['personal_user'] = tmp

        # add pg to "normal" groups so it can be normalized in standard group way
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=3)
        tmp = pcfg['groups']['user_personal_groups']

        t2 = tmp.get(pg_name, None)
        ansible_assert(not t2,
           "invalid configuration for user '{}': a personal user group"\
           " config section with name '{}' exists already:\n{}".format(
              my_subcfg['name'], pg_name, t2
           )
        )

        tmp[pg_name] = pg
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
        return 'smabot_base_manage_os_users_and_groups_args'

