
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import collections
import pathlib

from ansible.errors import AnsibleOptionsError
##from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, \
  DefaultSetterConstant, \
  NormalizerBase, \
  NormalizerNamed

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import \
  get_subdict, \
  setdefault_none, \
  SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SudoMappingsNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)



class SudoMappingsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SudoMappingInstNormer(pluginref),
        ]

        super(SudoMappingsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['mappings']



class SudoMappingInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'absent', DefaultSetterConstant(False)
        )

        super(SudoMappingInstNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return [SUBDICT_METAKEY_ANY]

    @property
    def name_key(self):
        return 'cfgfile'

    @property
    def simpleform_key(self):
        return '_simple_user_spec'


    def _norm_userlist(self, ulist):
        return ','.join(ulist)

    def _norm_hostlist(self, hlist):
        return self._norm_userlist(hlist)

    def _norm_runas_list(self, runas):
        ansible_assert(False, "TODO: supporting runas list")

    def _norm_cmdlist(self, runas):
        ansible_assert(False, "TODO: supporting cmd list")

    def _norm_runas(self, runas):
        ansible_assert(False, "TODO: supporting runas")

    def _norm_cmdopts(self, options):
        ansible_assert(False, "TODO: supporting cmdspec options")

    def _norm_cmdtags(self, tags):
        return ' '.join(tags)


    def _norm_cmdspec(self, spec):
        res = []

        # optionally handle runas
        tmp = spec.get('runas', None)

        if tmp:
            res.append(self._norm_runas(tmp))

        # optionally handle options
        tmp = spec.get('options', None)

        if tmp:
            res.append(self._norm_cmdopts(tmp))

        # optionally handle tags
        tmp = spec.get('tags', None)

        if tmp:
            res.append(self._norm_cmdtags(tmp))

        cmd = setdefault_none(spec, 'cmd', 'ALL')
        res.append(cmd)

        return ' '.join(res)


    def _norm_cmdspecs(self, specs):
        tmp = []
        for s in specs:
            tmp.append(self._norm_cmdspec(s))

        return self._norm_userlist(tmp)


    def _norm_subspecs(self, subspec):
        hlist = setdefault_none(subspec, 'hosts', [])

        if not hlist:
            hlist.append('ALL')

        cmdspecs = setdefault_none(subspec, 'cmd_specs', [{}])

        return "{} = {}".format(self._norm_hostlist(hlist),
          self._norm_cmdspecs(cmdspecs)
        )


    def _norm_userspec(self, cfg, my_subcfg, cfgpath_abs, uspec):
        if not isinstance(uspec, collections.abc.Mapping):
            ## assume simple string form
            return {'_export': uspec}

        # create userspec sudo cfg line
        res = []
        res.append(self._norm_userlist(uspec['users']))

        subspecs = setdefault_none(uspec, 'subspecs', [{}])

        tmp = []
        for sub in subspecs:
            tmp.append(self._norm_subspecs(sub))

        ansible_assert(tmp, "Must at least set one subspec")
        res.append(' : '.join(tmp))

        uspec['_export'] = ' '.join(res)
        return uspec


    def _norm_deftype(self, deftype):
        if not isinstance(deftype, collections.abc.Mapping):
            ## assume simple string form
            return deftype

        deftype_sfx = ''
        deftype_matched = None

        subtypes = (
           ('hosts', '@', self._norm_hostlist),
           ('users', ':', self._norm_userlist),
           ('commands', '!', self._norm_cmdlist),
           ('runas', '>', self._norm_runas_list),
        )

        ## check all subtypes, matching none or one
        ## is okay, nether mutliple at once
        for x in subtypes:
            ck, sym, normfn = x

            cfgval = deftype.get(ck, None)

            if not cfgval:
                ## type not matched in config, ignore it
                continue

            ansible_assert(not deftype_matched,\
                "bad default spec default type config, use either"\
                " '{}' or '{}' subspec, but nether both:\n{}".format(
                   ck, deftype_matched[0], deftype
                )
            )

            deftype_sfx = sym + normfn(cfgval)
            deftype_matched = x

        return 'Defaults' + deftype_sfx


    def _norm_default_params(self, pspec):
        if not isinstance(pspec, collections.abc.Mapping):
            ## assume simple string form
            return pspec

        def check_valkeys_valid(spec, matched, allkeys):
            for k in allkeys:
                if k == matched:
                    continue

                y = spec.get(k, None)

                ansible_assert(not y,\
                    "bad param subspec for default entry, use either"\
                    " subkey '{}' or '{}' but never more than one"\
                    " at the same time".format(matched, k)
                )

        param = pspec.get('param', None)
        ansible_assert(param,\
            "bad param subspec for default entry, mandatory"\
            " subkey param not found"
        )

        valkeys = ['invert', 'values', 'values+', 'values-']

        ck = 'invert'
        tmp = pspec.get(ck, None)

        if tmp is not None:
            # flag param inversion mode
            check_valkeys_valid(pspec, ck, valkeys)

            if tmp:
                return "!" + param

            return param

        ck = 'values'
        tmp = pspec.get(ck, None)

        if tmp is not None:
            # default value set mode
            check_valkeys_valid(pspec, ck, valkeys)

            if isinstance(tmp, list):
                tmp = '"' + ' '.join(tmp) + '"'

            return "{} = {}".format(param, tmp)

        for x in ['+', '-']:
            ck = 'values' + x
            tmp = pspec.get(ck, None)

            if tmp is not None:
                # list value change modes (+/-)
                check_valkeys_valid(pspec, ck, valkeys)

                if not isinstance(tmp, list):
                    tmp = [tmp]

                tmp = '"' + ' '.join(tmp) + '"'
                return "{} {}= {}".format(param, x, tmp)

        ## no valkey match is basically the same invert
        ## false (flag param not inverted)
        return param


    def _norm_defaultspec(self, cfg, my_subcfg, cfgpath_abs, spec):
        if not isinstance(spec, collections.abc.Mapping):
            ## assume simple string form
            return {'_export': spec}

        # create default spec (entry) sudo cfg line
        setdefault_none(spec, 'type', 'Defaults')
        res = []
        res.append(self._norm_deftype(spec['type']))

        params = setdefault_none(spec, 'parameters', [{}])

        tmp = []
        for p in params:
            tmp.append(self._norm_default_params(p))

        ansible_assert(tmp, "Must at least set one parameter entry for default spec")
        res.append(' , '.join(tmp))

        spec['_export'] = ' '.join(res)
        return spec



    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        # normalize cfgfile
        cfgfile = pathlib.Path(my_subcfg['cfgfile'])

        if not cfgfile.is_absolute():
            cfgfile = pathlib.Path('/etc/sudoers.d/') / cfgfile

        my_subcfg['cfgfile'] = str(cfgfile)

        if my_subcfg['absent']:
            return my_subcfg

        self.sub_normalizers += [
          (MappingInstFixEnvNormer, True),
        ]

        # normalize user specs
        uspecs = setdefault_none(my_subcfg, 'user_specs', [])
        tmp = my_subcfg.pop(self.simpleform_key, None)

        if tmp:
            uspecs.append(tmp)

        new_specs = []
        for u in uspecs:
            new_specs.append(self._norm_userspec(
               cfg, my_subcfg, cfgpath_abs, u)
            )

        my_subcfg['user_specs'] = new_specs

        setdefault_none(my_subcfg, 'default_specs', [])
        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        if my_subcfg['absent']:
            return my_subcfg

        # normalize defaults specs
        new_specs = []
        for u in my_subcfg['default_specs']:
            new_specs.append(self._norm_defaultspec(
               cfg, my_subcfg, cfgpath_abs, u)
            )

        my_subcfg['default_specs'] = new_specs

        return my_subcfg



class MappingInstFixEnvNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['fix_env']

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          MappingInstFixEnvProxyNormer(pluginref),
          MappingInstFixEnvCustomPlusNormer(pluginref),
          MappingInstFixEnvCustomMinusNormer(pluginref),
        ]

        super(MappingInstFixEnvNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH



class MappingInstFixEnvSubXNormer(NormalizerBase):

    def _add_default_entry_env(self, cfg, my_subcfg, cfgpath_abs, entry):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)

        entry['param'] = 'env_keep'

        cmt = entry.get('comment', None)

        entry = {
          'parameters': [entry],
        }

        if cmt:
            entry['comment'] = cmt

        pcfg['default_specs'].append(entry)



class MappingInstFixEnvCustomBaseNormer(MappingInstFixEnvSubXNormer):

    @property
    def simpleform_key(self):
        return 'values'

    @property
    @abc.abstractmethod
    def values_entry_key(self):
        pass

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        values = my_subcfg.get('values', None)

        if not values:
            return my_subcfg

        entry = {
          self.values_entry_key: values,
        }

        cmt = my_subcfg.get('comment', None)
        if cmt:
            entry['comment'] = cmt

        self._add_default_entry_env(cfg, my_subcfg, cfgpath_abs, entry)
        return my_subcfg


class MappingInstFixEnvCustomPlusNormer(MappingInstFixEnvCustomBaseNormer):

    @property
    def values_entry_key(self):
        return 'values+'

    @property
    def config_path(self):
        return ['custom+']


class MappingInstFixEnvCustomMinusNormer(MappingInstFixEnvCustomBaseNormer):

    @property
    def values_entry_key(self):
        return 'values-'

    @property
    def config_path(self):
        return ['custom-']



class MappingInstFixEnvProxyNormer(MappingInstFixEnvSubXNormer):

    PROXY_VARS = [
      'http_proxy', 'https_proxy', 'ftp_proxy', 'no_proxy',
    ]

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'enabled', DefaultSetterConstant(None)
        )

        super(MappingInstFixEnvProxyNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['proxy']

    @property
    def simpleform_key(self):
        return 'enabled'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        setdefault_none(my_subcfg, 'enabled', len(my_subcfg) > 1)

        if not my_subcfg['enabled']:
            return my_subcfg

        cmt = setdefault_none(my_subcfg, 'comment',
           "make sure to keep user original proxy settings"\
           " intact in sudo mode"
        )

        self._add_default_entry_env(cfg, my_subcfg, cfgpath_abs, {
           'values+': self.PROXY_VARS + list(
              map(lambda x: x.upper(), self.PROXY_VARS)
           ),

           'comment': cmt
        })

        return my_subcfg



class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            RootCfgNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_base_setup_sudo_args'

    @property
    def supports_merging(self):
        return False

