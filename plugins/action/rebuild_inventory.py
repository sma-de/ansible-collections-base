
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections


from ansible.module_utils.six import string_types
##from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


##display = Display()


class ActionModule(BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


# TODO: support excluding parts of inventory
    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'modify_by': ([collections.abc.Mapping], {}),
        })

        return tmp


    def _mod_host_settings_by_group(self, h, def_settings, grplst, modcfg):
        for g in grplst:
            tmp = modcfg.get(g, None)

            if not tmp:
                continue

            for k, v in tmp.items():
                h[k] = v.format(**def_settings)


    def _get_full_host_reference(self, h, hostvars, grplst, modifiers):
        hv = hostvars[h]

        res = {}
        def_settings = {}

        # do default host settings
        for k in ['ansible_host']:
            res[k] = hv[k]
            def_settings[k] = hv[k]

        # extra keys for templating in modifiers
        for sk, tk in [('computer_name', 'hostname')]:
            def_settings[tk] = hv[sk]

        # optionally chain settings through modifiers
        for m in modifiers.get('order', modifiers.keys()):
            tmp = getattr(self, '_mod_host_settings_by_' + m, None)

            mv = modifiers[m]

            ansible_assert(tmp,
              "Unsupported modifier type '{}': {}".format(m, mv)
            )

            tmp(res, def_settings, grplst, mv)

        return res


    def run_specific(self, result):
        modifiers = self.get_taskparam('modify_by')
        inv_grps = self.get_ansible_var('groups')

        ungrouped = inv_grps['ungrouped']

        # TODO: not yet sure how to handle ungrouped, did not have a case yet where this was not empty
        ansible_assert(not ungrouped, "handling ungrouped not supported yet")

        # convert "all" to map
        hosts_all = {}

        for h in inv_grps['all']:
            hosts_all[h] = []

        # handle other custom groups
        for g, hlst in inv_grps.items():
            if g in ['all', 'ungrouped']:
                continue

            for h in hlst:
                hosts_all[h].append(g)

        hostvars = self.get_ansible_var('hostvars')

        all_hosts = {}
        all_subgrps = {}

        for h, grplst in hosts_all.items():
            if not grplst:
                # current host is not part of any group except "all",
                # add it as direct child to hosts
                all_hosts[h] = self._get_full_host_reference(
                  h, hostvars, grplst, modifiers
                )

                continue

            ## host is part of one or more custom subgroups, add it
            ## with the full description to first group and as
            ## minimal reference value to all others
            full_reference = True
            for g in grplst:
                g = all_subgrps.setdefault(g, {'hosts': {}})
                g = g['hosts']

                hcfg = None
                if full_reference:
                    hcfg = self._get_full_host_reference(
                       h, hostvars, grplst, modifiers
                    )

                g[h] = hcfg
                full_reference = False

        ##
        ## note that there are multiple euquivalent ways to describe
        ## a semantically identical inventory, so it is totally possible
        ## that the result of this plugin looks different to how the
        ## inventory looked as input, but functionally it should be the same
        ##
        result['inventory'] = {
          'all': {
             'hosts': all_hosts,
             'children': all_subgrps,
          },
        }

        return result

