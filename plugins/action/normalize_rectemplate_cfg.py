
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import pathlib
import os

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBase, NormalizerBase, NormalizerNamed, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.proxy import ConfigNormerProxy
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY, setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



def check_types_filter(cfg):
    setfilter = cfg.get('types', None)

    if setfilter:
        # dont change pre-existing filter, but do some sanity checks
        tmp = None

        if isinstance(setfilter, list):
            tmp = setfilter
        elif not setfilter.get('exclude', False):
            tmp = setfilter['list']

        if tmp:
            ansible_assert('directory' not in tmp, 
               "User explicitly specified a types filter criteria for"\
               " recursive templating which includes dirs. This does"\
               " not make sense as templating only works on files."
            )

    return setfilter


class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          CommonFilterNormalizer(pluginref),
          CommonPathModNormalizer(pluginref),
          PathsNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class CommonFilterNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(CommonFilterNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['filter_criteria']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        tf = check_types_filter(my_subcfg)

        if not tf:
            # set default types filter, as templating internally only 
            # works on files exclude dirs
            my_subcfg['types'] = {
              'exclude': True,
              'list': ['directory']
            }

        return my_subcfg


class CommonPathModNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           ## on default remove j2 as file ending, as we expect 
           ## jinja templates to end with it, and if they do, we 
           ## also expect that wanted target name has this ending stripped
           'strip_endings', DefaultSetterConstant(['j2'])
        )

        super(CommonPathModNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['path_modifiers']


class PathsNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          CopyItemNormalizer(pluginref, 
             filterable=True, moddable=True
          ),
        ]

        super(PathsNormalizer, self).__init__(pluginref, *args, **kwargs)

    @property
    def config_path(self):
        return ['paths']


class CopyItemNormalizer(NormalizerNamed):

    def __init__(self, pluginref, *args, 
        filterable=False, moddable=None, **kwargs
    ):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          CopyItemCopyApiNormalizer(pluginref),
        ]

        super(CopyItemNormalizer, self).__init__(pluginref, *args, **kwargs)
        self.filterable = filterable
        self.moddable = moddable

    @property
    def config_path(self):
        return [SUBDICT_METAKEY_ANY]

    @property
    def name_key(self):
        return 'src'

    @property
    def simpleform_key(self):
        return 'dest'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        src = my_subcfg['src']

        src_suffix = ''

        if src[-1] == '/':
            src_suffix = '/'

        ## note: this is actually only relative when source_root is 
        ##   set and src is given as relative, if src is given as 
        ##   abspath which is allowed, this is actually not recursive
        my_subcfg['src_rel'] = src
        my_subcfg['relative'] = False

        src = pathlib.PurePosixPath(src)

        if not src.is_absolute():
            my_subcfg['relative'] = True

            ## note: for relative paths, source root must be set
            src = pathlib.PurePosixPath(cfg['source_root']) / src

        my_subcfg['src'] = str(src) + src_suffix

        if self.filterable:
            deffilter = cfg.get('filter_criteria', {})

            fcsubd = my_subcfg.get('filter_criteria', None) or {}
            tf = check_types_filter(fcsubd)

            if not tf and not fcsubd:
                fcsubd.update(deffilter)

            my_subcfg['filter_criteria'] = fcsubd

        if self.moddable:
            defmods = cfg.get('path_modifiers', {})

            mypms = my_subcfg.get('filter_criteria', None) or {}

            if not mypms:
                mypms.update(defmods)

            my_subcfg['path_modifiers'] = defmods

        return my_subcfg


##
## note: we forward this atm to both, the copy module and the template 
##   module, fortunately there interfaces are more or less the same, 
##   it might be still possible that we come to a point in the future 
##   where we must differentiate between them
##
class CopyItemCopyApiNormalizer(NormalizerBase):

    def __init__(self, *args, **kwargs):
        ## note: force is needed here to replace files 
        ##   when they have changed
        self._add_defaultsetter(kwargs, 
           'force', DefaultSetterConstant(True)
        )

        super(CopyItemCopyApiNormalizer, self).__init__(
           *args, **kwargs
        )

    @property
    def config_path(self):
        return ['copy_api']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        parent_cfg = self.get_parentcfg(cfg, cfgpath_abs)

        ##
        ## note: on default (if mode is unset) ansible will create 
        ##   files with the default file mode of the remot system, 
        ##   but as we always have a source file here I would prefer, 
        ##   that on default (if mode is unset) the mode of the source 
        ##   file is kept, this can be simply done by using the 
        ##   keyword 'preserve'
        ##
        ## TODO: is preserve also supported by template module or only by copy module (is it not mentioned in the docu of template)
        ##
        mode = setdefault_none(my_subcfg, 'mode',
          self.pluginref.get_ansible_var(
            # note: as this is somewhat "heavy" to change 
            #   the default behaviour of filemode we 
            #   optionally allow to generally change the 
            #   default by a global default ansvar
            'ANSIBLE_DEFAULT_FILEMODE', default='preserve'
          )
        )

        # note: as we map None to "use our default" we use a 
        #   special value here to say use ansible builtin default
        if mode == 'ANSIBLE_DEFAULT':
            mode = None

        my_subcfg.update(
          self.copy_from_parent(cfg, cfgpath_abs, ['src', 'dest'])
        )

        return my_subcfg


class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            ConfigRootNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'template_recursive_args'

    @property
    def supports_merging(self):
        return False

