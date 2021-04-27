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


def ansible_assert(condition, error_msg):
    if not condition:
        raise AnsibleAssertionError(error_msg)


def detemplate(val, templater):
    from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import template_recursive

    if isinstance(val, (collections.abc.Mapping, list)):
        return template_recursive(val, templater)

    val = templater.template(val)

    if isinstance(val, (collections.abc.Mapping, list)):
        return template_recursive(val, templater)

    return val

