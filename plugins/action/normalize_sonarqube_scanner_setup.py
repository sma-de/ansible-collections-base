
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


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



def require_os_packages(basecfg, *packages):
    os_pkg = basecfg['os_packages']['name']

    for x in packages:
        if x not in os_pkg:
            os_pkg.append(x)


def require_pip_packages(basecfg, *packages):
    pips = setdefault_none(basecfg, '_pip_installs', [])

    for x in packages:
        if x not in pips:
            pips.append(x)



class RootCfgNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'java', DefaultSetterConstant(JavaNormer.JAVA_EMBEDDED_KEY)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          DestNormer(pluginref),
          JavaNormer(pluginref),
          OsPackageNormer(pluginref),
          DownloadNormer(pluginref),
          SupportsNormer(pluginref),

          RequirementsPipNormer(pluginref),
        ]

        super(RootCfgNormalizer, self).__init__(pluginref, *args, **kwargs)


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        # TODO: default version to latest, this can be done by querying github repo of scanner: https://github.com/SonarSource/sonar-scanner-cli/releases
        ver = my_subcfg.setdefault('version', None)

        ansible_assert(ver, "autoversioning to latest ver not yet implemented, please provide a concrete version for now")

        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        # create passthrough cfg
        tmp = {}

        for x in ['download', 'destination']:
            tmp[x] = my_subcfg[x]

        my_subcfg['_install'] = tmp

        instpath = pathlib.Path(my_subcfg['destination']['path'])

        my_subcfg['envvars'] = {
          'SONAR_SCANNER_HOME': str(instpath),
        }

        my_subcfg['syspath'] = {
          'present': [str(instpath / 'bin')],
        }

        return my_subcfg



class RequirementsPipNormer(NormalizerBase):

    @property
    def config_path(self):
        return ['requirements', 'pip']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        plst = pcfg.pop('_pip_installs', None)

        my_subcfg['enabled'] = True

        if not plst:
            my_subcfg['enabled'] = False
            return my_subcfg

        c = setdefault_none(my_subcfg, 'config', {})

        c['state'] = 'present'
        c['name'] = plst

        return my_subcfg



class JavaNormer(NormalizerBase):

    JAVA_EMBEDDED_KEY = 'embedded'

    @property
    def config_path(self):
        return ['java']

    @property
    def simpleform_key(self):
        return 'name'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        use_embedded = my_subcfg['name'] == self.JAVA_EMBEDDED_KEY
        my_subcfg['use_embedded'] = use_embedded

        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        dest = pcfg['destination']

        # create config to enforce that external java is actually
        # is used (which atm unfortunately makes it necessary to
        # hardcode change scanner binary script)
        tmp = setdefault_none(my_subcfg, 'force_external', {})

        if not use_embedded:
            tmp['backrefs'] = True
            setdefault_none(tmp, 'path',
              str(pathlib.Path(dest['path']) / dest['binpath'])
            )

            setdefault_none(tmp, 'regexp', r'(?i)^(\s*use_embedded_jre=).*')

            l = setdefault_none(tmp, 'line', r'\g<1>{}')
            tmp['line'] = l.format('false')

        return my_subcfg



class OsPackageNormer(NormalizerBase):

    @property
    def config_path(self):
        return ['os_packages']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        ##my_subcfg['state'] = 'present'

        # handle all packages needed
        tmp = ['nodejs']

        java = pcfg['java']
        if not java['use_embedded']:
            tmp.append(java['name'])

        my_subcfg['name'] = tmp
        return my_subcfg



class SupportsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          (SupportShellNormer, True),
          (SupportPythonNormer, True),
        ]

        super(SupportsNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['supports']



class SupportShellNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['shell']

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return '_simple_formkey'


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        # simpleform is not used itself atm as value, only to
        # cticate this cfg as a whole
        my_subcfg.pop(self.simpleform_key)

        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        require_os_packages(pcfg, 'shellcheck')

        return my_subcfg



class SupportPythonNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['python']

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return '_simple_formkey'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        # simpleform is not used itself atm as value, only to
        # cticate this cfg as a whole
        my_subcfg.pop(self.simpleform_key)

        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        require_pip_packages(pcfg, 'pylint')

        return my_subcfg



class DownloadNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'url', DefaultSetterConstant(
             'https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-{VERSION}.zip'
          )
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          (DownloadVerifyNormer, True),
        ]

        super(DownloadNormer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['download']

    @property
    def simpleform_key(self):
        return 'url'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs)
        my_subcfg['url'] = my_subcfg['url'].format(
          **dict(VERSION=pcfg['version'])
        )

        return my_subcfg



class DownloadVerifyNormer(NormalizerBase):

    NORMER_CONFIG_PATH = ['verify']

    @property
    def config_path(self):
        return self.NORMER_CONFIG_PATH

    @property
    def simpleform_key(self):
        return 'fingerprint'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)

        # TODO: in theory this should be handled more internally by install from url
        # TODO: as we only need it during install it might also be a good idea to remove them after that again with a proper process
        require_os_packages(pcfg, 'gnupg')
        require_pip_packages(pcfg, 'python-gnupg')
        require_pip_packages(pcfg, 'validators')

        return my_subcfg



class DestNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
          'path', DefaultSetterConstant('/opt/sonar-scanner')
        )

        self._add_defaultsetter(kwargs,
          'binpath', DefaultSetterConstant('bin/sonar-scanner')
        )

        self._add_defaultsetter(kwargs,
          'unpacking', DefaultSetterConstant(True)
        )

        super(DestNormer, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['destination']

    @property
    def simpleform_key(self):
        return 'path'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        unpack = my_subcfg['unpacking']

        if unpack or isinstance(unpack, collections.abc.Mapping):
            if not isinstance(unpack, collections.abc.Mapping):
                unpack = {}

            setdefault_none(unpack, 'flatten', 1)

            my_subcfg['unpacking'] = unpack

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
        return 'smabot_base_setup_sonarscan_args'

    @property
    def supports_merging(self):
        return False

