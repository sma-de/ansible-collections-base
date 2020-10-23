#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import collections
import copy
import re
import traceback

from ansible.module_utils.basic import missing_required_lib
from ansible.errors import AnsibleError, AnsibleInternalError, AnsibleOptionsError
from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems
from ansible.plugins.action import ActionBase, set_fact
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import AnsSpaceAndArgsPlugin
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert, detemplate


display = Display()



class AnsibleInnerExecError(AnsibleError):

    def __init__(self, calltype, call_id, inner_res):
      super(AnsibleInnerExecError, self).__init__('')
      self.inner_res = inner_res
      self.call_type = calltype
      self.call_id = call_id


class BaseAction(ActionBase, AnsSpaceAndArgsPlugin):
    ''' TODO '''

    def __init__(self, *args, **kwargs):
      ActionBase.__init__(self, *args, **kwargs)
      AnsSpaceAndArgsPlugin.__init__(self)
      self._ansvar_updates = {}


    def _rescheck_inner_call(self, inner_res, call_id, call_type, 
        ignore_error=False, on_error=False
    ):
        if ignore_error:
            return inner_res

        if inner_res.get('failed', False):

            if on_error:
                ignore_error = on_error(inner_res)

            if ignore_error:
                return inner_res

            raise AnsibleInnerExecError(call_type, call_id, inner_res)

        return inner_res


    def run_other_action_plugin(self, plugin_class, 
        ans_varspace=None, plugin_args=None, **kwargs
    ):
        display.vv(
           "[ACTION_PLUGIN] :: execute other action plugin: {}".format(
               plugin_class
           )
        )

        display.vvv(
           "[ACTION_PLUGIN] :: plugin args: {}".format(plugin_args)
        )

        ## TODO: not sure if it is really safe to reuse all this magic ansible interna's for other plugin calls, we need at least to adjust _task.args which again means we need a clean copy of this object at least
        ## note: re-using _task object and imply overwriting args worked, still not sure how safe this is
        self._task.args = plugin_args or {}

        tmp = plugin_class(self._task, self._connection, 
            self._play_context, self._loader, self._templar, 
            self._shared_loader_obj
        )

        return self._rescheck_inner_call(
           tmp.run(task_vars=ans_varspace or self._ansible_varspace), 
           str(plugin_class), 'ACTION_PLUGIN', **kwargs
        )


    def exec_module(self, modname, modargs=None, ans_varspace=None, **kwargs):
        display.vv("[ACTION_PLUGIN] :: execute module: {}".format(modname))
        display.vvv(
           "[ACTION_PLUGIN] :: execute module args: {}".format(modargs)
        )

        if modname == 'shell':
            ##
            ## for some strange reason executing shell here fails 
            ## internally, while using command works fine, luckily 
            ## shell and command are extremely similar so we will 
            ## map shell calls to command here for now
            ##
            ## TODO: find solution for bug described above
            ##
            ## bug-notes:
            ##
            ##   - only one context tested yet (connection docker, call from inside action plugin), so maybe this is important or maybe not
            ##
            ##   - happens for any cmd, even extremly simple ones like: echo foo
            ##
            ##   - calling shell module normally from playbook / tasklist / role works fine
            ##
            ##   - doesn't matter if name is 'shell' or 'ansible.builtin.shell'
            ##

            if not isinstance(modargs, collections.abc.Mapping):
                # assume freeform string
                modargs = {'cmd': modargs}

            tmp = []
            tmp.append(modargs.get('executable', '/bin/sh'))

            ## TODO: this depends on executable
            tmp.append('-c')

            tmp.append(modargs.pop('cmd'))

            modargs['argv'] = tmp
            modname = 'command'

        res = self._execute_module(module_name=modname, module_args=modargs,
            task_vars=ans_varspace or self._ansible_varspace
        )

        display.vvv(
           "[ACTION_PLUGIN] :: execute module result: {}".format(res)
        )

        return self._rescheck_inner_call(res, modname, 'MODULE', **kwargs)


    def set_ansible_vars(self, **kwargs):
        self._ansvar_updates.update(kwargs)


    @abc.abstractmethod
    def run_specific(self, result):
        ''' TODO '''
        pass


    def run(self, tmp=None, task_vars=None):
        ''' TODO '''

        # base method does some standard chorces like parameter validation 
        # and such, it makes definitly sense to call it (at all and first)
        result = super(BaseAction, self).run(tmp, task_vars)
        result['changed'] = False

        self._ansible_varspace = task_vars

        # handle args / params for this task
        self._handle_taskargs(self.argspec, self._task.args, self._taskparams)

        errmsg = None
        error_details = {}

        try:
            self.run_specific(result)

            if self._ansvar_updates:
                # with this to magic keys we can actually update the 
                # ansible var space directly just like set_fact, the first 
                # set the keys but the second is also important to set like 
                # this, otherwise var "foo" is only accessable as 
                # ansible_facts.foo beside many other important distinctions
                result['ansible_facts'] = self._ansvar_updates
                result['_ansible_facts_cacheable'] = False

                ##res = self.run_other_action_plugin(set_fact.ActionModule, **self._ansvar_updates)
                ##return res

                ## note: this fails, pretty sure this only works for "real" modules, not action plugins
                ##modret = self._execute_module(module_name='set_fact',
                ##  module_args=self._ansvar_updates, task_vars=task_vars
                ##)

                ##if modret.get('failed', False):
                ##    error_details['set_fact_result'] = modret
                ##    raise AnsibleInternalError(
                ##        "Updating ansible facts failed"
                ##    )

            return result

        except AnsibleInnerExecError as e:
            result = e.inner_res
            result['msg'] = \
               "Calling '{}' ({}) internally failed:"\
               " {}".format(e.call_id, e.call_type, result.get('msg', ''))

            return result

        except AnsibleError as e:
            error = e
            stacktrace = traceback.format_exc()

        except ModuleNotFoundError as e:
            error = e
            stacktrace = traceback.format_exc()

            bad_lib = re.search(r"(?i)module named '(.*?)'", e.msg).group(1)

            errmsg = missing_required_lib(bad_lib)

        except Exception as e:
            error = AnsibleInternalError(
               to_native("Unhandled native error {}: {}".format(type(e), e))
            )

            stacktrace = traceback.format_exc()

        error_details['stacktrace'] = stacktrace

        result['failed'] = True
        result['msg'] = errmsg or "{}".format(error)
        result['error'] = "{}".format(error)
        result['error_details'] = error_details
        result['stderr'] = stacktrace
        result['exception'] = stacktrace

        return result

