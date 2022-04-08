#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2021, SMA Solar Technology
# BSD 3-Clause Licence (see LICENSE or https://spdx.org/licenses/BSD-3-Clause.html)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: pip_facts

short_description: Collects various facts about python pip's avaible on target system

version_added: "1.0.0"

description: >-
  Standard ansible fact collector provides information about python itself
  on the target, but unfortunately not about pip(s) although it is similar
  important to python workflow's in general and also for ansible itself.
  So this module tries to provide a solution publishing various pip
  related information found on target as facts.

options:
    strict:
      description: >-
        If set will convert most "warning situations" (e.g.
        relative path given) to real errors.
      type: bool
      default: false
    try_paths:
      description:
        - >-
          As auto-detection might fail in specific scenarios, one
          can apply external knowledge here to seed some paths which might
          point to valid pip binaries. It is okay (on default) if in-module
          probing later reveals that a path given here does not point to a
          pip binary on target (or does not even exist).
        - If subvalue is a simple c(str) it will be used as I(name) subkey.
      type: list
      elements: str or dict
      suboptions:
        force_active:
          description:
            - >-
              By setting this you can override default detection of which
              pip should be considered "active".
            - >-
              Bear in mind, if this is set for more than one path,
              the last wins.
          type: bool
          default: false
        mandatory:
          description: >-
            On default paths which seem not to describe valid existing
            java home dirs are simply ignored. One can set this to
            signal to the module that this path should absolutely work
            and operation should immediately fail if it is not the case.
          type: bool
          default: false
        name:
          description:
            - >-
              Name / "ID" of pip to try, can either be a simple string
              like 'pip' or 'pip3' in which case remote target is searched
              for a match or a complete absolute path to a potential
              pip binary which is tried verbatim.
          type: str
          required: true

author:
    - Mirko Wilhelmi (@yourGitHubHandle)
'''

# TODO: github handle
EXAMPLES = r'''
- name: Return ansible pip facts (default configuration)
  smabot.base.pip_facts:

- name: Return ansible pip facts (strict mode, make warnings to errors)
  smabot.base.pip_facts:
    strict: yes

- name: Return ansible pip facts, help auto detecter a bit by providing some try paths
  smabot.base.pip_facts:
    try_paths:
      - /foo/bar/baz
      - name: pip3.7
        force_active: yes
        madatory: yes
      - name: /usr/local/bin/pip
        madatory: no
'''

RETURN = r'''
ansible_facts:
  description: The facts we will set.
  returned: always
  type: dict
  contains:
    pypip:
      description: pip facts about the system.
      type: dict
      returned: when one or more py pip's can be successfully detected on target system
      contains:
        installations:
          description: One or more pip(s) found on target system.
          type: list
          elements: dict
          sample:
          - - active: false
              binary: /usr/local/bin/pip
              python:
                home: /usr/local/lib/python3.10
                version:
                  major: 3
                  minor: 10
                  all: 3.10
              version: 21.2.4
              links:
                - /bin/pip
                - /usr/local/bin/pip3
            - active: true
              binary: /usr/local/bin/pip2
              python:
                home: /opt/lib/venvs/python2.7
                version:
                  major: 2
                  minor: 7
                  all: 2.7
              version: 18.0.0.0
              links: []
        active:
          description:
          - Facts about the "active" pip on remote.
          - This is a direct reference to one of the pip's in I(installations).
          type: dict
          sample:
            active: true
            binary: /usr/local/bin/pip2
            python:
              home: /opt/lib/venvs/python2.7
              version:
                major: 2
                minor: 7
                all: 2.7
            version: 18.0.0.0
            links: []
'''


import abc
import collections
import os
import re

from ansible.module_utils.basic import AnsibleModule



# TODO: regexing around in human addressed info is not really ideal, is there a better alternative???
class PipVer_Detector(abc.ABC):

    def __init__(self):
        self.pipver = None
        self.pyver = None
        self.pyhome = None


    @abc.abstractmethod
    def detect_pipver(self, verout):
        pass

    @abc.abstractmethod
    def detect_pyver(self, verout):
        pass

    @abc.abstractmethod
    def detect_pyhome(self, verout):
        pass


    def analyze_version_output(self, verout):
        verout = verout.split('\n')

        self.pipver = self.detect_pipver(verout)

        if not self.pipver:
            return False

        self.pyhome = self.detect_pyhome(verout)

        if not self.pyhome:
            return False

        self.pyver = self.detect_pyver(verout)

        if not self.pyver:
            return False

        tmp = self.pyver.split('.')
        self.pyver = {
          'combined': self.pyver,
          'major': tmp[0],
          'minor': tmp[1],
        }

        return True


    def update_pip_info(self, pip_info):
        pip_info['version'] = self.pipver
        pip_info['python'] = {
          'home': self.pyhome,
          'version': self.pyver,
        }


    @classmethod
    def from_version_output(cls, verout):
        obj = cls()

        if obj.analyze_version_output(verout):
            return obj

        return None


class PipVer_DetectorDefault(PipVer_Detector):

    def _get_match(self, verout, msgid, rgx, grpidx=1):
        line = verout[0]
        tmp = re.search(rgx, line)

        assert tmp, "Failed to detect {}: {}".format(msgid, line)
        return tmp.group(grpidx)


    def detect_pipver(self, verout):
        return self._get_match(verout,
          'pip version', r'(?i)pip\s+((\d+\.?)+)'
        )

    def detect_pyver(self, verout):
        return self._get_match(verout,
          'python version', r'(?i)\(\s*python\s+((\d+\.?)+)'
        )

    def detect_pyhome(self, verout):
        tmp = self._get_match(verout,
          'python version', r'(?i)from\s+(\S+)'
        )

        tmp = os.path.dirname(os.path.dirname(tmp))
        return tmp



pipver_detectors = [
  PipVer_DetectorDefault,
]



def find_matching_pipver_detector(verout):
    for x in pipver_detectors:
        x = x.from_version_output(verout)

        if x:
            return x

    return None



class PipFactCollector(AnsibleModule):

    def handle_warning(self, msg, result):
        strict = self.params['strict']

        if strict:
            # if strict convert warnings to real errors
            self.fail_json(msg, **result)

        self.warn(msg)


    def analyze_pip_version(self, pip_bin, pip_info, result):
        rc, stdout, stderr = self.run_command([pip_bin, '--version'])

        if rc != 0:
            self.handle_warning(
               "Trying to query the version from pip binary '{}' failed"\
               " with rc '{}':\n{}".format(pip_bin, rc, stderr), result
            )

            return False

        tmp = find_matching_pipver_detector(stdout)

        if not tmp:
            self.handle_warning(
               "Could not find a matching pip version detector for raw"\
               " version output:\n{}".format(stdout), result
            )

            return False

        tmp.update_pip_info(pip_info)
        return True


    def _check_duplicate(self, handled_pips, np):
        np_binset = set(np['links'] + [np['binary']])

        for hp in handled_pips:
            hp_binset = set(hp['links'])

            # check if both point to same python home
            if os.path.samefile(hp['python']['home'], np['python']['home']):
                hp['links'] = list(hp_binset | np_binset)
                return True

            # check if binaries match somewhere
            for n1 in hp['links'] + [hp['binary']]:
                for n2 in np_binset:
                    if os.path.samefile(n1, n2):
                        hp['links'] = list(hp_binset | np_binset)
                        return True

        return False


    def run(self, result):
        all_tries = [
          'pip', 'pip2', 'pip3'
        ] + (self.params['try_paths'] or [])

        handled_pips = []
        active_pip = None
        pip_installs = []
        default_active_candidates = []

        for x in all_tries:
            if not isinstance(x, collections.abc.Mapping):
                x = {'name': x, 'mandatory': False, 'force_active': False}

            name = x['name']
            mandatory = x['mandatory']

            links = []

            if name[0] == '/':
                # use name as binary path
                binary = name
            else:
                # try to find matching binary in $PATH
                binary = self.get_bin_path(name)

                if not binary:
                    if not mandatory:
                        continue

                    self.fail_json(
                       "Failed to find matching binary to mandatory"\
                       " pip try name '{}'".format(name), **result
                    )

            # note their is a good chance that this is a symbolic
            # link, so make sure to resolve all links here
            tmp = binary
            binary = os.path.realpath(binary)

            if tmp != binary:
                links.append(tmp)

            # check if binary path exists
            if not os.path.isfile(binary):
                if mandatory:
                    self.fail_json(
                       "Mandatory pip binary path does not exist '{}'"\
                       " on remote".format(binary), **result
                    )

                continue

            tmp = {
              'binary': binary, 'active': x.get('force_active', False),
              'links': links
            }

            if not self.analyze_pip_version(binary, tmp, result):
                continue

            really_new = not self._check_duplicate(handled_pips, tmp)

            # x is just another description of an
            # already handled path, so we will skip it
            if not really_new:
                continue

            if not active_pip:
                # do active pip defaulting
                for n in tmp['links'] + [binary]:
                    if os.path.basename(n) == 'pip':
                        # if we have a binary which is simply called
                        # pip, this is definetly a candidate for
                        # default active
                        default_active_candidates.append(tmp)
                        break

            pip_installs.append(tmp)
            handled_pips.append(tmp)

            if tmp['active']:
                if active_pip:
                    active_pip['active'] = False

                active_pip = tmp

        if not pip_installs:
            return {}

        if not active_pip:
            # finalize default active choice, start with preselected ones,
            # if there are none, make any found binary a potential candidate
            default_active_candidates = \
              default_active_candidates or pip_installs

            # final decider, highest version wins, if they are more
            # than one with this version, simply take the last
            default_active_candidates.sort(key=lambda x: x['version'])
            active_pip = default_active_candidates[-1]
            active_pip['active'] = True

        return {
          'pypip': {
             'installations': pip_installs,
             'active': active_pip,
          }
        }



def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
      try_paths=dict(
        type='list',
      ),
      strict=dict(
        type='bool',
        default=False,
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
    module = PipFactCollector(
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

