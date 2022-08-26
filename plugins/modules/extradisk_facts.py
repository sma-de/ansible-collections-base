#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2021, SMA Solar Technology
# BSD 3-Clause Licence (see LICENSE or https://spdx.org/licenses/BSD-3-Clause.html)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: extradisk_facts

short_description: Collects various extra facts about disk drives not handled by standard fact collector

version_added: "1.0.0"

description: |-
  Adds additional facts about disks not handled by standard fact
  collector like gpt part label. Expects standard fct collection
  run before and relies on its results as basis for its own
  exploration. Currently implemented extra facts:

    - gpt part label
    - gpt part uuid

  Note that it only supports linux atm but it is safe to call
  for other systems (where it simply does nothing)


options:
  facts_device_links:
    description: >-
      Previously gathered device links facts.
    required: true
    type: dict
  facts_devices:
    description: >-
      Previously gathered devices facts.
    required: true
    type: dict


author:
    - Mirko Wilhelmi (@yourGitHubHandle)
'''

# TODO: github handle
EXAMPLES = r'''
- name: Return extra disk facts
  smabot.base.extradisk_facts:
    facts_device_links: ansible_facts.device_links
    facts_devices: ansible_facts.devices
'''


RETURN = r'''
ansible_facts:
  description: The facts we will set.
  returned: always
  type: dict
  contains:
    device_links:
      description: device links py part label and/or part uuid
      type: dict
      returned: always
      sample:
        part_labels:
          sda1: "example_partlabel"
        part_uuids:
          sda1: "56a5dd0a-b80f-45ec-bcc8-8f28cb89e2ef"
    devices:
      description: extra device infos added to device mapping
      type: dict
      returned: always
      sample:
        sda:
          partitions:
            sda1:
              links:
                part_label: "example_partlabel"
                part_uuid: "56a5dd0a-b80f-45ec-bcc8-8f28cb89e2ef"
'''

##import collections
##import os
import platform
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.facts.hardware.linux import LinuxHardware



class ExtraDiskFactCollector(AnsibleModule):

    def run(self, result):
        if platform.system().lower() != 'linux':
            # we only support linux atm, for other systens
            # simply return immediatelly and do nothing
            return result

        lnhw = LinuxHardware(self)

        devlinks = self.params['facts_device_links']
        device_facts = self.params['facts_devices']

        # handle extra device link types
        partx_cfg = {
          'part_label': 'by-partlabel',
          'part_uuid': 'by-partuuid',
        }

        for k, v in partx_cfg.items():
            for kk, vv in lnhw.get_device_links("/dev/disk/{}".format(v)).items():
                if len(vv) != 1:
                    self.fail_json(
                       "{} must be unique, but found '{}': {}".format(
                         k, len(vv), vv
                       ), **result
                    )

                vv = vv[0]

                # add it to device links
                tmp = devlinks.setdefault(k + 's', {})
                tmp[kk] = vv

                # add it to devices
                regex = r'(\D+)\d+'
                device =  re.fullmatch(regex, kk)

                if not device:
                    self.fail_json(
                       "Expected partition name did not match"\
                       " its regex ('{}'): '{}'".format(regex, kk), **result
                    )

                device = device.group(1)
                tmp = device_facts[device]['partitions'][kk].setdefault('links', {})
                tmp[k] = vv

        return {
          'device_links': devlinks,
          'devices': device_facts,
        }


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
      facts_device_links=dict(
        required=True, type=dict
      ),
      facts_devices=dict(
        required=True, type=dict
      ),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
       changed=False,
       ansible_facts=dict(),
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = ExtraDiskFactCollector(
       argument_spec=module_args,
       supports_check_mode=True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    result['ansible_facts'] = module.run(result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)



def main():
    run_module()



if __name__ == '__main__':
    main()

