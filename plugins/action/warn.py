
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


from ansible.module_utils.six import string_types
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction


display = Display()


ANSIBLE_WARNINGS_VAR = 'ans_warnings'


##
## note: unexpectedly there is not yet such a thing in vanilla ansible for printing warnings in playbooks, but there is an open feature request for it, so keep an eye on that:
##   https://github.com/ansible/ansible/issues/67260
##

class ActionModule(BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'msg': (list(string_types)),
        })

        return tmp


    def run_specific(self, result):
        msg = self.get_taskparam('msg')

        display.warning(msg)
        result['msg'] = msg

        ## collect all warnings as list for later usage (like report at end or stuff like that)
        warns = self.get_ansible_var(ANSIBLE_WARNINGS_VAR, [])
        warns.append(msg)
        self.set_ansible_vars(**{ANSIBLE_WARNINGS_VAR: warns})

        return result

