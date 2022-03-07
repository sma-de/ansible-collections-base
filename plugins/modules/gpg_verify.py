#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2021, SMA Solar Technology
# BSD 3-Clause Licence (see LICENSE or https://spdx.org/licenses/BSD-3-Clause.html)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: gpg_verify

short_description: verifies a given file with a given signature

version_added: "1.0.0"

description: >-
  TODO (based on gnu-pg [gpg])

## TODO: all key management related code (fingerprint to key, import key, ...) should be made common util code so that it can be reused for other related modules (gpg_import, ...)

options:
    key:
      description:
        - Public key used for verification
        - Mutually exclusive with I(fingerprint)
        - If you work with a pre existing gnupg home which already have all necessary keys installed, this can be omitted
      type: str
    fingerprint:
      description:
        - Public key fingerprint used for verification, if necessary the corresponding key will be imported from a keyserver
        - Mutually exclusive with I(key)
        - If you work with a pre existing gnupg home which already have all necessary keys installed, this can be omitted
      type: str
    keyservers:
      description: >-
        List of keyservers to query for fingerprints. Normally not expected to be necessary to set.
      type: list
      elements: str
      default: ['ha.pool.sks-keyservers.net', 'hkp://p80.pool.sks-keyservers.net:80', 'keyserver.ubuntu.com', 'hkp://keyserver.ubuntu.com:80', 'pgp.mit.edu']
    file:
      description: >-
        Absolute path to an existing file on remote which should be checked / verified
      type: path
      required: true
    sigfile:
      description:
        - signature file to use
        - for non detached scenarios (your file to check contains the signature) either give the same value here as for I(file) or the special magic value c("inplace")
        - can also be an url instead of a remote file path
      type: str
      default: /path/to/file-to-check.asc
    tmphome:
      description:
        - If this is set this module will use a tmpdir as gnu home, where only the explicitly imported key is valid and which will be deleted after this call
        - I(gpghome) is ignored when I(tmphome) is active
      type: bool
      default: true
    gpghome:
      description:
        - Specify a path to an existing gnu home to use as trust base
        - If not set will try to determine gpghome from environment
        - Totally ignored when I(tmphome) is set, but must point to a valid gpghome path when I(tmphome) is unset or an error will be generated
      type: path
      default: envvar
    proxy:
      description:
        - Set a proxy for communicating with keyservers
        - Defaults to envvar c($HTTP_PROXY)
      type: str
      default: envvar

author:
    - Mirko Wilhelmi (@yourGitHubHandle)
'''

# TODO: github handle
EXAMPLES = r'''
- name: verify remote file with default settings (assuming necessary keys pretrusted)
  smabot.base.gpg_verify:
    file: /foo/bar/baz.zip

- name: verify remote file with key to import from fingerprint and signatur to download
  smabot.base.gpg_verify:
    fingerprint: <KEY-FINGERPRINT>
    file: /foo/bar/baz.zip
    sigfile: https://url-to-sig

- name: like example above but forcing a keyserver
  smabot.base.gpg_verify:
    fingerprint: <KEY-FINGERPRINT>
    file: /foo/bar/baz.zip
    sigfile: https://url-to-sig
    keyservers:
      - url-to-my-prefered-keyserver

- name: use mostly standard settings and a predefined gpghome with needed keys already contained
  smabot.base.gpg_verify:
    file: /foo/bar/baz.zip
    tmphome: false

- name: like example above but explicitly give a path to gpghome to use
  smabot.base.gpg_verify:
    file: /foo/bar/baz.zip
    gpghome: /usr/share/local/my-gpghome
'''

## TODO
## RETURN = r'''
## ansible_facts:
##   description: The facts we will set.
##   returned: always
##   type: dict
##   contains:
##     java:
##       description: Java facts about the system.
##       type: dict
##       returned: when one or more JVM installations can be successfully detected on target system
##       contains:
##         installations:
##           description: One or more JVM(s) found on target system.
##           type: list
##           elements: dict
##           sample: 
##           - - active: false
##               binary: /opt/java/openjdk/bin/java
##               homedir: /opt/java/openjdk
##               type: UNKOWN
##               version: 1.8.0_292
##               build: 1.8.0_292-b10
##             - active: true
##               binary: /usr/local/share/java/bin/java
##               homedir: /usr/local/share/java
##               type: AdoptOpenJDK
##               version: 1.7.0_142
##               build: 1.7.0_142-b13
##         active:
##           description:
##           - Facts about the "active" JVM on remote.
##           - This is a direct reference to one of JVMs in I(installations).
##           type: dict
##           sample: 
##             active: true
##             binary: /usr/local/share/java/bin/java
##             homedir: /usr/local/share/java
##             type: AdoptOpenJDK
##             version: 1.7.0_142
##             build: 1.7.0_142-b13
## '''

import collections
import os

from ansible.module_utils.basic import AnsibleModule

from ansible.module_utils.common.parameters import env_fallback

from ansible.module_utils.errors import ArgumentValueError
from ansible.module_utils.urls import fetch_file



DEFAULT_KEYSERVERS = [
  'hkp://keys.gnupg.net',
  'ha.pool.sks-keyservers.net',
  'hkp://p80.pool.sks-keyservers.net:80',
  'keyserver.ubuntu.com',
  'hkp://keyserver.ubuntu.com:80',
  'pgp.mit.edu',
]



def recv_keys_patched(self, keyserver, *keyids, server_opts=None, mod=None):
    import gnupg

    # note: most of this is copy & pasted from upstream module
    result = self.result_map['import'](self)
    ##logger.debug('recv_keys: %r', keyids)
    data = gnupg._make_binary_stream('', self.encoding)
    ## <patch start> ##
    args = ['--keyserver', gnupg.no_quote(keyserver)]
    if server_opts:
        args.extend(['--keyserver-options', ' '.join(server_opts)])
    args.append('--recv-keys')
    ## <patch end> ##
    args.extend([gnupg.no_quote(k) for k in keyids])
    self._handle_io(args, data, result, binary=True)
    ##logger.debug('recv_keys result: %r', result.__dict__)
    data.close()
    return result



class ClientGPG():

    def __init__(self, module,
        home=None, encoding=None, keyservers=None, proxy=None,
        tmphome=False, tmpdir_root=None, server_opts=None
    ):
        if tmphome:
            home = os.path.join(tmpdir_root, 'gpghome')
            os.mkdir(home)
        elif not home:
            raise ArgumentValueError(
               "Either set tmphome or explicitly specify"\
               " a gnupg home dir to use"
            )

        self.tmphome = tmphome

        self.home = home
        self.encoding = encoding or 'utf-8'
        self.keyservers = keyservers or DEFAULT_KEYSERVERS

        if proxy:
            server_opts = server_opts or {}
            tmp = server_opts.setdefault('all', {})
            tmp['http-proxy'] = proxy

        self.server_opts = server_opts

        self.module = module
        self._client = None


    @property
    def client(self):
        if not self._client:
            self._client = self.init_client()

        return self._client


    def init_client(self):
        import gnupg

        # monkey patch upstream class (TODO: fix it upstream and remove this)
        gnupg.GPG.recv_keys = recv_keys_patched

        gpg = gnupg.GPG(gnupghome=self.home)

        if self.encoding:
            gpg.encoding = self.encoding

        return gpg


    def find_keys_in_home(self, keys=None, fingerprints=None):
        assert not keys or not fingerprints,\
            "either look for keys or key fingerprints,"\
            " not both at the same time"

        kwargs = {}

        if keys or fingerprints:
            # TODO: what exactly is matched here, does it work for fingerprints too??
            kwargs['keys'] = keys or fingerprints

        res = self.client.list_keys(**kwargs)

        if not res:
            return res

        if fingerprints:
            if not isinstance(fingerprints, list):
                fingerprints = [fingerprints]

            tmp = []

            for fp in fingerprints:
                tmp.append(res['key_map'][fp])

            res = tmp

        return res


    def _get_server_opts(self, server):
        tmp = self.server_opts

        if not tmp:
            return []

        tmp = {}

        # get generic server opts valid for all servers (optional)
        tmp.update(self.server_opts.get('all', {}))

        # get server specific server opts (optional)
        tmp.update(self.server_opts.get(server, {}))

        res = []
        for k,v in tmp.items():
            res.append("{}={}".format(k,v))

        return res


    def import_from_fingerprints(self, *fingerprints,
        fail_for_unhandled=True, result=None
    ):
        fp_todo = set(fingerprints)
        fpadded = set()

        for ks in self.keyservers:
            self.module.log(
              "Trying to obtain keys from keyserver '{}' for the"\
              " following fingerprints: {}".format(ks, fp_todo)##, lvl=2
            )

            try:
                res = self.client.recv_keys(ks, *fp_todo,
                  server_opts=self._get_server_opts(ks), mod=self.module
                )

                self.module.log("Result from keyserver: {}".format(res.summary()))

                if res.count > 0:
                    tmp = set(res.fingerprints)
                    fpadded |= tmp
                    fp_todo -= tmp

                if not fp_todo:
                    break  # all fingerprints done, op done

            except Exception as e:
                # note: connecting to keyservers is notoriously unreliable, dont let a single key server not working mess up the operation
                # TODO: logging, other stuff todo here???
                self.module.log("Failed to query keyserver: {}".format(str(e)))
                ##self.module.warn("da keyserver exception => " + str(e))

        if fail_for_unhandled and fp_todo:
            self.module.fail_json(
               msg="Failed to obtain the keys for the following"\
               " fingerprints from any of this keyservers"\
               " '{}': {}".format(self.keyservers, fp_todo), **result
            )

        # TODO: maybe it would be better here to get more familiar with type returned by gnupg here and figure out how to merge them
        tmp = collections.namedtuple("ImportRes", "count fingerprints")
        return tmp(len(fpadded), fpadded)



class VerifyGPG(AnsibleModule):

    def run(self, result):
        tmphome = self.params['tmphome']

        # create gpg client with home
        client = ClientGPG(self, home=self.params['gpghome'],
           tmphome=tmphome,
           keyservers=self.params['keyservers'],
           proxy=self.params['proxy'],
           tmpdir_root=self.tmpdir,
        )

        # when necessary get and import key
        key = self.params['key']
        fp = self.params['fingerprint']

        # TODO: this whole key is new stuff should propbably be also part of the more generic and sharable client
        key_is_new = True

        if key or fp:
            res = client.find_keys_in_home(keys=key, fingerprints=fp)
            key_is_new = not bool(res)

        added_keys = []

        if key_is_new:
            # there is no real sense in marking this module as having
            # changed something when we use a tmphome as we only change
            # stuff inside pghome dir, and tmphome's are deleted after
            # this call
            result['changed'] = not tmphome

            if key:
                added_keys = client.client.import_keys(key).fingerprints
            else:
                added_keys = client.import_from_fingerprints(
                  fp, result=result
                ).fingerprints

        result['keys_added'] = added_keys

        # handle actual verification
        file_to_verify = self.params['file']
        sigfile = self.params['sigfile']

        inplace_sig = file_to_verify == sigfile or sigfile == 'inplace'
        vertype = 'detached'

        if inplace_sig:
            # verify
            vertype = 'inplace'
            real_sigfile = file_to_verify

            with open(file_to_verify, 'rb') as f:
                verified = client.client.verify_file(f, close_file=False)
        else:
            import validators

            sigfile = sigfile or (file_to_verify + '.asc')
            real_sigfile = sigfile

            # when necessary download sigfile
            if validators.url(sigfile):
                sigfile = fetch_file(self, sigfile)

            # verify
            if not os.path.isfile(sigfile):
                self.fail_json(
                   msg="failed to verify given file as determined"\
                       " signature file '{}' does not exists".format(sigfile),
                   **result
                )

            with open(sigfile, 'rb') as f:
                verified = client.client.verify_file(
                  f, file_to_verify, close_file=False
                )

        gpg_ok = bool(verified)

        result['verified'] = gpg_ok
        result['verification_type'] = vertype
        result['signature_file'] = real_sigfile
        result['verification_details'] = verified.sig_info

        # fail this module run when not verified
        if not gpg_ok:
            self.fail_json(
               msg='failed to verify given file with given signature',
               **result
            )



def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
      key=dict(
        type='str',
      ),
      fingerprint=dict(
        type='str',
        default=False,
      ),
      keyservers=dict(
        type='list',
        elements='str',
      ),
      file=dict(
        type='path',
        required=True,
      ),
      sigfile=dict(
        type='str',
      ),
      tmphome=dict(type='bool',
        default=True,
      ),
      gpghome=dict(type='path',
        fallback=(env_fallback, ['GNUPGHOME'])
      ),
      proxy=dict(type='str',
        fallback=(env_fallback, ['HTTP_PROXY'])
      ),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
      changed=False,
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = VerifyGPG(
      argument_spec=module_args,
      mutually_exclusive=[
        ('key', 'fingerprint'),
      ],
      required_if=[
        ('tmphome',  True, ('key', 'fingerprint'), True),
        ('tmphome', False, ('gpghome')),
      ],
      supports_check_mode=False # TODO: make this True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    module.run(result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)



def main():
    run_module()



if __name__ == '__main__':
    main()

