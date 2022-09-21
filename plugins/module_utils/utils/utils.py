#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import collections

from ansible.errors import AnsibleAssertionError
from ansible.module_utils.six import string_types


##LAZYTEMPLATE_START = '{!'
##LAZYTEMPLATE_END = '!}'


## TODO: complete list
ANSRET_DEFFIELDS = [
  'changed',
  'invocation',
]


def ansible_assert(condition, error_msg):
    if not condition:
        raise AnsibleAssertionError(error_msg)


##def handle_lazy_templates(val, templater):
##    if not isinstance(val, string_types):
##        return val
##
##    if not val.startswith(LAZYTEMPLATE_START):
##        return val
##
##    if not not val.endswith(LAZYTEMPLATE_END):
##        return val
##
##    ## if we find a lazy template, make it now a real 
##    ## template, and template it
##    val = '{{' + val[len(LAZYTEMPLATE_START):len(LAZYTEMPLATE_END)] + '}}'
##    return templater.template(val)


def detemplate(val, templater):
    from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import template_recursive

    ##val = handle_lazy_templates(val, templater)

    if isinstance(val, (collections.abc.Mapping, list)):
        return template_recursive(val, templater)

    val = templater.template(val)

    if isinstance(val, (collections.abc.Mapping, list)):
        return template_recursive(val, templater)

    return val


##
## expects a dict like returned by an ansible module and removes ansible standard fields like changed from it
##
def remove_ansible_defret_vals(retmap):
    ansdef = {}

    for x in ANSRET_DEFFIELDS:
        if x not in retmap:
            continue

        ansdef[x] = retmap.pop(x)

    return (retmap, ansdef)

