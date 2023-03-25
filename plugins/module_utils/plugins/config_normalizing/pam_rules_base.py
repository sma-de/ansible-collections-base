
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, NormalizerBase, NormalizerNamed, DefaultSetterConstant

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, merge_dicts, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible.utils.display import Display


display = Display()


## different distros use diffrent name schemes for pam files,
## add overwrites here when necessary
DISTRO_PAMFILE_OVERWRITES = {
  ##"distro name as returned by ansible_distribution": "pam-file-name"
  ## TODO: fill when suporting another distro
}


##
## properly naming this method is a bit tricky, technically it does not
## order the given python object list, quite contrary it expect it to
## be in the correct final order, what it does is updating the object
## keys so that upstream pamd module will create correctly ordered
## pamd entries for the given list
##
def order_pamrules_list(rules, pamfile, pre_rule=None, post_rule=None,
    front_to_back=True, enabled=True
):
    ansible_assert(not(pre_rule and post_rule),
       "Either give a pre_rule or a post_rule or none of"\
       " them, but never both together"
    )

    startpos = 0

    ## pre and post rules imply ordering directions
    if pre_rule:
        startpos = 1
        front_to_back = True
        rules = [pre_rule] + rules

    elif post_rule:
        startpos = 1
        front_to_back = False
        rules = rules + [post_rule]

    defstate = 'after'

    if not front_to_back:
        defstate = 'before'
        rules = list(reversed(rules))

    i = startpos
    for r in rules[startpos:]:
        display.vvv(
           "[order_pamrules_list] => iterate rule[{}]: {}".format(i, r)
        )

        state = r.get('state', defstate)

        if not enabled:
            state = 'absent'

        r['name'] = pamfile
        r['state'] = state

        nr = copy.deepcopy(r)
        nr.pop('refrule', None)

        nr['new_type'] = r['type']
        nr['new_control'] = r['control']
        nr['new_module_path'] = r['module_path']

        if state != 'absent':
            tmp = r.pop('refrule', None)

            display.vvv(
               "[order_pamrules_list] => find refrule: {}".format(tmp)
            )

            if not tmp:
                j = i - 1

                display.vvv(
                   "[order_pamrules_list] => no explicit refrule given,"\
                   " default to next previous non absentee rule, start"\
                   " search with index '{}'".format(j)
                )

                while True:
                    if j < 0:
                        ## if neither post or pre rule is given, simply put first
                        ## rule of give list to the end of given pam file (append)
                        ## if new, if it already exist it will keep its current position
                        r['state'] = 'updated'
                        nr = None
                        break

                    tmp = rules[j]
                    if tmp.get('state', '') != 'absent':
                        break

                    j -= 1

            if nr:
                nr['type'] = tmp.get('new_type', tmp['type'])
                nr['control'] = tmp.get('new_control', tmp['control'])
                nr['module_path'] = tmp.get('new_module_path', tmp['module_path'])

                merge_dicts(r, nr)

        i += 1

    ## dont forget to remove reference only pre/post rule again
    if pre_rule or post_rule:
        rules = rules[1:]

    return rules


class PamRulesNormer(NormalizerBase):

    @property
    def config_path(self):
        return ['pam_rules']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pamfile_default = DISTRO_PAMFILE_OVERWRITES.get(
           self.pluginref.get_ansible_var('ansible_distribution'),
           'common-auth' # current default is based on modern ubuntu
        )

        setdefault_none(my_subcfg, 'pamfile', pamfile_default)
        return my_subcfg

