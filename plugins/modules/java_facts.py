#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2021, SMA Solar Technology
# BSD 3-Clause Licence (see LICENSE or https://spdx.org/licenses/BSD-3-Clause.html)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: java_facts

short_description: Collects various facts about jvm(s) avaible on target system

version_added: "1.0.0"

description: >-
  Similar to how standard setup collects various facts about the 
  python environment on a target system this module tries to determine 
  stuff about one or possible more java environments installed on the 
  system. This knowledge might than prove useful in various java 
  related workflows.

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
          be valid java homes. It is okay (on default) if in-module 
          probing later reveals that a given path is not a valid java 
          home on target (or does not even exist).
        - If subvalue is a simple c(str) it will be used as I(path) subkey.
      type: list
      elements: str or dict
      suboptions:
        binary:
          description: Relative sub path to the java binary.
          type: str
          default: bin/java
        force_active:
          description:
            - >-
              By setting this you can override default detection of which
              JVM should be considered "active".
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
        path:
          description: Absolute path which might be a java home directory.
          type: str
          required: true

author:
    - Mirko Wilhelmi (@yourGitHubHandle)
'''

# TODO: github handle
EXAMPLES = r'''
- name: Return ansible java facts (default configuration)
  smabot.base.java_facts:

- name: Return ansible java facts (strict mode, make warnings to errors)
  smabot.base.java_facts:
    strict: yes

- name: Return ansible java facts, help auto detecter a bit by providing some try paths
  smabot.base.java_facts:
    try_paths:
      - /foo/bar/baz
      - path: /usr/share/java
        force_active: yes
        madatory: yes
'''

RETURN = r'''
ansible_facts:
  description: The facts we will set.
  returned: always
  type: dict
  contains:
    java:
      description: Java facts about the system.
      type: dict
      returned: when one or more JVM installations can be successfully detected on target system
      contains:
        installations:
          description: One or more JVM(s) found on target system.
          type: list
          elements: dict
          sample: 
          - - active: false
              binary: /opt/java/openjdk/bin/java
              homedir: /opt/java/openjdk
              type: UNKOWN
              version: 1.8.0_292
              build: 1.8.0_292-b10
            - active: true
              binary: /usr/local/share/java/bin/java
              homedir: /usr/local/share/java
              type: AdoptOpenJDK
              version: 1.7.0_142
              build: 1.7.0_142-b13
        active:
          description:
          - Facts about the "active" JVM on remote.
          - This is a direct reference to one of JVMs in I(installations).
          type: dict
          sample: 
            active: true
            binary: /usr/local/share/java/bin/java
            homedir: /usr/local/share/java
            type: AdoptOpenJDK
            version: 1.7.0_142
            build: 1.7.0_142-b13
'''

import abc
import collections
import os
import re

from ansible.module_utils.basic import AnsibleModule



# TODO: regexing around in human addressed info is not really ideal, is there a better alternative, like maybe running a small java program which analyze with structure, but are we guaranteed to have a java compiler on remote??
class JVM_Detector(abc.ABC):

    def __init__(self):
        self.version = None
        self.build = None
        self.type = None


    def detect_version(self, verout):
        # on default version should be relatively easy 
        # detectable on first line
        line = verout[0]
        tmp = re.findall(r'\d+\.[-_.0-9]+', line)

        assert tmp, "Failed to detect java version: {}".format(line)
        assert len(tmp) == 1, "Detected more than one java version: {}, raw: {}".format(tmp, line)

        return tmp[0]


    def detect_build(self, verout):
        # on default version should be relatively easy 
        # detectable on 2nd line
        line = verout[1]
        tmp = re.search(r'(?i)\(build\s+(\S+)\s*\)', line)

        assert tmp, "Failed to detect java build: {}".format(line)

        return tmp.group(1)


    @abc.abstractmethod
    def detect_type(self, verout):
        pass


    def analyze_version_output(self, verout):
        verout = verout.split('\n')
        self.version = self.detect_version(verout)
        self.build = self.detect_build(verout)
        self.type = self.detect_type(verout)

        ## if this detector matches the input depends 
        ## on if it recognize and can extract the type of it
        if self.type:
            return True

        return False


    def update_jvm_info(self, jvm_info):
        for x in ['version', 'build', 'type']:
            v = getattr(self, x, None)
            jvm_info[x] = v


    @classmethod
    def from_version_output(cls, verout):
        obj = cls()

        if obj.analyze_version_output(verout):
            return obj

        return None


class JVM_DetectorFallback(JVM_Detector):

    def detect_type(self, verout):
        return 'UNKOWN'


class JVM_DetectorRegexId(JVM_Detector):

    @abc.abstractmethod
    def _get_type_regex(self):
        pass

    @abc.abstractmethod
    def _get_type_id(self):
        pass

    def _get_test_line(self, verout):
        return verout[1]

    def detect_type(self, verout):
        line = self._get_test_line(verout)
        tmp = re.search(self._get_type_regex(), line)

        if tmp:
            return self._get_type_id()

        return None


## TODO: temurin seems to be the successor project of AdoptOpenJDK, should this be refected somehow in facts???
class JVM_DetectorTemurin(JVM_DetectorRegexId):

    def _get_type_regex(self):
        return r'(?i)temurin'

    def _get_type_id(self):
        return 'Temurin'


class JVM_DetectorAdoptOpenJdk(JVM_DetectorRegexId):

    def _get_type_regex(self):
        return r'(?i)adoptopenjdk'

    def _get_type_id(self):
        return 'AdoptOpenJDK'


class JVM_DetectorOpenJ9(JVM_DetectorRegexId):

    def _get_type_regex(self):
        return r'(?i)\bopenj9'

    def _get_type_id(self):
        return 'OpenJ9'

    def _get_test_line(self, verout):
        return verout[2]


jvm_detectors = [
  JVM_DetectorAdoptOpenJdk,
  JVM_DetectorOpenJ9,
  JVM_DetectorTemurin,

  ## must always be the last
  JVM_DetectorFallback
]


def find_matching_jvm_detector(verout):
    for x in jvm_detectors:
        x = x.from_version_output(verout)

        if x:
            return x

    return None



class JavaFactCollector(AnsibleModule):

    def handle_warning(self, msg, result):
        strict = self.params['strict']

        if strict:
            # if strict convert warnings to real errors
            self.fail_json(msg, **result)

        self.warn(msg)


    def analyze_java_version(self, java_bin, jvm_info, result):
        rc, stdout, stderr = self.run_command([java_bin, '-version'])

        if rc != 0:
            self.handle_warning(
               "Trying to query the version from java failed"\
               " with rc '{}':\n{}".format(rc, stderr), result
            )

            return False

        tmp = find_matching_jvm_detector(stderr)

        if not tmp:
            self.handle_warning(
               "Could not find a matching JVM detector for raw"\
               " version output:\n{}".format(stderr), result
            )

            return True

        tmp.update_jvm_info(jvm_info)
        return True


    def run(self, result):
        all_homes = [] + (self.params['try_paths'] or [])

        # check typical java_home envvar
        home_from_env = os.environ.get('JAVA_HOME', None)

        if home_from_env:

            if not os.path.isdir(home_from_env):
                self.handle_warning(
                   "The path $JAVA_HOME envvar points to is not an existing"\
                   " directory on target: {}".format(home_from_env), result
                )

            else:
                all_homes.insert(0, 
                  {'path': home_from_env, 'mandatory': True}
                )

        # check for java binary on path
        home_from_path = self.get_bin_path('java')

        if home_from_path:
            # note their is a good chance that this is a symbolic
            # link, so make sure to resolve all links here
            # 
            # TODO: should we add binary symlinks to our facts return ??
            home_from_path = os.path.realpath(home_from_path)

            # java binary should be here: $JAVA_HOME/bin/java
            # so going up two times should give us home
            home_from_path = os.path.dirname(os.path.dirname(home_from_path))
            use_this_home = not home_from_env

            if home_from_env:
                if not os.path.samefile(home_from_env, home_from_path):
                    use_this_home = True
                    self.handle_warning(
                       "The java homedir where $JAVA_HOME environment"\
                       " variable points to differs from the java homedir"\
                       " where java binary from $PATH resides in"\
                       " ('{}' != '{}'). This seems fishy.".format(
                           home_from_env, home_from_path
                    ), result)

            if use_this_home:
                # 
                # note: normally, when both home_from_path and 
                #   home_from_env are set, they are expected 
                #   to point to the same directory, if not 
                #   prefer binary home over env home as 
                #   "active" jvm
                # 
                all_homes.insert(0, 
                  {'path': home_from_path, 'mandatory': True}
                )

        # go through all java homedirs and collect facts about them, 
        # note that orders matter here, as the first "working" 
        # homedir is used as active one
        handled_homes = []
        active_home = None
        j_installs = []

        for h in all_homes:
            really_new = True

            if not isinstance(h, collections.abc.Mapping):
                h = {'path': h}

            hp = h['path']
            mandatory = h.get('mandatory', False)

            if not os.path.isabs(hp):
                msg = "Paths must be absolute, so we will skip relative"\
                      " java home test path: '{}'".format(hp)

                if mandatory:
                    self.fail_json(msg, result)

                self.handle_warning(msg, result)
                continue

            # check home path for defects
            if not os.path.isdir(hp):
                if mandatory:
                    self.fail_json(
                       "Tested mandatory java home dir '{}' is"\
                       " not an existing directory on remote".format(hp), 
                       **result
                    )

                # when paths are non mandatory just silently skip them
                continue

            for x in handled_homes:
                if os.path.samefile(x['path'], hp):
                    really_new = False
                    break

            # h is just another description of an 
            # already handled path, so we will skip it
            if not really_new:
                continue

            jbin_path = os.path.join(hp, h.get('binary', 'bin/java'))

            if not os.path.isfile(jbin_path):
                if mandatory:
                    self.fail_json(
                       "Mandatory java home dir '{}' seems to be missing"\
                       " java binary, expected path: {}".format(
                         hp, jbin_path
                       ), **result
                    )

                continue

            # check if this java env contains a compiler
            # (is a jdk) or not (is a jre)
            jbin_comp = os.path.join(hp, h.get('compiler', 'bin/javac'))
            if not os.path.isfile(jbin_comp):
                jbin_comp = None

            tmp = {
              'homedir': hp, 'binary': jbin_path, 'active': False,
              'compiler': jbin_comp
            }

            if not self.analyze_java_version(jbin_path, tmp, result):
                continue

            j_installs.append(tmp)

            handled_homes.append(h)

            if not active_home or h.get('force_active', False):
                if active_home:
                    active_home['active'] = False

                active_home = tmp
                tmp['active'] = True

        if not j_installs:
            return {}

        return {
          'java': {
             'installations': j_installs,
             'active': active_home,
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
    module = JavaFactCollector(
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

