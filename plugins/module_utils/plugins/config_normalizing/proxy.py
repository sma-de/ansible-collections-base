
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import abc
import copy
from urllib.parse import urlparse

from ansible.errors import AnsibleError

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  DefaultSetterConstant, \
  NormalizerBase

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import \
  merge_dicts, \
  setdefault_none

from ansible.utils.display import Display


display = Display()


class StandardProxyNormerBase(NormalizerBase):

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        proxy_proxy = my_subcfg.get('proxy', None)

        if not proxy_proxy:
            # proxy optionally unset
            return my_subcfg

        ## default proxy values
        setdefault_none(proxy_proxy, 'https', proxy_proxy['http'])

        ## create proxy env vars
        proxy_vars = {}

        for k in ['http', 'https']:
            tmp = proxy_proxy.get(k, None)

            if not tmp: continue

            proxy_vars[k + '_proxy'] = tmp

        no_proxy = proxy_proxy.get('noproxy', None)

        if no_proxy:
            proxy_vars['no_proxy'] = ','.join(no_proxy)

        ## some distro's / progs awaits proxy vars to be all caps, 
        ## some to be all lower case, make sure we handle both
        tmp = list(proxy_vars.keys())
        for k in tmp:
            proxy_vars[k.upper()] = proxy_vars[k]

        my_subcfg['vars'] = proxy_vars
        return my_subcfg


class ConfigNormerProxy(StandardProxyNormerBase):

    def __init__(self, pluginref, *args,
        config_path=None, force_ecosystems=False, **kwargs
    ):
        self._config_path = config_path or ['proxy']

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ## note: order does matter here dependency wise
          ConfigNormerProxyBuildTime(pluginref, forced=force_ecosystems),
          ConfigNormerProxyJava(pluginref, forced=force_ecosystems),
          ConfigNormerProxyJavaBuildTime(pluginref, forced=force_ecosystems),
        ]

        super(ConfigNormerProxy, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self._config_path


class ConfigNormerProxyBuildTime(StandardProxyNormerBase):

    def __init__(self, pluginref, *args, forced=False, **kwargs):
       self._add_defaultsetter(kwargs,
         'activate', DefaultSetterConstant(True)
       )

       self._add_defaultsetter(kwargs,
         'inherit', DefaultSetterConstant(True)
       )

       super(ConfigNormerProxyBuildTime, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['eco_systems', 'build_time']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if not my_subcfg['activate']:
            ## build time proxy handling explicitly deactivated, nothing to do
            return my_subcfg

        if my_subcfg['inherit']:
            proxy_proxy = setdefault_none(my_subcfg, 'proxy', {})

            tmp = proxy_proxy.get('http', None)

            if tmp:
                setdefault_none(proxy_proxy, 'https', tmp)

            pcfg = self.get_parentcfg(cfg, cfgpath_abs, 2)
            tmp = copy.deepcopy(pcfg.get('proxy', {}))

            my_subcfg['proxy'] = merge_dicts(tmp, proxy_proxy)

        super(ConfigNormerProxyBuildTime, self)._handle_specifics_presub(
          cfg, my_subcfg, cfgpath_abs
        )

        return my_subcfg


class ConfigNormerProxyJavaBase(NormalizerBase):


    def _create_proxy_props(self, proxy_url, prefix, java_props):
        if not proxy_url:
            return ## noop

        tmp = urlparse(proxy_url)

        java_props.append(
          "{}.proxyHost='{}'".format(prefix, tmp.hostname)
        )

        if tmp.port:
            java_props.append(
              "{}.proxyPort={}".format(prefix, tmp.port)
            )


    @abc.abstractmethod
    def _get_base_proxy_ref(self, cfg, my_subcfg, cfgpath_abs):
        pass


    def _handle_auto_detect(self, cfg, my_subcfg, cfgpath_abs):
        return True


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self._get_base_proxy_ref(cfg, my_subcfg, cfgpath_abs)
        proxy_proxy = pcfg.get('proxy', None)

        if not proxy_proxy:
            ## no proxy defined, nothing to do
            return my_subcfg

        activate = my_subcfg['activate']

        if not activate:
            ## java proxy handling explicitly deactivated, nothing to do
            return my_subcfg

        if not self._handle_auto_detect(cfg, my_subcfg, cfgpath_abs):
            return my_subcfg

        java_props = []

        self._create_proxy_props(
          proxy_proxy.get('http', None), 'http', java_props
        )

        self._create_proxy_props(
          proxy_proxy.get('https', None), 'https', java_props
        )

        noproxy = proxy_proxy.get('noproxy', None)

        if noproxy:
            tmp = []

            for x in noproxy:
                if x[0] == '.':
                    x = '*' + x

                tmp.append(x)

            java_props.append("http.nonProxyHosts='{}'".format('|'.join(tmp)))

        switches = []
        envvars = {}

        for x in java_props:
            switches.append("-D" + x)

        # TODO: re-eval which JAVA opts vars to use: https://stackoverflow.com/q/28327620
        envvars['JAVA_OPTS'] = ' '.join(switches)

        my_subcfg['switches'] = switches
        my_subcfg['envvars'] = envvars

        return my_subcfg


class ConfigNormerProxyJava(ConfigNormerProxyJavaBase):

    def __init__(self, pluginref, *args, forced=False, **kwargs):
       self._add_defaultsetter(kwargs,
         'activate', DefaultSetterConstant('autodetect')
       )

       self.forced = forced

       super(ConfigNormerProxyJava, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['eco_systems', 'java']

    def _get_base_proxy_ref(self, cfg, my_subcfg, cfgpath_abs):
        return self.get_parentcfg(cfg, cfgpath_abs, 2)

    def _handle_auto_detect(self, cfg, my_subcfg, cfgpath_abs):
        activate = my_subcfg['activate']
        jfact = self.pluginref.get_ansible_fact('java', None)

        if jfact:
            jfact = jfact.get('active', None)

        auto_detect = False
        if activate == 'autodetect':
            auto_detect = True
            my_subcfg['auto_detect'] = auto_detect

            if not jfact and not self.forced:
                ## auto detection did not find any java
                ## installation, nothing to do
                return False

        else:

            if not self.forced:
                # use explicitly request java handling, but no
                # java could be found, this seems fishy
                display.warning(
                   "Java proxy handling explicitly requested, but no"\
                   " java installation on target detected"
                )

        my_subcfg['auto_detect'] = auto_detect
        return True


class ConfigNormerProxyJavaBuildTime(ConfigNormerProxyJavaBase):

    def __init__(self, pluginref, *args, forced=False, **kwargs):
       self._add_defaultsetter(kwargs,
         'activate', DefaultSetterConstant(True)
       )

       super(ConfigNormerProxyJavaBuildTime, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['eco_systems', 'java_buildtime']

    def _get_base_proxy_ref(self, cfg, my_subcfg, cfgpath_abs):
        tmp = self.get_parentcfg(cfg, cfgpath_abs)
        return tmp['build_time']

