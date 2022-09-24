
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
          AllPackagesNormer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


## TODO: support different install opts for packages
class AllPackagesNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SinglePackageNormer(pluginref),
        ]

        super(AllPackagesNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['packages']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        # TODO: optionally allow to force set a sepcific distro
        distro = self.pluginref.get_ansible_var('ansible_distribution').lower()
        distro_replace = True
        cur_packlist = my_subcfg.get(distro, None)

        if not cur_packlist:
            distro_replace = False
            cur_packlist = my_subcfg.get('default', {})

        ansible_assert(cur_packlist,
           "Failed to find any packages to handle, either specify"\
           " a generic package list with the key 'default' or a"\
           " distro specific overwrite list with the key '{}'".format(distro)
        )

        cur_packlist = copy.deepcopy(cur_packlist)

        # check for distro specific +/- keys
        distro_plus = my_subcfg.get(distro + '+', None)

        if distro_plus:
            ansible_assert(not distro_replace,
               "Either use distro specific +/- keys to adjust default"\
               " set distro specific or replace default list completly"\
               " with a standard distro key, but never combine these"\
               " two techniques"
            )
            
            merge_dicts(cur_packlist, distro_plus)

        distro_minus = my_subcfg.get(distro + '-', None)

        if distro_minus:
            ansible_assert(not distro_replace,
               "Either use distro specific +/- keys to adjust default"\
               " set distro specific or replace default list completly"\
               " with a standard distro key, but never combine these"\
               " two techniques"
            )

            for k in distro_minus:
                ansible_assert(k in cur_packlist,
                   "Trying to remove package '{}' distro specific"\
                   " from default list, but such a package does"\
                   " not exist on default set".format(k)
                )

                cur_packlist.pop(k)

        # split packages into state groups (TODO: generalize to specific option groups)
        tmp = {}

        for k,v in cur_packlist.items():
            vc = v['config']
            t2 = tmp.setdefault(vc['state'], None)

            if not t2:
                t2 = copy.deepcopy(vc)
                t2['name'] = [t2['name']]
            else:
                cp = t2.pop('name')
                np = vc.pop('name')

                ## assure package configs match
                ansible_assert(t2 == vc,
                   "Package configs must be identical in the same state group"
                )

                ## add new package to config
                cp.append(np)

                t2['name'] = cp
                vc['name'] = np

            tmp[vc['state']] = t2

        my_subcfg['_install_groups'] = list(tmp.values())
        return my_subcfg


class SinglePackageNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        super(SinglePackageNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return [SUBDICT_METAKEY_ANY, SUBDICT_METAKEY_ANY]

##    @property
##    def name_key(self):
##        return 'id'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)

        c = setdefault_none(my_subcfg, 'config', {})

        c['name'] = my_subcfg['name']
        setdefault_none(c, 'state', 'latest')

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
        return 'smabot_base_os_packages_args'

