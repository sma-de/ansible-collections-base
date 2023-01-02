
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections


from ansible.errors import AnsibleError
from ansible.module_utils.six import iteritems, string_types
##from ansible.utils.display import Display
from ansible.plugins.action import include_vars, template

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction

from ansible_collections.smabot.base.plugins.action import merge_vars
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import \
  get_subdict,\
  merge_dicts,\
  template_recursive


##display = Display()


class ActionModule(BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'dirtree': ([[collections.abc.Mapping]]),
        })

        return tmp


    def _handle_cfgfile(self, cfgdict, cfgfile):
        src_path = cfgfile['src']
        tmpfile = None
        tmpkey = '_tmp_vardir_cfgfile'

        try:

            if src_path.endswith('.j2'):
                # template input cfgfile before reading vars
                tmpfile = self.exec_module('ansible.builtin.tempfile', 
                  modargs={'state': 'file'}
                )['path']

                self.run_other_action_plugin(template.ActionModule, 
                   plugin_args={'src': src_path, 'dest': tmpfile,
                    'variable_start_string': '{!',
                    'variable_end_string': '!}',
                    'block_start_string': '{=',
                    'block_end_string': '=}',
                  }
                )

                src_path = tmpfile

            tmp = self.run_other_action_plugin(include_vars.ActionModule, 
               plugin_args={'file': src_path, 'name': tmpkey }
            )

        finally:

            if tmpfile:
                self.exec_module('ansible.builtin.file', 
                  modargs={'state': 'absent', 'path': tmpfile}
                )

        merge_dicts(cfgdict, tmp['ansible_facts'][tmpkey])


    def run_specific(self, result):
        dirtree = self.get_taskparam('dirtree')

        dircfg = {}

        # build dircfg from dir tree
        for sp in dirtree:
            spp = sp['path']
            sps = sp['state']
            key = spp.split('/')

            if sps == 'directory':
                # dirs are used as cfg subkeys, but this is handled 
                # also at the file section, so noop atm
                pass

            elif sps == 'file':
                key = key[:-1]
                self._handle_cfgfile(
                  get_subdict(dircfg, key, default_empty=True), sp
                )

            else:
                raise AnsibleError(
                   "Unsupported path item state '{}' for"\
                   " path '{}'".format(sps, spp)
                )

        # merge new dircfg with existing vars of the same name
        ma = {
          'result_var': merge_vars.MAGIG_KEY_TOPLVL,
          'update_facts': False,
        }

        tmp = {}

        for (k, v) in iteritems(dircfg):
            v = template_recursive(v, self._templar)
            tmp[k] = v

            if not isinstance(v, collections.abc.Mapping):
                continue

            # if found toplvl key is a mapping, do a vars merge for it
            # ordering??
            tmp[k] = self.merge_vars(invars=[{'name': k, 'optional': True}], 
              vardict=v, vardict_pos=-1
            )['merged_var']

        dircfg = tmp

        if dircfg:
            self.set_ansible_vars(**dircfg)

        result['dircfg'] = dircfg
        return result

