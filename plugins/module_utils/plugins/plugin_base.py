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

from ansible.errors import AnsibleError, AnsibleInternalError, AnsibleOptionsError
from ansible.module_utils.basic import missing_required_lib
from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert, detemplate


display = Display()


KWARG_UNSET = object()
MAGIC_ARGSPECKEY_META = '___args_meta'


def default_param_value(pname, defcfg, ans_varspace, templater):
    def get_space_val(space, key, templater=templater):
        res = space[key]

        if templater:
            ## note: at least sometimes when we get values 
            ## from ansible varspace, they are still template 
            ## string, not the templated value
            res = detemplate(res, templater)

        return res

    if not defcfg:
        raise AnsibleOptionsError(
          "Must set mandatory param '{}'".format(pname)
        )

    # check if we have a match in for ansvars
    ansvars = defcfg.get('ansvar', [])
    for av in ansvars:
        if av in ans_varspace:
            return get_space_val(ans_varspace, av)

    # check if we have a matching envvar
    envvars = defcfg.get('env', [])
    envspace = ans_varspace.get('ansible_env', {})

    for e in envvars:
        if e in envspace:
            return get_space_val(envspace, e)

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

    display.vvv(
      "[PLUGIN] :: handle args, do type check: {}".format(typespec)
    )

    for xt in typespec:
        display.vvv(
          "[PLUGIN] :: handle args, type test: {}".format(xt)
        )

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

        display.vvv(
          "[PLUGIN] :: handle args, do subtype check: {}".format(sub_types)
        )

        for vx in value:
            check_paramtype(param, vx, sub_types, errmsg)



class ArgsPlugin():
    ''' TODO '''

    def __init__(self):
      self._taskparams = {}
      self._ansible_varspace = {}


    @property
    def argspec(self):
        return {}

    @property
    def error_prefix(self):
        return ''


    def get_taskparam(self, name):
        return self._taskparams[name]


    def _handle_taskargs(self, argspec, args_in, args_out):
        display.vvv(
           "[PLUGIN] :: handle args, argspec: {}".format(argspec)
        )

        argspec = copy.deepcopy(argspec)
        args_set = copy.deepcopy(args_in)

        args_found = {}

        args_meta = argspec.pop(MAGIC_ARGSPECKEY_META, {})

        for (k, v) in iteritems(argspec):
            display.vv(
              "[PLUGIN] :: handle args, do param '{}'".format(k)
            )

            ## first normalize argspec

            # convert convenience short forms to norm form
            if isinstance(v, collections.abc.Mapping):
                display.vvv(
                   "[PLUGIN] :: handle args, argspec is dict,"\
                   " nothing to normalize"
                )

                pass  # noop
            elif isinstance(v, tuple):
                tmp = {}

                display.vvv(
                   "[PLUGIN] :: handle args, argspec is short form,"\
                   " normalizing ..."
                )

                for i in range(0, len(v)):
                    vx = v[i]

                    if i == 0:
                        tmp['type'] = vx
                    elif i == 1:
                        tmp['defaulting'] = { 'fallback': vx }
                    elif i == 2:
                        if isinstance(vx, collections.abc.Mapping):
                            tmp['subspec'] = vx
                        else:
                            tmp['choice'] = vx

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

            display.vvv(
              "[PLUGIN] :: handle args, get set val / handle"\
              " aliasing: {}".format(aliases)
            )

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
                display.vv("[PLUGIN] :: handle args, do defaulting")

                # param unset, do defaulting
                pval = default_param_value(
                   k, vdef, self._ansible_varspace, 
                   getattr(self, '_templar', None)
                )

            display.vv(
              "[PLUGIN] :: handle args, final pvalue: |{}|".format(pval)
            )

            display.vv(
              "[PLUGIN] :: handle args, check param"\
              " type: {}".format(v['type'])
            )

            ## at this point param is either set explicitly or by 
            ## defaulting mechanism, proceed with value tests
            check_paramtype(k, pval, v['type'], v.get('type_err', None))

            ## optionally handle choice
            choice = v.get('choice', None)

            if choice:
                display.vvv(
                  "[PLUGIN] :: handle args, handle choice: {}".format(choice)
                )

                ansible_assert(isinstance(choice, list), 
                   "bad argspec[{}]: choice must be list,"\
                   " but was '{}': {}".format(k, type(choice), choice)
                )

                ansible_assert(
                   not isinstance(pval, (list, collections.abc.Mapping)), 
                   "bad argspec[{}]: if choice is specified, param"\
                   " cannot be collection type, it must be scalar".format(k)
                )

                if pval not in choice:
                    raise AnsibleOptionsError(
                       "Bad param '{}': given value was '{}' but it"\
                       " must be one of these: {}".format(k, pval, choice)
                    )

            args_out[k] = pval

            subspec = v.get('subspec', None)

            if isinstance(pval, collections.abc.Mapping) and subspec:
                display.vvv(
                  "[PLUGIN] :: handle args, do subspec: {}".format(subspec)
                )

                self._handle_taskargs(subspec, pval, pval)

        if args_set:
            raise AnsibleOptionsError(
              "Unsupported parameters given: {}".format(list(args_set.keys()))
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


    ## @abc.abstractmethod
    ## def run_specific(self, *args, **kwargs):
    ##     pass


    def run_wrapper(self, *args, **kwargs):
        try:
            return self.run_specific(*args, **kwargs)
        except AnsibleError as e:
            raise type(e)("{}{}".format(self.error_prefix, e))
        except ModuleNotFoundError as e:
            bad_lib = re.search(r"(?i)module named '(.*?)'", e.msg).group(1)
            raise AnsibleError("{}{}".format(
               self.error_prefix, missing_required_lib(bad_lib))
            )

        except Exception as e:
            raise AnsibleInternalError("{}{}".format(self.error_prefix,
               to_native("Unhandled native error {}: {}".format(type(e), e))
            )) from e


class AnsSpaceAndArgsPlugin(ArgsPlugin):
    ''' TODO '''

    def __init__(self, *args, **kwargs):
        super(AnsSpaceAndArgsPlugin, self).__init__(*args, **kwargs)


    @property
    def remote_envvars(self):
        return self._ansible_varspace.get('ansible_env', {})


    def get_ansible_var(self, var, default=KWARG_UNSET):
        varkeys = var.split('.')

        next_subkey = varkeys[0]
        res = self._ansible_varspace.get(next_subkey, KWARG_UNSET)

        for k in varkeys[1:]:
            if res == KWARG_UNSET:
                break

            next_subkey = k
            res = res.get(next_subkey, KWARG_UNSET)

        if res == KWARG_UNSET:
            ansible_assert(default != KWARG_UNSET,
               "Failed to find subkey '{}' for mandatory"\
               " ansible variable '{}'".format(next_subkey, var)
            )

            return default

        return detemplate(res, self._templar)


    def get_ansible_fact(self, fact, default=KWARG_UNSET):
        facts = self.get_ansible_var('ansible_facts')

        for k in fact.split('.'):
            facts = facts.get(k, KWARG_UNSET)

            if facts == KWARG_UNSET:
                ansible_assert(default != KWARG_UNSET,
                   "Failed to find subkey '{}' for mandatory"\
                   " ansible fact key '{}'".format(k, fact)
                )

                return default

        return facts

