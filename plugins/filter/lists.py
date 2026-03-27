

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


from ansible.errors import AnsibleFilterError, AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types
from ansible.module_utils.common._collections_compat import MutableMapping
from ansible.module_utils._text import to_native

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.plugins.filter_base import FilterBase



##
## sort date fields as real date object
##
## note: ansible already has builtin sorting filter and also date
##   instanciate filters, but getting both together in a clean
##   way is currently seemingly not possible
##
class DateSortFilter(FilterBase):

    FILTER_ID = 'date_sort'

    @property
    def argspec(self):
        tmp = super(DateSortFilter, self).argspec

        tmp.update({
          'attribute': (list(string_types) + [type(None)], None),
          'format': (list(string_types) + [type(None)], None),
          'reverse': ([bool], False),
        })

        return tmp

    def run_specific(self, inlist):
        from datetime import datetime

        dfmt = self.get_taskparam('format')
        sattr = self.get_taskparam('attribute')

        def sort_fn(x, sattr=sattr, dfmt=dfmt):
            ## on default assume x is a valid datetime string

            if sattr:
                ## if optional attribute param is set, assume
                ## x is a dict containing a valid datetime
                ## string using attribute as key(chain)
                for k in sattr.split('.'):
                    x = x[k]

            ## convert current element to proper datetime
            ## object, optionally using given format string
            if dfmt:
                return datetime.strptime(x, dfmt)

            return datetime.fromisoformat(x)

        return sorted(inlist,
          reverse=self.get_taskparam('reverse'), key=sort_fn
        )



# ---- Ansible filters ----
class FilterModule(object):
    ''' generic list filters '''

    def filters(self):
        res = {}

        tmp = [
          DateSortFilter,
        ]

        for f in tmp:
            res[f.FILTER_ID] = f()

        return res

