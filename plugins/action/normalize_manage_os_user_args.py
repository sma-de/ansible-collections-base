
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import collections
import copy
import pathlib

from ansible.errors import AnsibleOptionsError
##from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBaseMerger, \
  DefaultSetterConstant, \
  NormalizerBase, \
  NormalizerNamed

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import \
  get_subdict, \
  merge_dicts, \
  setdefault_none, \
  SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          UsersNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)



class ActiveUserOnlyNormer(NormalizerBase):

    @property
    def dynamic_subnorms(self):
        return []

    def user_active(self, cfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        return pcfg['configs']['user']['state'] != 'absent'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if self.user_active(cfg, cfgpath_abs):
            self.sub_normalizers += self.dynamic_subnorms
        else:
            my_subcfg['enabled'] = False

        return my_subcfg



class UsersNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
           UserInstNormer(pluginref),
        ]

        super().__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['users']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        sudo_mappings = {}

        for uk, uv in my_subcfg['users'].items():
            uvs = uv.get('sudo', None)

            if not uvs:
                continue

            usc = uvs.get('config', None)

            if not uvs['enabled'] and not usc['absent']:
                continue

            scfgf = usc['cfgfile']

            tmp = sudo_mappings.get(scfgf, None)

            if tmp:
                ##
                ## note: as absented sudo usr subcfgs do not add anything
                ##   useful to sudo upstream cfg except for the case that
                ##   all usr subcfgs are absenting (but then also the
                ##   initial first one is) we simply ignore absenting
                ##   user cfg's for merging
                ##
                if usc['absent']:
                    continue

                merge_dicts(tmp, usc)

            elif usc['absent']:
                tmp = {'absent': usc['absent']}

            else:
                tmp = copy.deepcopy(usc)

            sudo_mappings[scfgf] = tmp

        if sudo_mappings:
            sudo_mappings = {
               'mappings': sudo_mappings,
            }

        my_subcfg['_sudocfg'] = sudo_mappings
        return my_subcfg



class UserInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
           (UserSudoNormer, True),
           SecretSinkInstNormer(pluginref),
           PasswordNormer(pluginref),
           SSHNormer(pluginref),
        ]

        super(UserInstNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['users', SUBDICT_METAKEY_ANY]

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        all_configs = setdefault_none(my_subcfg, 'configs', {})

        ## default user gen modcfg
        uc = setdefault_none(all_configs, 'user', {})

        uc['name'] = my_subcfg['name']
        setdefault_none(uc, 'state', 'present')

        ## default ssh auth mod cfg
        sshc = setdefault_none(all_configs, 'authkey', {})

        sshc['user'] = my_subcfg['name']
        setdefault_none(sshc, 'state', 'present')

        return my_subcfg



class UserSudoNormer(ActiveUserOnlyNormer):

    DEFAULT_SUDOERS_FILEPATH = '60_ansible_users'

    NORMER_CONFIG_PATH = ['sudo']

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'enabled', DefaultSetterConstant(None)
        )

        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'no_password', DefaultSetterConstant(False)
        )

        super(UserSudoNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return 'enabled'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg = super()._handle_specifics_presub(
           cfg, my_subcfg, cfgpath_abs
        )

        setdefault_none(my_subcfg, 'enabled', bool(my_subcfg['config']))

        c = my_subcfg['config']

        setdefault_none(c, 'absent', False)
        setdefault_none(c, 'cfgfile', self.DEFAULT_SUDOERS_FILEPATH)

        if not my_subcfg['enabled']:
            c['absent'] = True
            return my_subcfg

        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        un = pcfg['name']

        for uspec in setdefault_none(c, 'user_specs', [{}]):
            setdefault_none(uspec, 'users', [un])

            defaulting = False
            specs = uspec.get('subspecs', None) or [{}]

            for sp in specs:
                for cp in setdefault_none(sp, 'cmd_specs', [{}]):
                    tags = cp.get('tags', None) or []

                    if my_subcfg['no_password']:
                        pwtag = 'PASSWD:'
                        nopw_tag = 'NO' + pwtag

                        ansible_assert(pwtag not in tags,\
                            "bad sudo user cmd spec for user '{}': having"\
                            " set both of these tags at the sime time"\
                            " doesn't make sense: {}".format(
                               un, [pwtag, nopw_tag]
                            )
                        )

                        if nopw_tag not in tags:
                            tags.append(nopw_tag)
                            defaulting = True
                            cp['tags'] = tags

            if defaulting:
                uspec['subspecs'] = specs

        return my_subcfg



class SSHNormer(ActiveUserOnlyNormer):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'enabled', DefaultSetterConstant(None)
        )

        self._add_defaultsetter(kwargs,
          'keys_exclusive', DefaultSetterConstant(True)
        )

        super(SSHNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['ssh']

    @property
    def simpleform_key(self):
        return 'enabled'

    @property
    def dynamic_subnorms(self):
        return [
          SSHKeygenInstNormer(self.pluginref),
        ]

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg = super()._handle_specifics_presub(
          cfg, my_subcfg, cfgpath_abs
        )

        if my_subcfg['enabled'] == False:
            return my_subcfg

        pcfg = self.get_parentcfg(cfg, cfgpath_abs)

        ssh_auth_cfg = pcfg['configs']['authkey']
        ssh_auth_cfg['exclusive'] = my_subcfg['keys_exclusive']

        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        if my_subcfg['enabled'] == False:
            return my_subcfg

        ## if at least one keygen for one ssh key is defined,
        ## ssh is enabled on default
        setdefault_none(my_subcfg, 'enabled',
           bool(my_subcfg['keygen'])
        )

        return my_subcfg



class SSHKeygenInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'ssh_keys', DefaultSetterConstant({})
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SSHKeygenInstNormerCfgAuth(pluginref),
          SSHKeygenInstNormerCfgGen(pluginref),
          SSHAutogenNormer(pluginref),
          SaveToSinksNormer(pluginref,
             subtype=SaveToSinksInstSSHNormer, userlvl=4
          ),
        ]

        super(SSHKeygenInstNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['keygen', SUBDICT_METAKEY_ANY]

    @property
    def name_key(self):
        return 'key_id'

    @property
    def simpleform_key(self):
        return '_pubkey'


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pkey = my_subcfg.pop('_pubkey', None)
        setdefault_none(my_subcfg['ssh_keys'], 'public', pkey)
        setdefault_none(my_subcfg['ssh_keys'], 'private', pkey)

        return my_subcfg



class SSHKeygenInstNormerCfgAuth(NormalizerBase):

    @property
    def config_path(self):
        return ['configs', 'auth']


class SSHKeygenInstNormerCfgGen(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'state', DefaultSetterConstant('present')
        )

        ##
        ## on default use the key type given here which matches
        ## the current recommendation from github
        ##
        self._add_defaultsetter(kwargs,
          'type', DefaultSetterConstant('ed25519')
        )

        super(SSHKeygenInstNormerCfgGen, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['configs', 'gen']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        cm = my_subcfg.get('comment', None)

        if cm is None:
            pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
            my_subcfg['comment'] = \
               '{} -- autogenerated by ansible'.format(pcfg['key_id'])

        return my_subcfg



class PasswordNormer(ActiveUserOnlyNormer):

    ##
    ## references for special pw values with special meaning:
    ##
    ##   - https://unix.stackexchange.com/q/252016
    ##

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'value', DefaultSetterConstant(None)
        )

        ##
        ## "empty=True" here means login without
        ## password possible, by just pressing enter
        ##
        self._add_defaultsetter(kwargs,
          'empty', DefaultSetterConstant(False)
        )

        ##
        ## "locked=True" means access per password is locked (not allowed)
        ##
        self._add_defaultsetter(kwargs,
          'locked', DefaultSetterConstant(False)
        )

        super(PasswordNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['password']

    @property
    def simpleform_key(self):
        return 'value'

    @property
    def dynamic_subnorms(self):
        return [
           PasswordAutogenNormer(self.pluginref),
           SaveToSinksNormer(self.pluginref,
             subtype=SaveToSinksInstPWNormer, userlvl=2
           ),
        ]

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg['enabled'] = True

        my_subcfg = super()._handle_specifics_presub(
          cfg, my_subcfg, cfgpath_abs
        )

        if not my_subcfg['enabled']:
            return my_subcfg

        ## default "special password modes" based on value
        if my_subcfg['value'] == '':
            my_subcfg['empty'] = True
        ## TODO: special meaning of chars here can vary, for example in modern ubuntu "!" is effectively more similar to empty
        elif my_subcfg['value'] in ['!', '*', '!!']:
            my_subcfg['locked'] = True

        ## norm value according to set "special pw mode" (if any)
        errmsg = "Either choose special user password mode 'empty' or"\
                 " 'locked' or none of them but nether both at the same"\
                 " time, it doesn't make sense"

        if my_subcfg['empty']:
            my_subcfg['value'] = ''
            ansible_assert(not my_subcfg['locked'], errmsg)
        elif my_subcfg['locked']:
            my_subcfg['value'] = '*'
            ansible_assert(not my_subcfg['empty'], errmsg)

        if my_subcfg['value'] is None:
            setdefault_none(my_subcfg, 'autogen', True)

        return my_subcfg



class SecretSinkInstNormer(NormalizerBase):

    @property
    def config_path(self):
        return ['secret_sinks', SUBDICT_METAKEY_ANY]



class SaveToSinksNormer(NormalizerBase):

    def __init__(self, pluginref, *args, subtype=None, userlvl=None,
        **kwargs
    ):
        self._add_defaultsetter(kwargs,
          'enabled_for', DefaultSetterConstant(None)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          subtype(pluginref),
        ]

        self.userlvl = userlvl

        super(SaveToSinksNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['save_to_sinks']

    @property
    def simpleform_key(self):
        return 'enabled_for'


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=self.userlvl)
        sinks = pcfg['secret_sinks']

        extra_sinks = my_subcfg.get('sinks', {})
        setdefault_none(my_subcfg, 'enabled_for',
          bool(sinks) or bool(extra_sinks)
        )

        ena = my_subcfg['enabled_for']

        if not ena:
            ena = []
        elif isinstance(ena, bool):
            ## enable it for all defined secret sinks
            ena = list(set(list(sinks.keys()) + list(extra_sinks.keys())))

        ##
        ## note: when none of the above if clauses matched assume
        ##   on default a list of sink mapkeys where this secret
        ##   should be saved to
        ##
        my_subcfg['enabled_for'] = ena

        ##
        ## create module export config for ansible per sink
        ##
        normed_map = {}

        for k in my_subcfg['enabled_for']:
            vbase = sinks.get(k, None)
            vextra = extra_sinks.get(k, None)

            ansible_assert(vbase or vextra,
               "undefined secret safe sink key '{}' in 'enabled_for'".format(k)
            )

            if vbase:
                vbase = copy.deepcopy(vbase)
            else:
                vbase = {}

            normed_map[k] = merge_dicts(vbase, vextra or {})

        my_subcfg['sinks'] = normed_map
        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        tmp = my_subcfg['sinks']

        if tmp:
            readcfg = []

            for x in tmp.values():
                if x['default']:
                    readcfg.append(x)

            ansible_assert(len(readcfg) < 2,
               "there can only be one save-sink cfg marked as"\
               " default, but we found '{}': {}".format(len(readcfg), readcfg)
            )

            ## if no savesink cfg is explicitly marked as
            ## default, simply use the first one
            if readcfg:
                readcfg = readcfg[0]
            else:
                tmp = tmp[next(iter(tmp.keys()))]
                tmp['default'] = True

                readcfg = tmp

            my_subcfg['_read_cfg'] = readcfg

        return my_subcfg



class SaveToSinksInstBaseNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'default', DefaultSetterConstant(False)
        )

        super(SaveToSinksInstBaseNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['sinks', SUBDICT_METAKEY_ANY]


    @abc.abstractmethod
    def _get_user_basecfg(self, cfg, my_subcfg, cfgpath_abs):
        pass


    def customize_secret_readcfg_hashivault(self,
       readcfg, keys, whole_cfg, my_subcfg, cfgpath_abs
    ):
        ## noop here, optionally overridable
        pass

    def customize_path_formatters_hashivault(self,
       path_formatters, cfg, my_subcfg, cfgpath_abs
    ):
        ## noop here, optionally overridable
        pass


    def _handle_specifics_presub_type_hashivault(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self._get_user_basecfg(cfg, my_subcfg, cfgpath_abs)
        un = pcfg['name']

        c = my_subcfg['config']

        keys = setdefault_none(c, 'secret_keys', {})

        setdefault_none(keys, 'password', 'password')
        setdefault_none(keys, 'private_key', 'private_key')
        setdefault_none(keys, 'public_key', 'public_key')

        unset = object()
        kusr = keys.get('user', unset)

        if kusr == unset:
            kusr = 'user'
            keys['user'] = kusr

        mpoint = c['mountpoint']
        spath = c['path']

        path_formatters = {
          'user_name': un,
        }

        self.customize_path_formatters_hashivault(
           path_formatters, cfg, my_subcfg, cfgpath_abs
        )

        mpoint = mpoint.format(**path_formatters)
        spath = spath.format(**path_formatters)

        savedat = c.get('data', {})

        if kusr:
            savedat[kusr] = un

        my_subcfg['_subcfg_sid'] = spath

        my_subcfg['_subcfg_write'] = {
          'set_secrets': {
             'secrets': {
                spath: {
                  'secret_engine': mpoint,
                  'data': savedat,
                }
             },
          },
        }

        readcfg = {
          'secret_engine': mpoint,
          'optional': True,
        }

        self.customize_secret_readcfg_hashivault(
           readcfg, keys, cfg, my_subcfg, cfgpath_abs
        )

        my_subcfg['_subcfg_read'] = {
          'get_secrets': {
             'return_layout': 'mirror_inputcfg',
             'secrets': {
                spath: readcfg,
             },
          },
        }

        return my_subcfg


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        sstype = my_subcfg.get('type', None)

        ansible_assert(sstype, "mandatory secret sink subkey 'type' not set")

        tmp = getattr(self, '_handle_specifics_presub_type_' + sstype, None)

        ansible_assert(tmp, "unsupported secret sink type '{}'".format(sstype))

        tmp(cfg, my_subcfg, cfgpath_abs)

        return my_subcfg



class SaveToSinksInstPWNormer(SaveToSinksInstBaseNormer):

    def _get_user_basecfg(self, cfg, my_subcfg, cfgpath_abs):
        return self.get_parentcfg(cfg, cfgpath_abs, level=4)

    def customize_secret_readcfg_hashivault(self,
       readcfg, keys, whole_cfg, my_subcfg, cfgpath_abs
    ):
        readcfg['data_keys'] = [keys['password']]



class SaveToSinksInstSSHNormer(SaveToSinksInstBaseNormer):

    def _get_user_basecfg(self, cfg, my_subcfg, cfgpath_abs):
        return self.get_parentcfg(cfg, cfgpath_abs, level=6)

    def customize_secret_readcfg_hashivault(self,
       readcfg, keys, whole_cfg, my_subcfg, cfgpath_abs
    ):
        readcfg['data_keys'] = [keys['public_key'], keys['private_key']]

    def customize_path_formatters_hashivault(self,
       path_formatters, cfg, my_subcfg, cfgpath_abs
    ):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=3)
        path_formatters['ssh_key_id'] = pcfg['key_id']



class AutogenNormerBase(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'config', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'cycle', DefaultSetterConstant(True)
        )

        super(AutogenNormerBase, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['autogen']

    @property
    def simpleform_key(self):
        return 'enabled'


    @abc.abstractmethod
    def _get_parent_preset_value(self, cfg, my_subcfg, cfgpath_abs):
        pass

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pwval = self._get_parent_preset_value(cfg, my_subcfg, cfgpath_abs)
        no_pwval = pwval is None

        ena = setdefault_none(my_subcfg, 'enabled', no_pwval)

        ansible_assert((ena and no_pwval) or (not ena and not no_pwval),
           "Must either set a predefined value or enable secret"\
           " autogen, but never do both"
        )

        return my_subcfg



class PasswordAutogenNormer(AutogenNormerBase):

    def _get_parent_preset_value(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        return pcfg['value']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg = super()._handle_specifics_presub(
           cfg, my_subcfg, cfgpath_abs
        )

        if not my_subcfg['enabled']:
            return my_subcfg

        ## set config defaults
        c = my_subcfg['config']
        setdefault_none(c, 'length', 50)
        setdefault_none(c, 'chars', ['ascii_letters', 'digits'])

        return my_subcfg



class SSHAutogenNormer(AutogenNormerBase):

    def _get_parent_preset_value(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        return pcfg['ssh_keys'].get('public', None)


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg = super()._handle_specifics_presub(
           cfg, my_subcfg, cfgpath_abs
        )

        if not my_subcfg['enabled']:
            return my_subcfg

        return my_subcfg



class ActionModule(ConfigNormalizerBaseMerger):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            RootCfgNormalizer(self), *args, default_merge_vars=[
               'smabot_base_manage_os_user_args_defaults',
            ], extra_merge_vars_ans=[
               'extra_smabot_base_manage_os_user_args_config_maps'
            ],
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_base_manage_os_user_args'

