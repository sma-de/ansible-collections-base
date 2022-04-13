

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


DICTKEY_UNSET = object()


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
        tmp = super(SubdictFilter, self).argspec

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


##
## Simply walks down from a base dict into a subdict, normally one
## would simply do "foo.x.y.z" for such cases but this becomes useful
## when the keychain itself is variable: foo[[x,y,z]]
##
##  TODO: is there really nothing builtin in which can do this???
##
class GetSubdictFilter(FilterBase):

    FILTER_ID = 'get_subdict'

    @property
    def argspec(self):
        tmp = super(GetSubdictFilter, self).argspec

        tmp.update({
          'keychain': ([[str]]),
          'default': ([object], DICTKEY_UNSET),
          'default_on_type_mismatch': ([bool], False),
        })

        return tmp


    def run_specific(self, indict):
        if not isinstance(indict, MutableMapping):
            raise AnsibleOptionsError(
               "filter input must be a dictionary, but given value"\
               " '{}' has type '{}'".format(indict, type(indict))
            )

        defval = self.get_taskparam('keychain')
        def_badtype = self.get_taskparam('default_on_type_mismatch')

        res = indict
        kc = []
        for k in self.get_taskparam('keychain'):
            if not isinstance(res, (MutableMapping, list)):
                if def_badtype:
                    return defval

                raise AnsibleOptionsError(
                   "Expected collection type item on subpath '{}',"\
                   " but found value of type '{}': {}".format(
                      '.'.join(kc), type(res), res
                   )
                )

            res = res.get(k, DICTKEY_UNSET)
            kc.append(k)

            if res == DICTKEY_UNSET:
                if defval != DICTKEY_UNSET:
                    return defval

        return res



# ---- Ansible filters ----
class FilterModule(object):
    ''' generic dictionary filters '''

    def filters(self):
        res = {}

        for f in [GetSubdictFilter, KvListFilter, SubdictFilter]:
            res[f.FILTER_ID] = f()

        return res

