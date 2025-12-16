
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import abc
import collections
import copy

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import\
  NormalizerBase,\
  NormalizerNamed,\
  DefaultSetterConstant

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import SUBDICT_METAKEY_ANY, setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import\
  get_subdict,\
  merge_dicts,\
  SafeDict

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


display = Display()


class CredentialSettingsNormerBase(NormalizerBase):

    def __init__(self, pluginref, *args,
        cycle_default=False, credstore_normer_kwargs=None, **kwargs
    ):
        self._add_defaultsetter(kwargs,
          'enable_default_stores', DefaultSetterConstant(None)
        )

        self._add_defaultsetter(kwargs,
          'stores', DefaultSetterConstant({})
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          CredentialStoreInstNormer(pluginref,
              **(credstore_normer_kwargs or {})
          ),
        ]

        self.cycle_default = cycle_default

        super(CredentialSettingsNormerBase, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def default_settings_distance(self):
        return 0

    @property
    def has_value(self):
        return True

    @property
    def storeable(self):
        return True

    @property
    def stores_mandatory(self):
        return False

    @property
    def default_stores(self):
        return {'ansible_variables': None}

    @property
    def default_settings_subpath(self):
        return ['default_settings']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if self.default_settings_distance:
            pcfg = self.get_parentcfg(cfg, cfgpath_abs,
              level=self.default_settings_distance
            )

            for k in self.default_settings_subpath:
                pcfg = pcfg[k]

            my_subcfg = merge_dicts(copy.deepcopy(pcfg), my_subcfg)

        ac = my_subcfg.get('auto_create', None)
        value = None

        if self.has_value:
            value = my_subcfg.get('value', None)

        if ac is None:
            ## default auto-create to false if an explicit
            ## value is provided and true otherwise
            ac = value is None

        if not isinstance(ac, collections.abc.Mapping):
            ## assume simple bool
            ac = {'enabled': ac}

        setdefault_none(ac, 'enabled', True)

        ansible_assert(value or ac['enabled'],
           "bad user definition: credential must either have"\
           " an explicit value set or 'auto_create' must be active"
        )

        ansible_assert(not (value and ac['enabled']),
           "bad user definition: either give a credential value"\
           " explicitly or activate 'auto_create', but never do"\
           " both at the same time"
        )

        setdefault_none(ac, 'cycle', self.cycle_default)
        my_subcfg['auto_create'] = ac

        auto_vers = ac.get('versions')

        if auto_vers:
            c = setdefault_none(my_subcfg, 'config', {})
            c['versions'] = auto_vers

        if self.storeable and my_subcfg['auto_create']['enabled']:
            ena_defstores = my_subcfg['enable_default_stores']
            stores = my_subcfg['stores']

            ## if not set otherwise on default the default stores
            ## are only added when no other explicit stores
            ## are given by config
            if ena_defstores is None:
                ena_defstores = not stores
                my_subcfg['enable_default_stores'] = ena_defstores

            if ena_defstores:
                # create ansible variable default store
                stores = merge_dicts(stores, self.default_stores)
                my_subcfg['stores'] = stores

        return my_subcfg


    def _get_store_keynames_replacements(self, cfg, my_subcfg, cfgpath_abs,
        store_id, store_map
    ):
        ## optionally overwriteable by subclasses
        return {}


    def _postsub_mod_credstore_ansible_variables(self, cfg, my_subcfg, cfgpath_abs,
        store_id, store_map
    ):
        ## optionally change store keynames based on credential
        ## specific meta information
        knames = store_map['parameters']['key_names']

        if self.has_value:
            ##
            ## optionally if credential has optional extra_values
            ## default there credstore keyname by their cfg keynames
            ##
            for k in my_subcfg.get('extra_values', {}):
                knames[k] = k

        for k in knames:
            repl = SafeDict()
            repl.update(**self._get_store_keynames_replacements(
              cfg, my_subcfg, cfgpath_abs, store_id, store_map
            ))

            v = knames[k].format_map(repl)

            knames[k] = v

        if self.has_value:
            credstore_extra_vals = {}

            for k, v in my_subcfg.get('extra_values', {}).items():
                credstore_extra_vals[knames[k]] = v

            store_map['parameters']['extra_values'] = credstore_extra_vals


    def _postsub_mod_credstore_hashivault(self, cfg, my_subcfg, cfgpath_abs,
        store_id, store_map
    ):
        self._postsub_mod_credstore_ansible_variables(
           cfg, my_subcfg, cfgpath_abs, store_id, store_map
        )


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        ## optionally normalize adapt generic cred stores settings
        ## to specific credential
        for k,v in my_subcfg.get('stores', {}).items():
            tmp = getattr(self, '_postsub_mod_credstore_' + v['type'], None)

            if tmp:
                tmp(cfg, my_subcfg, cfgpath_abs, k, v)

        if self.storeable:
            store_cnt = len(my_subcfg['stores'])

            if my_subcfg['auto_create']['enabled']:
                ansible_assert(store_cnt > 0 or not self.stores_mandatory,
                   "when auto generating secrets we need at least"\
                   " one store defined to export secrets to"
                )

            if store_cnt > 0:
                ## check there is at exactly 1 default store,
                ##   if only one is defined, make it auto default
                default_stores = []

                for k, v in my_subcfg['stores'].items():
                    if store_cnt == 1:
                        v['default'] = True

                    if v['default']:
                        default_stores.append(v)

                ansible_assert(default_stores,
                   "one secret store must be marked as default, if there is"\
                   " only one it should be made default automatically, if you"\
                   " defined more than one, you must set default to true for"\
                   " one of them explicitly, found '{}' stores"\
                   " defined:\n{}".format(len(my_subcfg['stores']),
                      my_subcfg['stores']
                   )
                )

                ansible_assert(len(default_stores) == 1,
                   "only one secret store can be default, but we"\
                   " found {}:\n{}".format(len(default_stores), default_stores)
                )

                my_subcfg['_default_store'] = default_stores[0]

        return my_subcfg



class UserCredsDefaults_Normer(CredentialSettingsNormerBase):

    def __init__(self, pluginref, *args, config_path=None, **kwargs):
        self._config_path = config_path or ['credentials', 'default_settings']

        super(UserCredsDefaults_Normer, self).__init__(
           pluginref, *args, **kwargs
        )
    @property
    def config_path(self):
        return self._config_path

    @property
    def has_value(self):
        return False

    @property
    def storeable(self):
        return False

##    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
##        my_subcfg = super()._handle_specifics_presub(cfg, my_subcfg, cfgpath_abs)
##
##        ##
##        ## update: bad idea of doing that here, what if a config only has
##        ##   store explicitly defined for specific credentials
##        ##
##        ##stores = my_subcfg['stores']
##
##        ##if my_subcfg['auto_create']['enabled'] and not stores:
##        ##    # create ansible variable default store
##        ##    stores = {'ansible_variables': None}
##        ##    my_subcfg['stores'] = stores
##
##        return my_subcfg



class CredentialStoreInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, default_basevar=None, **kwargs):
        self._add_defaultsetter(kwargs,
          'default', DefaultSetterConstant(False)
        )

        self._add_defaultsetter(kwargs,
          'parameters', DefaultSetterConstant({})
        )

        self._default_basevar = default_basevar

        super(CredentialStoreInstNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def default_basevar(self):
        return self._default_basevar

    @property
    def config_path(self):
        return ['stores', SUBDICT_METAKEY_ANY]


    def _handle_specifics_presub_ansible_variables(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg['reversable'] = False

        vnames = setdefault_none(my_subcfg['parameters'], 'key_names', {})

        bvar = vnames.get('basevar', None)

        if not bvar:
            ansible_assert(self.default_basevar,
               "mandatory key parameter for ansible-variable credential"\
               " backend store not defined, either define it explicitly"\
               " or ensure normalizer class has a default set or"\
               " disable this store"
            )

            vnames['basevar'] = self.default_basevar

        setdefault_none(vnames, 'password', 'password')
        setdefault_none(vnames, 'sshkey_public', 'sshkey_public_{cred_id}')
        setdefault_none(vnames, 'sshkey_private', 'sshkey_private_{cred_id}')
        setdefault_none(vnames, 'token', 'token_{cred_id}')

        return my_subcfg


    def _handle_specifics_presub_hashivault(self, cfg, my_subcfg, cfgpath_abs):
        reversable = setdefault_none(my_subcfg, 'reversable', True)

        my_subcfg = self._handle_specifics_presub_ansible_variables(
          cfg, my_subcfg, cfgpath_abs
        )

        my_subcfg['reversable'] = reversable
        setdefault_none(my_subcfg, 'config', {})

        params = my_subcfg['parameters']

        params['key_names'].pop('basevar')

        psets = setdefault_none(params, 'settings', {})
        psets_defs = setdefault_none(psets, 'defaults', {})
        psets_defs_read = setdefault_none(psets_defs, 'read', {})

        setdefault_none(psets_defs_read, 'optional', True)
        return my_subcfg


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        stype = setdefault_none(my_subcfg, 'type', my_subcfg['name'])

        ## optionally apply store defaults
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        st_def = pcfg.get('store_defaults', {})

        if st_def:
            my_stdefs = {}

            for x in ['all', stype]:
                my_stdefs = merge_dicts(my_stdefs,
                  copy.deepcopy(st_def.get(x, None) or {})
                )

            my_subcfg = merge_dicts(my_stdefs, my_subcfg)

        tmp = getattr(self, '_handle_specifics_presub_' + stype, None)

        if tmp:
            my_subcfg = tmp(cfg, my_subcfg, cfgpath_abs)

        return my_subcfg

