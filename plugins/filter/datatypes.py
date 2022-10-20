

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

from ansible.errors import AnsibleFilterError, AnsibleOptionsError
from ansible.module_utils.six import string_types
from ansible.module_utils.common._collections_compat import MutableMapping
from ansible.module_utils._text import to_text, to_native

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.plugins.filter_base import FilterBase

from ansible.utils.display import Display


display = Display()


class ToBoolFilter(FilterBase):

    FILTER_ID = 'to_bool'

    def run_specific(self, value):
        return bool(value)


# ---- Ansible filters ----
class FilterModule(object):
    ''' data type (conversions) related filters '''

    def filters(self):
        res = {}

        for f in [ToBoolFilter]:
            res[f.FILTER_ID] = f()

        return res

