
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import NormalizerBase, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import SUBDICT_METAKEY_ANY, setdefault_none



def connection_as_url(conn):
    tmp = "{scheme}://{host}".format(**conn)

    p = conn['port']

    if p:
        tmp += ':' + str(p)

    return tmp


class ConfigNormerWebservice(NormalizerBase):

    def __init__(self, pluginref, *args, config_path=None, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          self.get_connection_normer(pluginref),
        ]

        self._config_path = config_path or [SUBDICT_METAKEY_ANY]
        super(ConfigNormerWebservice, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return self._config_path

    def get_connection_normer(self, *args, **kwargs):
        return ConfigNormerConnection(*args, **kwargs)

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg['url'] = connection_as_url(my_subcfg['connection'])
        return my_subcfg


class ConfigNormerConnection(NormalizerBase):

    def __init__(self, *args, config_path=None, default_scheme='https', default_port='', **kwargs):
        self._add_defaultsetter(kwargs, 
           'scheme', DefaultSetterConstant(default_scheme)
        )

        self._add_defaultsetter(kwargs, 
           'port', DefaultSetterConstant(default_port)
        )

        self._config_path = config_path or ['connection']
        super(ConfigNormerConnection, self).__init__(*args, **kwargs)


    @property
    def config_path(self):
        return self._config_path


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        host = my_subcfg.get('host', None)

        if not host:
            # defaults host to parent mapping key URL-yfied
            host = cfgpath_abs[-2].replace('_', '.')
            my_subcfg['host'] = host

        return my_subcfg


class ConfigNormerConnLdap(ConfigNormerConnection):

    def __init__(self, *args, config_path=None, default_scheme='https', default_port='', **kwargs):
        kwargs.setdefault('default_scheme', 'ldaps')
        kwargs.setdefault('default_port', 636)
        super(ConfigNormerConnLdap, self).__init__(*args, **kwargs)

