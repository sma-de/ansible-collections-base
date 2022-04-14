

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

import collections
import re

from ansible.errors import AnsibleFilterError, AnsibleOptionsError
from ansible.module_utils.six import string_types
from ansible.module_utils.common._collections_compat import MutableMapping
from ansible.module_utils._text import to_text, to_native

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.plugins.filter_base import FilterBase

from ansible.utils.display import Display


display = Display()


class VersionSortFilter(FilterBase):

    FILTER_ID = 'sort_versions'

    @property
    def argspec(self):
        tmp = super(VersionSortFilter, self).argspec

        tmp.update({
          'reverse': ([bool], False),
          'method': (list(string_types), 'int_tuples'),
          'method_args': ([collections.abc.Mapping], {}),
        })

        return tmp


    def _method_int_tuples(self, x, versep=r'\.', **kwargs):
        # expects input values to be either already a list/tuple
        # representing each version component or a plain string
        # in which case the string is splitted by sep into a
        # list of single ver components
        if isinstance(x, string_types):
            x = re.split(versep, x)

        # TODO: support ver numbers with un-intable parts
        return list(map(int, x))


    def run_specific(self, value):
        if not isinstance(value, list):
            raise AnsibleOptionsError(
               "input value must be a list, but is of"\
               " type '{}'".format(type(value))
            )

        m = self.get_taskparam('method')
        tmp = getattr(self, '_method_' + m, None)

        ansible_assert(tmp, "unsupported sorting method '{}'".format(m))

        value = sorted(value,
           key=lambda x: tmp(x, **self.get_taskparam('method_args')),
           reverse=self.get_taskparam('reverse')
        )

        return value



class ListAddFilter(FilterBase):

    FILTER_ID = 'listadd'

    @property
    def argspec(self):
        tmp = super(ListAddFilter, self).argspec

        tmp.update({
          'lists': ([[]]),
          'optional': ([bool], True),
          'split': (list(string_types), ''),
        })

        return tmp


    def run_specific(self, value):
        if not isinstance(value, list):
            raise AnsibleOptionsError(
               "input value must be a list, but is of"\
               " type '{}'".format(type(value))
            )

        splitter = self.get_taskparam('split')

        for l in self.get_taskparam('lists'):
            if not l:
                ansible_assert(self.get_taskparam('optional'),
                  "Mandatory list to add is empty/none"
                )

                # ignore unset optional list
                continue

            if isinstance(l, string_types):
                ansible_assert(splitter,
                   "list to add is a string (=> '{}'), but no splitter"\
                   " was defined, set it like this: split=':'".format(l)
                )

                l = re.split(splitter, l)

            value += l

        return value



# ---- Ansible filters ----
class FilterModule(object):
    ''' file path related filters '''

    def filters(self):
        res = {}

        for f in [ListAddFilter, VersionSortFilter]:
            res[f.FILTER_ID] = f()

        return res

