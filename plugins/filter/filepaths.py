

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

import os

from ansible.errors import AnsibleFilterError, AnsibleOptionsError
from ansible.module_utils.six import string_types
from ansible.module_utils.common._collections_compat import MutableMapping
from ansible.module_utils._text import to_native

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.plugins.filter_base import FilterBase



class StripFileEndingsFilter(FilterBase):

    FILTER_ID = 'strip_file_endings'
##    def __init__(self, *args, **kwargs):
##        super(FilterBase, self).__init__(*args, **kwargs)

    @property
    def argspec(self):
        tmp = super(StripFileEndingsFilter, self).argspec

        tmp.update({
          MAGIC_ARGSPECKEY_META: {
            'mutual_exclusions': ['endings', 'count'],
          },

          'endings': ([list(string_types)], []),
          'count': ([int], 1),
        })

        return tmp


    def run_specific(self, filepath):
        if not isinstance(filepath, string_types):
            raise AnsibleOptionsError(
               "filter param 'filepath' must be a string, but given value"\
               " '{}' has type '{}'".format(filepath, type(filepath))
            )

        endings = self.get_taskparam('endings')

        if endings:
            ## if we got an explicit set of endings, 
            ## remove exactly them if matching, or do nothin

            ## note: dont do recursive chenanigans, 
            ## just plain simple first match wins
            for fe in endings:
                fe = '.' + fe
                if filepath.endswith(fe):
                    return filepath[: -len(fe)]

            return filepath

        ## on default remove the ending(s) specified by count
        ec = self.get_taskparam('count')
        tmp = filepath.split('.')

        return '.'.join(tmp[:-ec])


##
## takes any path as input and return a list including the path and
## all its parent paths sorted top down, for example:
##
##   input == 'foo/bar/baz' => result:
##     [foo, foo/bar, foo/bar/baz]
##
##   input == '/etc' => result:
##     [/, /etc]
##
class ExplodePathFilter(FilterBase):

    FILTER_ID = 'explode_path'

    @property
    def argspec(self):
        tmp = super(ExplodePathFilter, self).argspec

        tmp.update({
          'relroot': (list(string_types), ''),
        })

        return tmp

    def run_specific(self, filepath):
        if not isinstance(filepath, string_types):
            raise AnsibleOptionsError(
               "filter param 'filepath' must be a string, but given value"\
               " '{}' has type '{}'".format(filepath, type(filepath))
            )

        cp = os.path.normpath(filepath)
        res_paths = [cp]

        relroot = os.path.normpath(self.get_taskparam('relroot'))
        stop_early = False

        while True:
            nxp = os.path.normpath(os.path.dirname(cp))

            ## if an optional relative root path is given stop
            ## explosion early when reaching this root instead
            ## of the system abs root, note that this does not
            ## influence if returned paths are abs or relative
            ## which we dont modify here
            if relroot and nxp == relroot:
                stop_early = True
                break

            ## 1st condition hits for relative paths, 2nd for abs
            ## paths when we have reached "the top"
            if not nxp or nxp == cp:
                break

            cp = nxp
            res_paths.append(cp)

        if relroot and not stop_early:
            raise AnsibleFilterError(
               "Failed to match given relative root path '{}' to a"\
               " parent of given exploding path '{}'. Check if your"\
               " input paths are correct.".format(relroot, filepath)
            )

        return list(reversed(res_paths))


# ---- Ansible filters ----
class FilterModule(object):
    ''' file path related filters '''

    def filters(self):
        res = {}

        for f in [StripFileEndingsFilter, ExplodePathFilter]:
            res[f.FILTER_ID] = f()

        return res

