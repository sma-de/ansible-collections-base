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


MAPKEY_UNSET = object()


## TODO: support other merge strats, make them settable by caller??
def merge_dicts(da, db, strats_fallback=None):
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
      strats_fallback or ["override"],
      # finally, choose the strategies in
      # the case where the types conflict:
      ["override"]
    )

    ## important: this operation always changes first dict given as param, use copy if this is an issue
    return merger.merge(da, db)


##
## note: for some unfortunate reason inheritance breaks ansible templating, so we do it here ourselves
##
def template_recursive(mapping, templater,
    topmap=None, keychain=None, newmap=None,
    new_parent=None
):
    def handle_selfref(v, topmap, keychain, newmap):
        if not isinstance(v, string_types):
            return v

        matches = []
        obj = False

        for m in re.finditer(SELFREF_START + r'\s*(\S*)\s*' + SELFREF_END, v):
            selfref_key = m.group(1)

            ansible_assert(selfref_key, 
               "bad self reference inside string '{}': cannot"\
               " be empty".format(v)
            )

            selfref_key = selfref_key.split('.')

            if not selfref_key[0]:
                # key is relative to current position (technically
                # current key path parent, as self referencing one
                # self does not really make sense in this context
                # as we are replacing the content of current key)
                tmp = keychain[:-1]

                for k in selfref_key[1:]:
                    # when key part is a set value, append it to final
                    # refkey, it is empty, this means we go one up
                    # relative to current pos (like for relative python
                    # lib imports)
                    if k:
                        tmp.append(k)
                    else:
                        tmp.pop()

                selfref_key = tmp

            try:
                ## first check newmap if it already contains selfref_key
                ## to get the latest iteration of the value in question
                tmp = get_subdict(newmap, selfref_key,
                   allow_nondict_leaves=True
                )
            except KeyError:
                ## if selfref_key was not yet handled and as such is
                ## not already in newmap fallback to "old" topmap
                tmp = get_subdict(topmap, selfref_key,
                   allow_nondict_leaves=True
                )

            if isinstance(tmp, collections.abc.Mapping) \
              or isinstance(tmp, list):
                ansible_assert(not matches, 
                   "bad self reference inside string '{}': multiple self"\
                   " references inside a single value are only supported"\
                   " atm for simple types, not complex collection types"\
                   " like maps and lists".format(v)
                )

                obj = True

            matches.append({ 'key': m.group(0), 'replacement': tmp})

        if obj:
            return matches[0]['replacement']

        for m in matches:
            v = re.sub(m['key'], str(m['replacement']), v)

        return v

    ## TODO: also template keys like set_fact does
    is_map = isinstance(mapping, collections.abc.Mapping)

    if topmap is None:
        topmap = mapping

        if is_map:
            newmap = {}
        else:
            newmap = []

        new_parent = newmap
        keychain = []

    i = 0
    for v in mapping:

        k = i

        if is_map:
            k = v
            v = mapping[k]

        keychain.append(k)

        # template non-complex values
        if not isinstance(v, collections.abc.Mapping) \
        and not isinstance(v, list):
            v = handle_selfref(v, topmap, keychain, newmap)
            v = templater.template(v)

        # recurse down complex aka collection values, must happen
        # after templating as templating might convert a simple
        # values to a collection one
        is_submap = isinstance(v, collections.abc.Mapping)
        if is_submap or isinstance(v, list):
            if is_submap:
                nm = {}
            else:
                nm = []  # assume list

            if is_map:
                new_parent[k] = nm
            else:
                new_parent.append(nm)

            template_recursive(v, templater,
              topmap=topmap, keychain=keychain, newmap=newmap,
              new_parent=nm
            )

        else:
            if is_map:
                new_parent[k] = v
            else:
                new_parent.append(v)

        keychain.pop()
        i += 1

    return newmap


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
    ansible_assert(isinstance(d, collections.abc.Mapping), 
       "invalid input param d for keychain {}, it must be a mapping,"\
       " but was of type '{}': {}".format(keychain, type(d), d)
    )

    if not keychain:
        yield (d, kcout)
        return

    if kciter is None:
        kcout = []
        yield from get_subdicts(d, keychain,
          list(keychain[:]), kcout, **kwargs
        )

        return

    if not kciter:
        yield (d, kcout)
        return

    nextkeys = kciter.pop(0)

    if nextkeys == SUBDICT_METAKEY_ANY:
        nextkeys = list(d.keys())
    else:
        nextkeys = [nextkeys]

    for k in nextkeys:
        tmp = d.get(k, MAPKEY_UNSET)
        key_empty = False

        if tmp is MAPKEY_UNSET:
            key_empty = True
        else:
            key_empty = tmp in (kwargs.get('empty_vals', [None]) or [])

        if key_empty:

            if kwargs.get('default_empty', False):
                tmp = kwargs.get('default_value', {})

                if kwargs.get('default_update', True):
                    d[k] = tmp

            elif kwargs.get('ignore_empty', False):
                continue

            else:
                raise KeyError(
                   "invalid keychain {}, could not find"
                   " subkey '{}'".format(keychain, k)
                )

        if not isinstance(tmp, collections.abc.Mapping):
            ansible_assert(kwargs.get('allow_nondict_leaves', False),
              "invalid subdicts keychain {}, child element of key"
              " '{}' is not a dictionary: {}".format(keychain, k, tmp)
            )

            yield (tmp, kcout[:] + [k])
            continue


        yield from get_subdicts(tmp,
          keychain, kciter[:], kcout[:] + [k], **kwargs
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


def transpose_map(mapping):
    return dict((v, k) for k, v in mapping.items())


class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'

