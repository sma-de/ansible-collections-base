
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
import re


from ansible.errors import AnsibleOptionsError

from ansible.module_utils.six import string_types
from ansible.plugins.lookup import LookupBase
from ansible.module_utils._text import to_native, to_text
from ansible.utils.display import Display
from ansible.module_utils.six import iteritems


from ansible_collections.community.general.plugins.lookup import filetree

from ansible_collections.smabot.base.plugins.module_utils.plugins.lookup_base import BaseLookup


display = Display()


def normalize_excludable_list_arg(arg):
    if isinstance(arg, list):
        arg = { 'list': arg }

    arg.setdefault('exclude', False)
    return arg


class LookupModule(BaseLookup):

    @property
    def argspec(self):
        tmp = super(LookupModule, self).argspec

        filter_subspec = {
         'types': ([collections.abc.Mapping, list(string_types)], {}),
         'match': ([collections.abc.Mapping, list(string_types)], {}),
        }

        tmp.update({
          'filters': ([collections.abc.Mapping], {}, filter_subspec),
          'passthrough': ([collections.abc.Mapping], {}),
        })

        return tmp


    def create_filter_by_types(self, cfg):
        normed_cfg = normalize_excludable_list_arg(cfg)

        def filter_by_types(val):
            res = val['state'] in normed_cfg['list']

            if normed_cfg['exclude']:
                res = not res

            return res

        return filter_by_types

    def create_filter_by_match(self, cfg):
        normed_cfg = normalize_excludable_list_arg(cfg)

        def filter_by_match(val):
            res = False

            for rgx in normed_cfg['list']:
                res = re.search(rgx, val['path'])

                if res:
                    break

            if normed_cfg['exclude']:
                res = not res

            return bool(res)

        return filter_by_match


    def run_specific(self, terms):
        ## actually call the standard filetree internally 
        ## for getting the raw dir tree
        dirlist = self.run_other_lookup_plugin(filetree.LookupModule, 
          *terms, **self.get_taskparam('passthrough')
        )

        filters = self.get_taskparam('filters')

        if not filters:
            ## if no filters are specified, this returns 1:1 
            ## the result of wrapped upstream plugin
            return dirlist

        ## create filter functions based on user cfg
        filtlst = []

        for (filtid, filtcfg) in iteritems(filters):
            if not filtcfg:
                continue

            fc = getattr(self, "create_filter_by_{}".format(filtid), None)

            if not fc:
                raise AnsibleOptionsError(
                  "Unsupported filter type '{}'".format(filtid)
                )

            filtlst.append(fc(filtcfg))

        ## note: actually as filetree already returns a flat list (d'uhh), 
        ##   doing this recursevily here is more wrong than right

        ## ## remove all dir elements which do not match all given filters
        ## def visit(path, key, value):
        ##     for f in filtlst:
        ##         if not f(value):
        ##             return False

        ##     return True

        ##from boltons.iterutils import remap
        ##return remap(dirlist, visit=visit)

        res = []
        for p in dirlist:
            filtered_out = False

            for f in filtlst:
                if not f(p):
                    filtered_out = True
                    break

            if not filtered_out:
                res.append(p)

        return res

