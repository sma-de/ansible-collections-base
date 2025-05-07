
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type



from ansible.module_utils.six import string_types
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins import \
  action_base,\
  plugin_base

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


display = Display()


class ActionModule(action_base.BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'break_system_packages': {
            'type': [bool],
            'defaulting': {
               'ansvar': ['SMABOT_BASE_PIPEXT_PADEF_BREAK_SYSTEM_PACKAGE'],
               'env': [],
               'fallback': False,
            },
          },
          ## forcefully activates break_system_packages, but only when
          ## this module detects it is needed (distro / python "new" enough)
          'force_break_system_packages': {
            'type': [bool],
            'defaulting': {
               'ansvar': ['SMABOT_BASE_PIPEXT_PADEF_FORCE_BREAK_SYSTEM_PACKAGE'],
               'env': [],
               'fallback': False,
            },
          },
        })

        return plugin_base.argspec_set_options(tmp,
          unknown_args_handler=plugin_base.MAGIC_ARGSPECVAL_UNKNOWNARGS_PASSTHROUGH
        )


    def run_specific(self, result):
        venv = self._taskparams.get('virtualenv', None)

        if not venv:
            ## handle special option break_system_packages which is needed
            ## for newer distro versions to change / update python module
            ## inside system paths
            force_break_sys = self._taskparams.pop('force_break_system_packages')
            break_sys = self.get_taskparam('break_system_packages')
            custom_exe = self._taskparams.get('executable', None)

            if force_break_sys:
                ## check if system-break will be necessary (based on used
                ## python version)
                display.vv(
                   "forcing break-system requested, check if"\
                   " break-system is necessary ..."
                )

                if custom_exe:
                    display.vv(
                       "custom pip executable set '{}', try determing"\
                       " corresponding python version ...".format(custom_exe)
                    )

                    mres = self.exec_module('ansible.builtin.command',
                        modargs={'argv': [custom_exe, 'debug', '--verbose']},
                        ignore_error=True,
                    )

                    ansible_assert(mres['rc'] in [0, 2],
                        "Trying to determine python version from custom"\
                        " pip exe '{}' failed with bad rc '{}':\n{}".format(
                           custom_exe, mres['rc'], mres
                        )
                    )

                    lpre = 'sys.version:'
                    pyver = None

                    for l in mres['stdout_lines']:
                        l = l.strip()

                        if l.startswith(lpre):
                            pyver = l[len(lpre):].strip()
                            break

                    ansible_assert(pyver,
                        "Failed to determine python version from custom"\
                        " pip exe '{}', expected to find line starting"\
                        " with '{}' in output, but this was not the"\
                        " case:\n{}".format(custom_exe, lpre, mres['stdout'])
                    )

                    pyver = pyver.split('.')
                    pyver = {
                      'major': pyver[0],
                      'minor': pyver[1],
                      'micro': pyver[2],
                    }

                else:
                    display.vv(
                       "use default ansible python, determine"\
                       " its version ..."
                    )

                    pyver = self.get_ansible_fact(
                       'ansible_python', None
                    ) or self.get_ansible_fact(
                       'python', None
                    ).get('version')

                display.vvv("determined python version:\n{}".format(pyver))

                if pyver['major'] > 3 or (pyver['major'] == 3 and pyver['minor'] > 10):
                    ## flag is needed to avoid pip erroring out without venv
                    display.vv(
                       "found python version supports and needs"\
                       " break-system flag, force it"
                    )

                    break_sys = True
                    self._taskparams['break_system_packages'] = break_sys
                else:
                    display.vv(
                        "found python version is to old for break-system"\
                        " flag, nothing to do here"
                    )

            ansver = self.get_ansible_var('ansible_version')

            if ansver['major'] < 2 or (ansver['major'] == 2 and ansver['minor'] < 17):
                ## wrapped upstream module does not support the break-system
                ## param not yet for too old ansible versions, if it is not
                ## active, just pop the param and we are already golden here
                self._taskparams.pop('break_system_packages')

                if break_sys:
                    ## break-system is active, workaround missing module
                    ## param with older cmdline passthrough method
                    extra_args = self._taskparams.get('extra_args', '')

                    if extra_args:
                        extra_args += ' '

                    extra_args += '--break-system-packages'
                    self._taskparams['extra_args'] = extra_args

        return self.exec_module('ansible.builtin.pip',
          modargs=self._taskparams,
        )

