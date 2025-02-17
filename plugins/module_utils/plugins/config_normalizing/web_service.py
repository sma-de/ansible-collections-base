
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from urllib.parse import urlparse

from ansible.errors import AnsibleOptionsError
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

    p = conn['path']

    if p:
        if isinstance(p, list):
            p = '/'.join(p)

        tmp += '/' + str(p)

        if conn.get('force_pathend_slash', False) and tmp[-1] != '/':
            tmp += '/'

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

        return super(
          ConfigNormerWebservice, self
        )._handle_specifics_postsub(cfg, my_subcfg, cfgpath_abs)


class ConfigNormerGitServer(ConfigNormerWebservice):

    def get_extra_conns(self, *args, **kwargs):
        return [
          ConfigNormerConnSSH(*args, config_path=[self.extraconns_key, 'ssh'],
            extra_connection=True, **kwargs
          ),
        ]


class ConfigNormerConnection(NormalizerBase):

    def __init__(self, *args, config_path=None, default_scheme='https',
      default_port='', extra_connection=False, url_by_key=True,
      do_auth=False, parse_from_url=False, with_url=False,
      with_srvtype=False, srvtype_default=None, auth_vars_toplvl=None,
      auth_vars_sublvl=None, **kwargs
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

        self._add_defaultsetter(kwargs,
           'path', DefaultSetterConstant('')
        )

        self._config_path = config_path or ['connection']
        self.extra_connection = extra_connection

        self.do_auth = do_auth
        self.url_by_key = url_by_key
        self.parse_from_url = parse_from_url
        self.with_url = with_url

        self.with_srvtype = with_srvtype
        self.srvtype_default = srvtype_default
        self.auth_vars_toplvl = auth_vars_toplvl
        self.auth_vars_sublvl = auth_vars_sublvl

        super(ConfigNormerConnection, self).__init__(*args, **kwargs)


    @property
    def config_path(self):
        return self._config_path


    ## TODO: support env vars???
    def _handle_server_var(self, var, srvtype, basemap,
        mapkey, publish_ansvars, optional=False,
    ):
        display.vvv("handle server var: '{}'".format(var))
        ##display.vvv("mapkey: '{}'".format(mapkey))
        ##display.vvv("basemap: '{}'".format(basemap))

        ## check if cfgmap has an explicit value set, if so prefer that
        val = basemap.get(mapkey, None)

        ## as we got the value from cfgmap we must create corresponding ansvars
        setvars = True
        test_vars = []

        if srvtype:
          test_vars.append(var + '_' + srvtype)
        else:
          test_vars.append(var)

        if not val:
            if srvtype:
                ## 2nd (optional) source: server specific var
                val = self.pluginref.get_ansible_var(test_vars[-1], None)

                ## connection credentials are already avaible as most specific
                ## variables, dont recreate them, it would not really hurt,
                ## but security wise it gives a little more theoretically
                ## exposure to confidential data than necessary, so dont do it
                setvars = False

            if not val:
                ## final fallback source: server agnostic general var
                if srvtype:
                    test_vars.append(var)

                val = self.pluginref.get_ansible_var(test_vars[-1], None)

                if not val and not optional:
                    raise AnsibleOptionsError(
                      "mandatory connection attribute '{}' not found, set"\
                      " it either directly in cfgmap or by using one of"\
                      " these ansible variables: {}".format(mapkey, test_vars)
                    )

        if val and setvars:
            for x in test_vars:
                publish_ansvars[x] = val

        ##display.vvv("publish_ansvars post: '{}'".format(val))


    def _handle_auth(self, cfg, my_subcfg, cfgpath_abs):
        if not self.do_auth:
            return my_subcfg

        srvtype = None

        if self.with_srvtype:
            if self.srvtype_default is None:
                srvtype = my_subcfg['type']
            else:
                srvtype = my_subcfg.get('type', self.srvtype_default)

        ##
        ## note: internally we handle connection credentials by ansible
        ##   vars which might or might not yet be set, normalize this here
        ##
        publish_ansvars = {}

        tmp = self.auth_vars_toplvl or [
          ('url', 'auth_url', False),
          ('validate_certs', 'auth_valcerts', True),
        ]

        for mk, avar, opt in tmp:
            self._handle_server_var(avar, srvtype,
              my_subcfg, mk, publish_ansvars, opt
            )

        auth = setdefault_none(my_subcfg, 'auth', {})

        tmp = self.auth_vars_sublvl or [
          ('token', 'auth_token', True),
          ('username', 'auth_user', True),
          ('password', 'auth_pw', True),
        ]

        for mk, avar, opt in tmp:
            self._handle_server_var(avar, srvtype,
              auth, mk, publish_ansvars, opt
            )

        my_subcfg['_export_vars'] = {
          'ansible': publish_ansvars,
        }

        return my_subcfg


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        url = my_subcfg.get('url', None)

        if self.parse_from_url and url:
            url = urlparse(url)

            if url.username and not my_subcfg['user']:
                my_subcfg['user'] = url.username

            if url.scheme and not my_subcfg['scheme']:
                my_subcfg['scheme'] = url.scheme

            if url.port and not my_subcfg['port']:
                my_subcfg['port'] = url.port

            if url.path and not my_subcfg['path']:
                my_subcfg['path'] = url.path

            if url.hostname and not my_subcfg.get('host', None):
                my_subcfg['host'] = url.hostname

        host = my_subcfg.get('host', None)

        if not host and not self.extra_connection:
            if not self.url_by_key:
                raise AnsibleOptionsError(
                   "Mandatory subkey 'host' for {} unset".format(
                      '.'.join(cfgpath_abs)
                   )
                )

            # defaults host to parent mapping key URL-yfied, 
            # but only for main connection
            host = cfgpath_abs[-2].replace('_', '.')
            my_subcfg['host'] = host

        if self.with_url:
            my_subcfg['url'] = connection_as_url(my_subcfg)

        self._handle_auth(cfg, my_subcfg, cfgpath_abs)

        return super(
          ConfigNormerConnection, self
        )._handle_specifics_presub(cfg, my_subcfg, cfgpath_abs)



class SecureConnectionNormer(ConfigNormerConnection):

    def __init__(self, *args, **kwargs):
        setdefault_none(kwargs, 'do_auth', True)
        setdefault_none(kwargs, 'parse_from_url', True)
        setdefault_none(kwargs, 'with_url', True)
        setdefault_none(kwargs, 'url_by_key', False)

        super(SecureConnectionNormer, self).__init__(*args, **kwargs)



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


class ConfigNormerConnDocker(ConfigNormerConnection):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default_port', 5000)
        super(ConfigNormerConnDocker, self).__init__(*args, **kwargs)

