

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



class KvListFilter(FilterBase):

    FILTER_ID = 'kvlist'

    @property
    def argspec(self):
        tmp = super(KvListFilter, self).argspec

        tmp.update({
          'joiner': (list(string_types), '='),
        })

        return tmp


    def run_specific(self, indict):
        if not isinstance(indict, MutableMapping):
            raise AnsibleOptionsError(
               "filter input must be a dictionary, but given value"\
               " '{}' has type '{}'".format(indict, type(indict))
            )

        joiner = self.get_taskparam('joiner')

        res = []

        for (k, v) in iteritems(indict):
            res.append(str(k) + joiner + str(v))

        return res


# ---- Ansible filters ----
class FilterModule(object):
    ''' generic dictionary filters '''

    def filters(self):
        res = {}

        for f in [KvListFilter]:
            res[f.FILTER_ID] = f()

        return res

