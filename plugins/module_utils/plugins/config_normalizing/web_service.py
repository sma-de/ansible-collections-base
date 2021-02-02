
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.module_utils.six import iteritems
from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import NormalizerBase, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import SUBDICT_METAKEY_ANY, setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, merge_dicts


display = Display()


def connection_as_url(conn):
    display.vvv("convert connection to url: " + str(conn))
    tmp = conn['scheme'] + '://'

    u = conn['user']

    if u:
        tmp += u + '@'

    tmp += conn['host']

    p = conn['port']

    if p:
        tmp += ':' + str(p)

    return tmp


class ConfigNormerWebservice(NormalizerBase):

    def __init__(self, pluginref, *args, config_path=None, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [ 
          self.get_connection_normer(pluginref),
        ] + self.get_extra_conns(pluginref)

        self._config_path = config_path or [SUBDICT_METAKEY_ANY]
        super(ConfigNormerWebservice, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return self._config_path

    @property
    def extraconns_key(self):
        return 'extra_connections'

    def get_connection_normer(self, *args, **kwargs):
        return ConfigNormerConnection(*args, **kwargs)

    def get_extra_conns(self, *args, **kwargs):
        return []

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        mc = my_subcfg['connection']
        my_subcfg['url'] = connection_as_url(mc)

        extra_conns = my_subcfg.get(self.extraconns_key, None)

        if extra_conns:
            # if extra connections are specified
            for (k, v) in iteritems(extra_conns):
                setdefault_none(v, 'host', mc['host'])
                v['url'] = connection_as_url(v)

        return my_subcfg


class ConfigNormerGitServer(ConfigNormerWebservice):

    def get_extra_conns(self, *args, **kwargs):
        return [
          ConfigNormerConnSSH(*args, config_path=[self.extraconns_key, 'ssh'],
            extra_connection=True, **kwargs
          ),
        ]


class ConfigNormerConnection(NormalizerBase):

    def __init__(self, *args, config_path=None, default_scheme='https', 
      default_port='', extra_connection=False, **kwargs
    ):
        self._add_defaultsetter(kwargs, 
           'scheme', DefaultSetterConstant(default_scheme)
        )

        self._add_defaultsetter(kwargs, 
           'port', DefaultSetterConstant(default_port)
        )

        self._add_defaultsetter(kwargs, 
           'user', DefaultSetterConstant('')
        )

        self._config_path = config_path or ['connection']
        self.extra_connection = extra_connection
        super(ConfigNormerConnection, self).__init__(*args, **kwargs)


    @property
    def config_path(self):
        return self._config_path


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        host = my_subcfg.get('host', None)

        if not host and not self.extra_connection:
            # defaults host to parent mapping key URL-yfied, 
            # but only for main connection
            host = cfgpath_abs[-2].replace('_', '.')
            my_subcfg['host'] = host

        return my_subcfg


class ConfigNormerConnLdap(ConfigNormerConnection):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default_scheme', 'ldaps')
        kwargs.setdefault('default_port', 636)
        super(ConfigNormerConnLdap, self).__init__(*args, **kwargs)


class ConfigNormerConnSSH(ConfigNormerConnection):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default_scheme', 'ssh')
        kwargs.setdefault('default_port', 22)
        super(ConfigNormerConnSSH, self).__init__(*args, **kwargs)

