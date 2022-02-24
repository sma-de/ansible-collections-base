
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

##
## find all versions existing on a maven repo server for a given artifact
##

import collections


from ansible.errors import AnsibleOptionsError

from ansible.module_utils.six import string_types
##from ansible.plugins.lookup import LookupBase
from ansible.module_utils._text import to_native, to_text
from ansible.utils.display import Display
from ansible.module_utils.six import iteritems

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.base.plugins.module_utils.plugins.lookup_base import BaseLookup


display = Display()


class LookupModule(BaseLookup):

    @property
    def argspec(self):
        tmp = super(LookupModule, self).argspec

        tmp.update({
          # on default query against maven central
          'repo_urls': ([list(string_types)], ['https://repo1.maven.org/maven2/']),
          'mapkey': (list(string_types), ''),
          'qualifiers': ([bool], True),
        })

        return tmp


    def run_specific(self, terms):
        from pymaven.client import MavenClient

        # each term is expected to describe an version incomplete
        # maven artifact coordinate description for which we will
        # query give repo url for all matching versions

        repos = self.get_taskparam('repo_urls')
        mapkey = self.get_taskparam('mapkey')
        qualifiers = self.get_taskparam('qualifiers')

        mc = MavenClient(*repos)

        res = []
        for t in terms:

            if isinstance(t, collections.abc.Mapping):
                # as pymaven internally only handles string description
                # of coordinates, we need to convert them here
                tmp = [t['gid'], t['aid']]  # these two are mandatory

                atype = t.get('type', None)

                if atype:
                    tmp.append(atype)

                classifier = t.get('classifier', None) or t.get('class', None)

                if classifier:
                    ansible_assert(atype,
                       "when classifier is specified, maven type"\
                       " must also be given: {}".format(t)
                    )

                    tmp.append(classifier)

                t = ':'.join(tmp)

            if t[-1] != ':':
                # to avoid issues with wrongly mapping given type or
                # classifier as version in pymaven we must make sure
                # that search coords end with ':' to "force" an empty
                # version
                t += ':'

            # query for versions matching given coordinates
            # and optionally convert them
            subres = []

            for x in mc.find_artifacts(t):
                tmp = {
                  'gid': x.group_id,
                  'aid': x.artifact_id,
                  'type': x.type,
                  'classifier': x.classifier,
                  'version': str(x.version.version),
                }

                if not qualifiers and '-' in tmp['version']:
                    # filter out versions with qualifiers
                    # as requested by caller
                    continue

                if mapkey:
                    tmp = tmp[mapkey]

                subres.append(tmp)

            if subres:
                res.append(subres)

        return res

