
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import re


from ansible.module_utils.six import string_types
##from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import remove_ansible_defret_vals


##display = Display()


class ActionModule(BaseAction):

    PAMD_PASSTHROUGH_ARS = [
      'backup',
      'control',
      'module_arguments',
      'module_path',
      'name',
      'new_control',
      'new_module_path',
      'new_type',
      'path',
      'state',
      'type',
    ]


    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'backup': ([bool, type(None)], None),
          'control': (list(string_types)),
          'module_arguments': ([list(string_types), type(None)], None),
          'module_path': (list(string_types)),
          'name': (list(string_types)),
          'new_control': (list(string_types) + [type(None)], None),
          'new_module_path': (list(string_types) + [type(None)], None),
          'new_type': (list(string_types) + [type(None)], None),
          'path': (list(string_types), "/etc/pam.d"),
          'state': (list(string_types), "updated"),
          'type': (list(string_types)),
        })

        return tmp


    def regexify_param(self, val):
        return re.escape(val)


    def assure_pamline_exists(self, result):
        ##
        ## there already exists a pamd module in community.general and it
        ## should be preferred as much as possible, but one thing it is
        ## strangely bad at (atm) is to add a new pam rule because it
        ## only adds it when another already existing rule is explicitly
        ## specified where to position the new rule relatively too, in
        ## principle there is nothing wrong with this as order can be
        ## quite important for pam rules, but it still should be imho
        ## possible to simply just append new rules for simple cases,
        ## this we will do here by using the lineinfile module
        ##
        mres = self.exec_module('ansible.builtin.lineinfile',
          modargs={
            'state': 'present',
            'path': self.get_taskparam('path') + '/' + self.get_taskparam('name'),

            'regexp': r'^{}\s+{}\s+{}($|\s+.*)'.format(
               self.regexify_param(self.get_taskparam('type')),
               self.regexify_param(self.get_taskparam('control')),
               self.regexify_param(self.get_taskparam('module_path')),
            ),

            ##
            ## note that the line used here might be only a simplified
            ## version of the actual final line (e.g. module_arguments),
            ## but after this call guarantees that at least a simplified
            ## version does exists in the pamd file the later pamd module
            ## call should be able to handle the finetuning itself correctly
            ##
            'line': '{}\t{}\t{}'.format(
               self.get_taskparam('type'),
               self.get_taskparam('control'),
               self.get_taskparam('module_path'),
            ),
          },
        )

        t, t2 = remove_ansible_defret_vals(mres)

        result['append'] = t

        if t2['changed']:
            result['changed'] = True


    def run_specific(self, result):
        state = self.get_taskparam('state')

        if state == 'updated':
            self.assure_pamline_exists(result)

        ## atm we simple pass through everything to upstream
        ## pamd module unchanged
        pass_args = {}

        for x in self.PAMD_PASSTHROUGH_ARS:
            pass_args[x] = self.get_taskparam(x)

        mres = self.exec_module('community.general.pamd',
          modargs=pass_args,
        )

        t, t2 = remove_ansible_defret_vals(mres)

        result['pamd'] = t

        if t2['changed']:
            result['changed'] = True

        return result

