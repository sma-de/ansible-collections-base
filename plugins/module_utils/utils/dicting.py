#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import copy
import re

from ansible.errors import AnsibleError
from ansible.module_utils.six import string_types

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


SUBDICT_METAKEY_ANY = '<<<|||--MATCHALL--|||>>>'

SELFREF_START = '{:'
SELFREF_END = ':}'


## TODO: support other merge strats, make them settable by caller??
def merge_dicts(da, db):
    ''' TODO '''

    ## note: ansible does not like raw lib import errors, so move 
    ##   import here into function so caller can handle this more 
    ##   gracefully
    import deepmerge

    merger = deepmerge.Merger(
      # pass in a list of tuple, with the
      # strategies you are looking to apply
      # to each type.
      [
          (list, ["append"]),
          ##(collections.abc.Mapping, ["merge"])
          (dict, ["merge"])
      ],
      # next, choose the fallback strategies,
      # applied to all other types:
      ["override"],
      # finally, choose the strategies in
      # the case where the types conflict:
      ["override"]
    )

    ## important: this operation always changes first dict given as param, use copy if this is an issue
    return merger.merge(da, db)


##
## note: for some unfortunate reason inheritance breaks ansible templating, so we do it here ourselves
##
def template_recursive(mapping, templater, topmap=None):
    def handle_selfref(v, topmap):
        if not isinstance(v, string_types):
            return v

        matches = []

        for m in re.finditer(SELFREF_START + '\s*(\S*)\s*' + SELFREF_END, v):
            selfref_key = m.group(1)

            ansible_assert(selfref_key, 
               "bad self reference inside string '{}': cannot"\
               " be empty".format(v)
            )

            selfref_key = selfref_key.split('.')
            tmp = get_subdict(topmap, selfref_key)

            if isinstance(tmp, collections.abc.Mapping) \
              or isinstance(tmp, list):
                ansible_assert(not matches, 
                   "bad self reference inside string '{}': multiple self"\
                   " references inside a single value are only supported"\
                   " atm for simple types, not complex collection types"\
                   " like maps and lists".format(v)
                )

            matches.append({ 'key': m.group(0), 'replacement': tmp})

        if len(matches) == 1:
            return matches[0]['replacement']

        for m in matches:
            v = v.sub(m['key'], str(m['replacement']), v)

        return v

    if topmap is None:
        topmap = mapping

    ## TODO: also template keys like set_fact do
    is_map = isinstance(mapping, collections.abc.Mapping)

    if is_map:
        nm = {}
    else:
        nm = []  # assume list

    for v in mapping:

        if is_map:
            k = v
            v = mapping[k]

        if not isinstance(v, collections.abc.Mapping) \
        and not isinstance(v, list):
            v = handle_selfref(v, topmap)
            v = templater.template(v)

        if isinstance(v, collections.abc.Mapping) \
        or isinstance(v, list):
            v = template_recursive(v, templater, topmap=topmap)

        if is_map:
            nm[k] = v
        else:
            nm.append(v)

    return nm


def get_subdict(d, keychain, **kwargs):
    ansible_assert(SUBDICT_METAKEY_ANY not in keychain, 
      "use get_subdict only with a simple keychain with just one"
      " result, use get_subdicts instead for wildcards with"
      " multiple possible results"
    )

    d = list(get_subdicts(d, keychain, **kwargs))

    ansible_assert(len(d) == 1, 
      "get_subdict produced more than one result, this should never happen"
    )

    return d[0][0]


def get_subdicts(d, keychain, kciter=None, kcout=None, **kwargs):
    if not keychain:
        yield (d, kcout)
        return

    if not kciter:
        kcout = []
        yield from get_subdicts(d, keychain, iter(keychain), kcout, **kwargs)
        return

    nextkeys = next(kciter, None)

    if not nextkeys:
        yield (d, kcout)
        return

    if nextkeys == SUBDICT_METAKEY_ANY:
        nextkeys = d.keys()
    else:
        nextkeys = [nextkeys]

    for k in nextkeys:
        tmp = d.get(k, None)

        if tmp:
            if not isinstance(tmp, collections.abc.Mapping):
                ansible_assert(kwargs.get('allow_nondict_leaves', False),
                  "invalid subdicts keychain {}, child element of key"
                  " '{}' is not a dictionary: {}".format(keychain, k, tmp)
                )

                yield (tmp, kcout[:] + [k])
                continue

        elif kwargs.get('default_empty', False):
            tmp = {}
            d[k] = tmp
        else:
            raise KeyError(
               "invalid keychain {}, could not find"
               " subkey '{}'".format(keychain, k)
            )

        yield from get_subdicts(
          tmp, keychain, kciter, kcout[:] + [k], **kwargs
        )


def set_subdict(d, keychain, val):
    ansible_assert(keychain, "keychain cannot be empty when setting subdict")

    parent_kc = keychain[:-1]
    sd = get_subdict(d, parent_kc)

    sd[keychain[-1]] = val

    return d


def get_partdict(d, *keys, include=True):
    res = {}

    if not keys:
        res.update(d)
        return res

    if include:
        ## keys given are included
        for k in keys:
            res[k] = d[k]

        return res

    ## else: keys are excluded
    res.update(d)

    for k in keys:
        del(res[k])

    return res


def setdefault_none(d, key, defval=None, defval_fn=None):
      v = d.get(key, None)

      if v is None:
          if defval_fn:
              defval = defval_fn(defval)
          v = defval

      d[key] = v

      return v

