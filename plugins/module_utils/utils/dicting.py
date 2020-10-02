#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections


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
def template_recursive(mapping, templater):
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

        v = templater.template(v)

        if isinstance(v, collections.abc.Mapping) \
        or isinstance(v, list):
            v = template_recursive(v, templater)

        if is_map:
            nm[k] = v
        else:
            nm.append(v)

    return nm

