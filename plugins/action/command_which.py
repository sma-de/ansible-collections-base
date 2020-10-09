
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import textwrap


from ansible.module_utils.six import string_types
##from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction


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
          'cmd': (list(string_types) + [list(string_types)]),
          'test_args': ([list(string_types)], []),
        })

        return tmp

    def _get_abspath(self, cmd):
        ## not sure what the real which does internally what doing a 
        ## pseudo which is actually quite straight forward, just read 
        ## out PATH var, split it, and test in the loop if we get an 
        ## existing file with the combined path
        script = textwrap.dedent("""\
           echo "$PATH" | tr ":" "\\n" | ( while read p; do \\
           tmp="$p/{}" \\
           ; if [ -e "$tmp" ]; then echo "$tmp" ; exit 0 ; fi \\
           ; done ; exit 1 ) """.format(cmd)
        )

        ## simply try to call the command per shell, 
        ## and look if it works or not
        mres = self.exec_module('shell', 
          modargs={'cmd': script}, ignore_error=True
        )

        return mres['stdout']


    def run_specific(self, result):
        cmd = self.get_taskparam('cmd')

        result['abspath'] = ''
        result['linksrc'] = ''

        abspath = None
        cmd_match = None

        if not isinstance(cmd, list):
            cmd = [cmd]

        for ca in cmd:
            abspath = self._get_abspath(ca)

            if abspath:
                cmd_match = ca
                break

        if not abspath:
            ## command could not be found on remote, return with 
            ## empty result, but dont fail module on default
            return result

        result['abspath'] = abspath
        result['matched_cmd'] = cmd_match

        ## as a little extra service, if the found abspath 
        ## is a symlink, follow it to its source, do this always, 
        ## if abspath is no symlink, linksrc == abspath
        mres = self.exec_module('shell', 
          modargs={'cmd': "readlink -f '{}'".format(abspath)}, ##ignore_error=True  ## should normally never fail
        )

        result['linksrc'] = mres['stdout']
        
        test_args = self.get_taskparam('test_args')

        if not test_args:
            return result

        ## optionally do a test run with found abspath
        ##
        ## note: we dont use shell here, but call the exe directly, 
        ##   this should be fine as we have the abspath, right?
        mres = self.exec_module('ansible.builtin.command', 
          modargs={'argv': [abspath] + test_args}
        )

        return result

