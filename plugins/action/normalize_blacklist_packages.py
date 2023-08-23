
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import re
import textwrap

from ansible.errors import AnsibleOptionsError
##from ansible.plugins.filter.core import to_bool

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  ConfigNormalizerBase, \
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
          PackageInstNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg['_blacklist_cfg'] = {}
        return my_subcfg


class PackageInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          VersionsNormer(pluginref),
        ]

        super(PackageInstNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['packages', 'packages', SUBDICT_METAKEY_ANY]

    def _handle_specifics_postsub_debian(self, cfg, my_subcfg, cfgpath_abs):
        ## prepare content for pinning (apt preference files)
        lines = [textwrap.dedent("""
          ##
          ## Auto created file managed by ansible. DO NOT EDIT!
          ##
          """), '']

        for k,v in my_subcfg['versions']['blacklist'].items():
            sublines = []

            if v['comment']:
                sublines.append(v['comment'])

            sublines.append("Package: {}".format(my_subcfg['name']))
            sublines.append("Pin: version {}".format(v['name']))
            sublines.append("Pin-Priority: {}".format(v['priority']))

            lines.append('\n'.join(sublines))

        lines.append('')
        lines.append('')
        lines = '\n'.join(lines)

        ## determine pereferences file filename
        fname = "/etc/apt/preferences.d/ansible_pblacklist_" + my_subcfg['safe_name']

        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=4)

        tmp = setdefault_none(pcfg['_blacklist_cfg'], 'fill_pref_files', {})
        tmp[fname] = {
          'package': my_subcfg['name'],
          'cfg': {
            'content': lines,
            'dest': fname
          },
        }

        return my_subcfg

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        ostype = self.pluginref.get_ansible_var('ansible_os_family').lower()

        tmp = getattr(self, '_handle_specifics_postsub_' + ostype, None)
        if tmp:
            my_subcfg = tmp(cfg, my_subcfg, cfgpath_abs)

        return my_subcfg

    def build_safe_package_name(self, pname):
        repl_map = {
          '-': '_',
          '.': '_',
          '~': '_',
          ':': '_',
        }

        for k,v in repl_map.items():
            pname = pname.replace(k, v)

        return pname

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        safe_name = my_subcfg.get('safe_name', None)

        if not safe_name:
            my_subcfg['safe_name']= self.build_safe_package_name(
               my_subcfg['name']
            )

        return my_subcfg


class VersionsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          VersionBlacklistInstNormer(pluginref),
        ]


        super(VersionsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['versions']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        ##
        ## note: for later ansible compuations it is important to
        ##   have a collection where the exact versions are
        ##   the keys / items, note that can be equal to official api
        ##   blacklist subkey, but it does not have to as external
        ##   key allows to optionally have different strings for
        ##   mapkey and exact value string
        ##
        blist_vers = {}

        for k,v in my_subcfg['blacklist'].items():
            v['mapkey'] = k
            blist_vers[v['name']] = v

        my_subcfg['_blacklist_vers'] = blist_vers
        return my_subcfg


class VersionBlacklistInstNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          BadVerInstalledNormer(pluginref),
        ]

        self._add_defaultsetter(kwargs,
          'comment', DefaultSetterConstant(None)
        )

        super(VersionBlacklistInstNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['blacklist', SUBDICT_METAKEY_ANY]

    def _handle_specifics_presub_debian(self, cfg, my_subcfg, cfgpath_abs):
        setdefault_none(my_subcfg, 'priority', -1)

        comment = my_subcfg['comment']
        if comment:
            ## normalize input comment to final string and prefix every line with comment char
            if not isinstance(comment, list):
                ## assume string type
                comment = comment.split('\n')

            tmp = []
            for l in comment:
                tmp.append("## " + (l or ''))

            my_subcfg['comment'] = '\n'.join(tmp)

        return my_subcfg

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ostype = self.pluginref.get_ansible_var('ansible_os_family').lower()

        tmp = getattr(self, '_handle_specifics_presub_' + ostype, None)
        if tmp:
            my_subcfg = tmp(cfg, my_subcfg, cfgpath_abs)

        return my_subcfg


class BadVerInstalledNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          (BadVerInstalledTypeErrorNormer, True),
          (BadVerInstalledTypeWarnNormer, True),
          (BadVerInstalledTypeReInstallNormer, True),
          (BadVerInstalledTypeFallbackVerNormer, True),
        ]

        super(BadVerInstalledNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['when_installed']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if not my_subcfg:
            tmp = BadVerInstalledTypeErrorNormer.NORMER_CONFIG_PATH[-1]
            my_subcfg[tmp] = None

        return my_subcfg



class BadVerInstalledTypeXBase(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'enabled', DefaultSetterConstant(True)
        )

        super(BadVerInstalledTypeXBase, self).__init__(pluginref, *args, **kwargs)

    @property
    def name_key(self):
        return "type"

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if not my_subcfg['enabled']:
            return my_subcfg

        pcfg_p = self.get_parentcfg(cfg, cfgpath_abs, level=5)
        pcfg_ver = self.get_parentcfg(cfg, cfgpath_abs, level=2)

        active_badinst_meth = pcfg_ver.get('_when_installed_active', None)

        assert not active_badinst_meth,\
           "there can only be one active 'when_installed' method for"\
           " a blacklisted version, but {}:{} has currently set at"\
           " least two: '{}' and '{}'".format(pcfg_p['name'],
               pcfg_ver['name'], active_badinst_meth['type'],
               my_subcfg['type']
            )

        pcfg_ver['_when_installed_active'] = my_subcfg
        return my_subcfg


class BadVerInstalledTypeErrorNormer(BadVerInstalledTypeXBase):

    NORMER_CONFIG_PATH = ['raise_error']

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH


class BadVerInstalledTypeWarnNormer(BadVerInstalledTypeXBase):

    NORMER_CONFIG_PATH = ['warn']

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH


class BadVerInstalledTypeFallbackVerNormer(BadVerInstalledTypeXBase):

    NORMER_CONFIG_PATH = ['fallback_version']

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'install_new', DefaultSetterConstant({})
        )

        super(BadVerInstalledTypeFallbackVerNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return 'version'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=5)

        tmp = setdefault_none(my_subcfg['install_new'], 'cfg', {})
        tmp = setdefault_none(tmp, 'packages', {})
        tmp = setdefault_none(tmp, 'default', {})
        tmp = setdefault_none(tmp, pcfg['name'], {})

        pn = tmp.get('name', None) or []

        if not isinstance(pn, list):
            pn = [pn]

        t2 = pcfg['name']

        # TODO: verjoiner is distro / package manager dependend, make this more customizable (current implementation == debian/ubuntu like (apt))
        t2 += "=" + my_subcfg['version']

        pn.append(t2)

        tmp['name'] = pn

        tmp = setdefault_none(tmp, 'config', {})
        setdefault_none(tmp, 'state', 'present')

        # TODO: this setting is technically distro / package manager dependend, so make it adaptable
        # TODO-2: or would it be grade if ussed upstream module could handle switching it distro specific??
        setdefault_none(tmp, 'allow_downgrade', True)

        return super()._handle_specifics_presub(cfg, my_subcfg, cfgpath_abs)


class BadVerInstalledTypeReInstallNormer(BadVerInstalledTypeXBase):

    NORMER_CONFIG_PATH = ['reinstall']

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'remove_old', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs,
          'install_new', DefaultSetterConstant({})
        )

        super(BadVerInstalledTypeReInstallNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=5)

        tmp = setdefault_none(my_subcfg['remove_old'], 'cfg', {})
        tmp['state'] = 'absent'

        ## for the case an user wants or needs to also deinstall some
        ## other packages besides the critical (for example
        ## dependencies or similar), it is optionally possible here
        ## to specify extra deinstall names
        pn = tmp.get('name', None) or []

        if not isinstance(pn, list):
            pn = [pn]

        pn.append(pcfg['name'])

        tmp['name'] = pn

        ## optionally allow to specify an explicit version
        ## when reinstalling bad package
        newver = my_subcfg['install_new'].get('version', None)

        tmp = setdefault_none(my_subcfg['install_new'], 'cfg', {})
        setdefault_none(tmp, 'state', 'present')

        ## similar to above it is possible for reinstall step to specify extra package for reinstall step
        pn = tmp.get('name', None) or []

        if not isinstance(pn, list):
            pn = [pn]

        t2 = pcfg['name']

        if newver:
            # TODO: verjoiner is distro / package manager dependend, make this more customizable (current implementation == debian/ubuntu like (apt))
            t2 += "=" + newver

        pn.append(t2)

        tmp['name'] = pn

        return super()._handle_specifics_presub(cfg, my_subcfg, cfgpath_abs)



class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            RootCfgNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_base_blacklist_packages_args'

    @property
    def supports_merging(self):
        return False

