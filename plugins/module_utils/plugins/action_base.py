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

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


display = Display()


KWARG_UNSET = object()
MAGIC_ARGSPECKEY_META = '___args_meta'


def default_param_value(pname, defcfg, ans_varspace):
    if not defcfg:
        raise AnsibleOptionsError(
          "Must set mandatory param '{}'".format(pname)
        )

    # check if we have a match in for ansvars
    ansvars = defcfg.get('ansvar', [])
    for av in ansvars:
        if av in ans_varspace:
            return ans_varspace[av]

    # check if we have a matching envvar
    envvars = defcfg.get('env', [])
    envspace = ans_varspace['ansible_env']

    for e in envvars:
        if e in envspace:
            return envspace[e]

    # use hardcoded fallback
    if 'fallback' in defcfg:
        return defcfg['fallback']

    raise AnsibleOptionsError(
      "No hardcoded fallback for param '{}', set it either directly or"
      " by specifying one of these ansible variables (=> {}) or one of"
      " these environment variables (=> {})".format(pname, ansvars, envvars)
    )


def check_paramtype(param, value, typespec, errmsg):
    if typespec == []:
        # no type restriction ==> noop
        return

    if callable(typespec):
        return typespec(value)

    type_match = False

    for xt in typespec:
        sub_types = None

        if isinstance(xt, list):
            xt = list
            sub_types = xt

        if isinstance(value, xt):
            type_match = True
            break

    if not type_match:
        if not errmsg:
            errmsg = "Must be one of the following types: {}".format(typespec)
        raise AnsibleOptionsError(
           "Value '{}' for param '{}' failed its type"
           " check: {}".format(value, param, errmsg)
        )

    if isinstance(value, list):
        ansible_assert(sub_types, 'bad typespec')

        for vx in value:
            check_paramtype(param, vx, sub_types, errmsg)


class AnsibleInnerExecError(AnsibleError):

    def __init__(self, calltype, call_id, inner_res):
      super(AnsibleInnerExecError, self).__init__('')
      self.inner_res = inner_res
      self.call_type = calltype
      self.call_id = call_id


class BaseAction(ActionBase):
    ''' TODO '''

    def __init__(self, *args, **kwargs):
      super(BaseAction, self).__init__(*args, **kwargs)
      self._ansvar_updates = {}
      self._taskparams = {}


    @property
    def argspec(self):
        return {}


    def get_taskparam(self, name):
        return self._taskparams[name]


    def _rescheck_inner_call(self, inner_res, call_id, call_type, 
        ignore_error=False
    ):
        if ignore_error:
            return inner_res

        if inner_res.get('failed', False):
            raise AnsibleInnerExecError(call_type, call_id, inner_res)

        return inner_res


    def run_other_action_plugin(self, plugin_class, 
        ans_varspace=None, plugin_args=None, **kwargs
    ):
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


    def _handle_taskargs(self, argspec, args_in, args_out):
        display.vvv(
           "[ACTION_PLUGIN] :: handle args, argspec: {}".format(argspec)
        )

        argspec = copy.deepcopy(argspec)
        args_set = copy.deepcopy(args_in)

        args_found = {}

        args_meta = argspec.pop(MAGIC_ARGSPECKEY_META, {})

        for (k, v) in iteritems(argspec):
            ## first normalize argspec

            # convert convenience short forms to norm form
            if isinstance(v, collections.abc.Mapping):
                pass  # noop
            elif isinstance(v, tuple):
                tmp = {}

                for i in range(0, len(v)):
                    vx = v[i]

                    if i == 0:
                        tmp['type'] = vx
                    elif i == 1:
                        tmp['defaulting'] = { 'fallback': vx }
                    elif i == 2:
                        tmp['subspec'] = vx
                    else:
                        raise AnsibleInternalError(
                          "Unsupported short form argspec tuple: '{}'".format(v)
                        )

                v = tmp

            else:
                ## assume a single value for arg type
                v = { 'type': v }

            # normalize norm form
            ansible_assert('type' in v, 
              "Bad argspec for param '{}': Mandatory type field missing".format(k)
            )

            vdef = v.get('defaulting', None)

            mandatory = not vdef

            ## TODO: min and max sizes for collection types

            # get param
            key_hits = []
            aliases = v.get('aliases', [])
            for x in [k] + aliases:
                ansible_assert(x not in args_found, 
                  "Bad argspec for param '{}': duplicate alias"
                  " name '{}'".format(k, x)
                )

                if x in args_set:
                    key_hits.append(x)
                    pval = args_set.pop(x)
                    args_found[k] = True

            if len(key_hits) > 1:
                raise AnsibleOptionsError(
                  "Bad param '{}': Use either key or one of its aliases"
                  " '{}', but not more than one at a time".format(k, aliases)
                )

            if len(key_hits) == 0: 
                # param unset, do defaulting
                pval = default_param_value(k, vdef, self._ansible_varspace)

            ## at this point param is either set explicitly or by 
            ## defaulting mechanism, proceed with value tests
            check_paramtype(k, pval, v['type'], v.get('type_err', None))

            args_out[k] = pval

            subspec = v.get('subspec', None)

            if isinstance(pval, collections.abc.Mapping) and subspec:
                self._handle_taskargs(subspec, pval, pval)

        if args_set:
            raise AnsibleOptionsError(
              "Unsupported parameters given: {}".format(list(args_set.keys))
            )

        ## check mutual exclusions:
        for exlst in args_meta.get('mutual_exclusions', []):
            tmp = []

            for x in exlst:

                if x in args_found:
                    tmp.append(x)

                if len(tmp) > 1:
                    raise AnsibleOptionsError(
                      "It is not allowed to set mutual exclusive"
                      " params '{}' and '{}' together".format(*tmp)
                    )


    def get_ansible_var(self, var, default=KWARG_UNSET):
        if default != KWARG_UNSET:
            return self._ansible_varspace.get(var, default)
        return self._ansible_varspace[var]


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

