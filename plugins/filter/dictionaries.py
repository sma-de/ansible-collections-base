

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
## Converts a dict to a list of key-value strings
##
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



##
## Returns a somewhat filtered subdict of input dict
##
class SubdictFilter(FilterBase):

    FILTER_ID = 'subdict'

    @property
    def argspec(self):
        tmp = super(KvListFilter, self).argspec

        tmp.update({
          'keys_keep': ([[str]], []),
          'keys_remove': ([[str]], []),
          'values_keep': ([[str]], []),
          'values_remove': ([[str]], []),
        })

        return tmp


    def run_specific(self, indict):
        if not isinstance(indict, MutableMapping):
            raise AnsibleOptionsError(
               "filter input must be a dictionary, but given value"\
               " '{}' has type '{}'".format(indict, type(indict))
            )

        ## TODO: support callables/ functions for keep/rm test
        kkeep = self.get_taskparam('keys_keep')
        krm = self.get_taskparam('keys_remove')

        if kkeep and krm:
            raise AnsibleOptionsError(
               "Either specifiy dict keys to keep or keys to remove,"\
               " but never both at the same call"
            )

        vkeep = self.get_taskparam('values_keep')
        vrm = self.get_taskparam('values_remove')

        if vkeep and vrm:
            raise AnsibleOptionsError(
               "Either specifiy dict values to keep or values to"\
               " remove, but never both at the same call"
            )

        res = {}

        for (k, v) in iteritems(indict):

            if kkeep and k not in kkeep:
                continue  ## remove

            if krm and k in krm:
                continue  ## remove

            if vkeep and v not in vkeep:
                continue  ## remove

            if vrm and v in vrm:
                continue  ## remove

            res[k] = v

        return res



# ---- Ansible filters ----
class FilterModule(object):
    ''' generic dictionary filters '''

    def filters(self):
        res = {}

        for f in [KvListFilter, SubdictFilter]:
            res[f.FILTER_ID] = f()

        return res

