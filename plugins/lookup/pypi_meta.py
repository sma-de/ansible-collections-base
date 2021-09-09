
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

## DOCUMENTATION = r'''
## TODO
## '''
## 
## EXAMPLES = r"""
## TODO
## """
## 
## RETURN = r"""
## TODO
## """

import collections


from ansible.errors import AnsibleOptionsError

from ansible.module_utils.six import string_types
##from ansible.plugins.lookup import LookupBase
from ansible.module_utils._text import to_native, to_text
from ansible.utils.display import Display
from ansible.module_utils.six import iteritems


##from ansible_collections.community.general.plugins.lookup import filetree

from ansible_collections.smabot.base.plugins.module_utils.plugins.lookup_base import BaseLookup


display = Display()


## TODO: this really should be a generic fn from a generic lib
def parse_slice(slice_raw):
    if slice_raw is None:
        return slice(None)

    slice_args = []

    if isinstance(slice_raw, string_types):
        tmp = slice_raw.split(':')

        for x in tmp:
            x = x.strip()

            if x:
                x = int(x)
            else:
                x = None

            slice_args.append(x)
    else:
        # expect a single int type
        slice_args.append(int(slice_raw))

    if len(slice_args) == 1:
        ## note: x[3] != slice(3) and x[-2] is definetly 
        ##   not slice(-2), but we want the first behaviour 
        ##   in the cases we only have one number, so we 
        ##   do that if here which give us the wanted answer
        return slice_args[0]

    return slice(*slice_args)


class LookupModule(BaseLookup):

    @property
    def argspec(self):
        tmp = super(LookupModule, self).argspec

        tmp.update({
          'scope': (list(string_types), 'project', ['project']),
          'host': (list(string_types), 'https://pypi.org'),

          'subfn': (list(string_types), ''),
          'subfn_args': ([collections.abc.Mapping], {}),
        })

        return tmp


    def _subfn_get_versions(self, info_json, 
        subselect=None, force_list=False
    ):
        res = list(info_json['releases'].keys())

        if not subselect:
            return res

        res = res[parse_slice(subselect)]

        if force_list and not isinstance(res, list):
            res = [res]

        return res


    def _scope_project(self, project_name):
        return "/pypi/{}/json".format(project_name)


    def run_specific(self, terms):
        import requests

        host = self.get_taskparam('host')
        scope = self.get_taskparam('scope')

        scope = getattr(self, '_scope_' + scope)

        subfn_args = self.get_taskparam('subfn_args')
        subfn = self.get_taskparam('subfn')

        if subfn:
            tmp = getattr(self, '_subfn_' + subfn, None)

            if not tmp:
                raise AnsibleOptionsError(
                   "Unsupported sub function '{}'".format(subfn)
                )

            subfn = tmp

        res = []
        for t in terms:
            url = host + scope(t)

            tmp = requests.get(url)
            tmp.raise_for_status()
            tmp = tmp.json()

            if subfn:
                tmp = subfn(tmp, **subfn_args)

            res.append(tmp)

        return res

