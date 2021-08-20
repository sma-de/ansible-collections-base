
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from urllib.parse import urlparse

from ansible.errors import AnsibleError

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
  DefaultSetterConstant, \
  NormalizerBase

##from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY

from ansible.utils.display import Display


display = Display()


class ConfigNormerProxy(NormalizerBase):

    def __init__(self, pluginref, *args, 
        config_path=None, force_ecosystems=False, **kwargs
    ):
        self._config_path = config_path or ['proxy']

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ConfigNormerProxyJava(pluginref, forced=force_ecosystems),
        ]

        super(ConfigNormerProxy, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return self._config_path


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        proxy_proxy = my_subcfg.get('proxy', None)

        if not proxy_proxy:
            # proxy optionally unset
            return my_subcfg

        ## default proxy values
        proxy_proxy.setdefault('https', proxy_proxy['http'])

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



class ConfigNormerProxyJava(NormalizerBase):

    def __init__(self, pluginref, *args, forced=False, **kwargs):
       self._add_defaultsetter(kwargs, 
         'activate', DefaultSetterConstant('autodetect')
       )

       self.forced = forced

       super(ConfigNormerProxyJava, self).__init__(pluginref, *args, **kwargs)


    @property
    def config_path(self):
        return ['eco_systems', 'java']


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


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, 2)
        proxy_proxy = pcfg.get('proxy', None)

        if not proxy_proxy:
            ## no proxy defined, nothing to do
            return my_subcfg

        activate = my_subcfg['activate']

        if not activate:
            ## java proxy handling explicitly deactivated, nothing to do
            return my_subcfg

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
                return my_subcfg

        else:

            if not self.forced:
                # use explicitly request java handling, but no 
                # java could be found, this seems fishy
                display.warning(
                   "Java proxy handling explicitly requested, but no"\
                   " java installation on target detected"
                )

        my_subcfg['auto_detect'] = auto_detect

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

