
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import ssl

from ansible.errors import AnsibleOptionsError, AnsibleError##, AnsibleModuleError##
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible.utils.display import Display


display = Display()


def combine_ldap_filter(*filtlist, method='&', enclose=True):
    tmp = method + ''.join(map(lambda x: '(' + str(x) + ')', filtlist))

    if enclose:
        tmp = '(' + tmp + ')'

    return tmp


class LdapConnection:

    def __init__(self, server, user=None, pw=None, domain=None, base_dn=None):
        import ldap3

        # TODO: support more configuration options (different tls settings, ...)
        self.server = ldap3.Server(server, get_info=ldap3.ALL, 
          tls=ldap3.Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLSv1)
        )

        self.user = None
        self.domain = domain

        self.user = user
        self.usrpw = pw
        self.base_dn = base_dn
        self._connection = None


    def search(self, connection=None, **search_criteria):
        conn = connection or self.default_connection

        search_criteria.setdefault('search_base', self.base_dn)
        search_criteria.setdefault('paged_size', 5)

        ## note: this returns a paginated generator
        return conn.extend.standard.paged_search(**search_criteria)


    def get_user_object(self, user=None, check_attrs=None, empty_match_error=False, **kwargs):
        check_attrs = check_attrs or ['userPrincipalName']
        user = user or self.upn
 
        if not isinstance(user, list):
            user = [user]

        sfilt = []

        for ca in check_attrs:
            for u in user:
                sfilt.append(ca + '=' + u)

        sfilt = combine_ldap_filter(
           combine_ldap_filter(*sfilt, method='|', enclose=False), 
           'objectClass=person'
        )

        display.vvv(
           'LDAP :: get_user_object :: final search filter: ' + sfilt
        )

        res = list(filter(lambda x: x['type'] == 'searchResEntry', 
           self.search(search_filter=sfilt, **kwargs)
        ))
 
        if res:
            ansible_assert(len(res) == 1, 
               "bad result for getting ldap user object, expect to match"\
               " just one user, but found '{}': {}".format(len(res), res)
            )

            return res[0]
        elif empty_match_error:
            raise AnsibleError(
               "could not find matching ldap object for given"\
               " user: {}".format(user)
            )
 
        return res

    def _raise_error_when_operation_failed(self, opret, conn, msg=None):
        if not opret:
            msg = msg or 'LDAP operation failed: '
            raise AnsibleError(msg + str(conn.result))

    def rebind(self, connection=None, **binding_args):
        connection = connection or self.default_connection
        display.vvv("LDAP :: rebinding :: final args: " + str(binding_args))

        return self._raise_error_when_operation_failed(
            connection.rebind(**binding_args), connection, 
            msg="LDAP :: rebinding connection with auth user"\
                " '{}' failed: ".format(binding_args['user'])
        )

    def init_connection(self):
        import ldap3
        display.vv('LDAP: init connection ...')

        tmp = ldap3.Connection(self.server, auto_bind=True, 
           ## note: instead of checking the return value of each 
           ##   operation one could theoretically set this flag I 
           ##   assume, but unfortunately this is at least for my 
           ##   version broken in the sense that if activated 
           ##   opening / binding the connection already fails, 
           ##   which otherwise works totally fine
           ##raise_exceptions=True
        )

        display.vv('LDAP: new connection: ' + str(tmp))
        display.vvv('LDAP: server info: ' + str(self.server.info))

        ## note: ssl by secure port and upgrading an insecure connection 
        ##   later by start_tls are somewhat independend, at least in 
        ##   the sense that tls_started flag is false when connection 
        ##   was established over secure port
        if not self.server.ssl and not tmp.tls_started:
            display.vv('LDAP: starting tls ...')
            self._raise_error_when_operation_failed(
               tmp.start_tls(), tmp, msg='LDAP :: starting tls failed: '
            )

        usr = self.user

        if usr:
            display.vv('LDAP: rebinding with given user: {}'.format(usr))
            self.rebind(connection=tmp, user=usr, password=self.usrpw)

        display.vv('LDAP: final connection context: ' + str(tmp))
        self._connection = tmp


    @property
    def default_connection(self):
        if not self._connection:
            self.init_connection()
        return self._connection

    @property
    def upn(self):
        return self._upn

    @property
    def user(self):
        return self._user

    @user.setter
    def user(self, value):
        self._user = value
        self._update_upn()

    @property
    def domain(self):
        return self._domain

    @domain.setter
    def domain(self, value):
        self._domain = value
        self._update_upn()


    def _update_upn(self):
        tmp = self.user

        if not tmp:
            self._upn = None
            return

        tmp = tmp.split('@')

        ansible_assert(len(tmp) <= 2, 
           "ldap user cannot contain more than one '@': {}".format(self.user)
        )

        if len(tmp) < 2:
            domain = self.domain

            if not domain:
                raise AnsibleOptionsError(
                   "could not determine UPN, either give user as"\
                   " complete principal name ('foo@bar.com') or set domain parameter"
                )

            tmp.append(domain)

        self._upn = '@'.join(tmp)


class LdapActionBase(BaseAction):

    def __init__(self, *args, ldap_connection_type=None, **kwargs):
        super(LdapActionBase, self).__init__(*args, **kwargs)
        self.ldap_connection_type = ldap_connection_type or LdapConnection

    @property
    def argspec(self):
        tmp = super(LdapActionBase, self).argspec

        tmp.update({
          'server': {
            'type': list(string_types),
            'defaulting': {
              'ansvar': ['awxcred_ldap_server'],
##         'env': '', # TODO
            },
          },

          'domain': {
            'type': list(string_types),
            'defaulting': {
              'ansvar': ['awxcred_ldap_domain'],
##         'env': '', # TODO
            },
          },

          'auth_user': {
            'type': list(string_types),
            'defaulting': {
              'ansvar': ['awxcred_ldap_user'],
##         'env': '', # TODO
            },
          },

          'auth_pw': {
            'type': list(string_types),
            'defaulting': {
              'ansvar': ['awxcred_ldap_pw'],
##         'env': '', # TODO
            },
          },

          'base_dn': {
            'type': list(string_types),
            'defaulting': {
              'ansvar': ['awxcred_ldap_base_dn'],
##         'env': '', # TODO
            },
          },
        })

        return tmp

    @abc.abstractmethod
    def run_ldap_tasks(self, result):
        pass

    def run_specific(self, result):
        ## init ldap connection
        self.ldap_connection = self.ldap_connection_type(
            self.get_taskparam('server'), 
            user=self.get_taskparam('auth_user'), 
            pw=self.get_taskparam('auth_pw'), 
            domain=self.get_taskparam('domain'), 
            base_dn=self.get_taskparam('base_dn')
        )

        return self.run_ldap_tasks(result)

