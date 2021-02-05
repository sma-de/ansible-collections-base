

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

import collections
import urllib

from ansible.errors import AnsibleFilterError, AnsibleOptionsError
from ansible.module_utils.six import string_types
from ansible.module_utils.common._collections_compat import MutableMapping
from ansible.module_utils._text import to_text, to_native

from ansible.plugins.filter import urlsplit
from ansible.plugins.lookup import pipe
from ansible_collections.community.general.plugins.lookup import dig

from ansible_collections.smabot.base.plugins.module_utils.plugins.plugin_base import MAGIC_ARGSPECKEY_META
from ansible_collections.smabot.base.plugins.module_utils.plugins.filter_base import FilterBase

from ansible.utils.display import Display


display = Display()


URL_PARTS = {
  'scheme': (list(string_types), 'https'),
  'hostname': {
    'type': list(string_types),
    'aliases': ['host', 'server'],
    'defaulting': {
       'fallback': '127.0.0.1',
    },
  },
  'netloc': (list(string_types), ''),
  'port': (list(string_types) + [int], ''),
  'username': (list(string_types) + [type(None)], None),
  'password': (list(string_types) + [type(None)], None),
  'path': (list(string_types), ''),
  'query': (list(string_types), ''),
  'fragment': (list(string_types), ''),
}


def rebuild_netloc(value):
    hname = value.get('hostname', None)

    # if hostname is unset, this is a noop
    if not hname:
        return

    tmp = '' + (value.get('username', None) or '')

    t2 = value.get('password', None)
    if tmp and t2:
        tmp += ':' + t2

    if tmp:
        tmp += '@'

    tmp += hname

    t2 = value.get('port', None)
    if t2:
        tmp += ':' + str(t2)

    value['netloc'] = tmp


class DummyLoader():
    def get_basedir(self):
        return '.'


class UrlModderDig:

    def _urlmod_fn_dig(self, hostname):
        # TODO: this works fine, but, is it really a good idea to call a lookup plugin inside a filter plugin
        return dig.LookupModule().run(hostname)

    def _urlmod_fn_getent(self, hostname):
        # note: we need to emulate a loader here, whatever this normally 
        #   is or does, and it must provide a kind of basepath for pipe to work
        return pipe.LookupModule(loader=DummyLoader()).run(
            ["getent hosts '{}'".format(hostname)], None
        )[0].strip().split()[0]

    def __call__(self, hostname, method='dig'):
        tmp = getattr(self, '_urlmod_fn_' + method, None)

        if not tmp:
            raise AnsibleOptionsError(
               "Unknown hostname digging method '{}'".format(method)
            )

        return tmp(hostname)



## converts url dict to url string
class ToUrlFilter(FilterBase):

    FILTER_ID = 'to_url'
##    def __init__(self, *args, **kwargs):
##        super(FilterBase, self).__init__(*args, **kwargs)

    def run_specific(self, url_dict):
        if not isinstance(url_dict, collections.abc.Mapping):
            raise AnsibleOptionsError(
               "filter expects input value to be a dict, but given value"\
               " '{}' has type '{}'".format(url_dict, type(url_dict))
            )

        display.vv("[{}] :: input dict: {}".format(
           type(self).FILTER_ID, url_dict
        ))

        tmp = {}
        self._handle_taskargs(URL_PARTS, url_dict, tmp)

        display.vv("[{}] :: url dict after argspec: {}".format(
           type(self).FILTER_ID, tmp
        ))

        rebuild_netloc(tmp)

        # note: it seems that unfortunately, we cannot simple 
        #   pass a dict where the method expects a special named tuple
        tmp = to_text(urllib.parse.urlunsplit(
            urllib.parse.SplitResult(
                tmp['scheme'], tmp['netloc'], tmp['path'], 
                tmp['query'], tmp['fragment']
            )
        ))

        display.vv("[{}] :: final url string: {}".format(
           type(self).FILTER_ID, tmp
        ))

        return tmp


## modify varius url components inside an url
class UrlModFilter(FilterBase):

    FILTER_ID = 'urlmod'

    MODDER_FUNCTIONS = {
      'dig': (UrlModderDig(), ['hostname']), 
    }

##    def __init__(self, *args, **kwargs):
##        super(FilterBase, self).__init__(*args, **kwargs)

    @property
    def argspec(self):
        tmp = super(UrlModFilter, self).argspec

        for up in URL_PARTS.keys():
            tmp[up] = (list(string_types) + [collections.abc.Mapping], {})

        return tmp


    def run_specific(self, value):
        to_string = False

        if isinstance(value, string_types):
            to_string = True
            value = urlsplit.split_url(value)

        for up in URL_PARTS.keys():
            tmp = self.get_taskparam(up)

            if not tmp:
                # no modifyer given for this url part, go to next one
                continue

            if isinstance(tmp, string_types):
                tmp = { 'fnid': tmp }

            tmp['params'] = tmp.get('params', None) or {}

            modfn = type(self).MODDER_FUNCTIONS.get(tmp['fnid'], None)

            if not modfn:
                raise AnsibleOptionsError(
                   "Unknown urlmod function '{}'".format(tmp['fnid'])
                )

            modfn, t2 = modfn

            if up not in t2:
                raise AnsibleOptionsError(
                  "urlmod function '{}' does not support url"\
                  " part '{}', only: {}".format(tmp['fnid'], up, t2)
                )

            value[up] = modfn(value[up], **tmp['params'])

        display.vvv("[{}] :: url after modification: {}".format(
           type(self).FILTER_ID, value
        ))

        # rebuild netlocation for the case some of its base fields 
        # where changed
        rebuild_netloc(value)

        display.vvv("[{}] :: url after netloc rebuilding: {}".format(
           type(self).FILTER_ID, value
        ))

        if to_string:
            tmp = ToUrlFilter()
            value = tmp(value)

        return value



# ---- Ansible filters ----
class FilterModule(object):
    ''' file path related filters '''

    def filters(self):
        res = {}

        for f in [UrlModFilter, ToUrlFilter]:
            res[f.FILTER_ID] = f()

        return res

