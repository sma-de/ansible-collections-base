
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import pathlib


from ansible.module_utils.six import string_types
##from ansible.utils.display import Display

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


##display = Display()


class ActionModule(BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        # TODO: optionally support find filters and excludes and co??
        tmp.update({
          'level': (list(string_types) + [int, bool]),
          'src': (list(string_types)),
          'dest': (list(string_types), ''),
          'allow_notempty': ([bool], False),
          'keep_orig': ([bool], False),
          'lvl_must_match': ([bool], True),
          'cmdline_limit': ([int], 1024), # <-- should be a very safe limit for linux
        })

        return tmp


    def _move_flattened_leafnode(self, leafnodes, dest):
        def run_shell(cmd):
            self.exec_module('shell', 
              modargs={'cmd': cmd},
            )

        cmd = 'mv'

        if self.get_taskparam('keep_orig'):
            cmd = 'cp -a'

        # combine multiple copy commands into a single
        # call to improve the time needed per copy
        max_size = self.get_taskparam('cmdline_limit')
        commands = []

        for l in leafnodes:
            commands.append("{} '{}' '{}'/.".format(
              cmd, str(l['path']), str(dest)
            ))

            tmp = ' && '.join(commands)

            if len(tmp) >= max_size:
                # to avoid running in issues with max cmdline
                # length we split the commands at certain treshold
                # sizes, the limit value should be "on the safe side"
                # in relatation to what the remote system can actually
                # handle, as we actually go somewhat over it with the
                # last command
                run_shell(tmp)
                commands = []

        if commands:
            run_shell(' && '.join(commands))


    def _flat_dirtree(self, src, dest, lvl, start=True):
        def get_leafs(dir_content, lvl):
            recurse = []
            leafs = []

            subdirs = []
            endnodes = []

            must_match = self.get_taskparam('lvl_must_match')

            for x in dir_content:
                if x['isdir']:
                    subdirs.append(x)
                else:
                    endnodes.append(x)

            if isinstance(lvl, int):
                # flattening on pos int number: the number says
                # how many prefix paths to kill

                if lvl == -1:
                    # complete flattening, remove subdir structure completly
                    return (endnodes, subdirs, lvl)

                # for positive flattening lvl remove subdir paths above
                # the given lvl, but keep everything below intact
                # TODO: allow optionally to ignore endnodes which lie above the flattening lvl
                if lvl > 0:
                    # flatten current lvl subdirs and continue with next lvl
                    if must_match:
                        ansible_assert(subdirs,
                           "expected to flatten '{}' more levels, but"\
                           " current src '{}' does not contain any subdirs,"\
                           " if this is acceptable set 'lvl_must_match'"\
                           " param to false".format(lvl, src)
                        )

                    return (endnodes, subdirs, lvl - 1)

                if lvl == 0:
                    # end lvl recursion, nothing more to flatten
                    return (dir_content, [], 0)

            # flattening based on string path (parts): use given path as new root
            if not lvl:
                return(dir_content, [], lvl)

            # get matching subdir (ignore any endnodes not on matching subpath)
            for d in subdirs:
                # TODO: optionally support regexes / globs
                if d == lvl[0]:
                    return ([], [d], lvl[1:])

            ansible_assert(False,
               "flattening into subdir '{}' not possible, could"\
               " not find a matching subdir in src"\
               " '{}': {}".format(lvl[1:], src, subdirs)
            )

        # TODO: allow passthrough of find filterting / excludes
        mres = self.exec_module('ansible.builtin.find',
          modargs={'paths': str(src), 'recurse': False, 'file_type': 'any'}
        )

        if start:
            if not isinstance(lvl, int):
                tmp = pathlib.Path(str(lvl))
                is_abs = tmp.is_absolute()

                tmp = tmp.parts

                if is_abs:
                    tmp = tmp[1:]

                # epxect string subpath description, convert it into path parts
                lvl = tmp

        leafs, recurse, nxtlvl = get_leafs(mres['files'], lvl)

        self._move_flattened_leafnode(leafs, dest)

        for d in recurse:
            self._flat_dirtree(d['path'], dest, nxtlvl, start=False)


    def run_specific(self, result):
        src = self.get_taskparam('src')
        dest = self.get_taskparam('dest')
        lvl = self.get_taskparam('level')

        if not lvl:
            # TODO: throw error for this case??
            return # noop

        if isinstance(lvl, bool):
            lvl = -1

        keep_orig = self.get_taskparam('keep_orig')

        if not dest:
            dest = src

        src  = pathlib.Path(src)
        dest = pathlib.Path(dest)

        tmp_dest = None

        if dest.is_relative_to(src) and not keep_orig:
            # dest is the same or a subpath of src and src
            # should also be removed, this means we need
            # a temporary workdir
            tmp_dest = self.exec_module('ansible.builtin.tempfile',
              modargs={'state': 'directory'}
            )

            tmp_dest = tmp_dest['path']

        else:

            # check if dest exists and is a dir
            mres = self.exec_module('ansible.builtin.stat',
              modargs={'path': str(dest)}
            )

            mres = mres['stat']

            # if not create it
            if mres['exists']:
                ansible_assert(mres['isdir'],
                   "given dest '{}' exists already on remote,"
                   "but is not a dir: {}".format(dest, mres)
                )

                if not self.get_taskparam('allow_notempty'):
                    # assert that dest dir is empty
                    mres = self.exec_module('ansible.builtin.find',
                       modargs={'paths': str(dest), 'recurse': False}
                    )

                    ansible_assert(mres['examined '] == 0,
                       "given dest dir '{}' is not empty, set"\
                       " 'allow_notempty' to true if this is"\
                       " acceptable".format(dest)
                    )

            else:

                # TODO: allow to passthrough more creation options
                self.exec_module('ansible.builtin.file',
                   modargs={'state': 'directory', 'path': str(dest)}
                )

        try:
            # find all files in src, iterate over them
            # flatten src file path
            # move or copy to dest
            self._flat_dirtree(src, tmp_dest or dest, lvl)

            if not keep_orig:
                # remove src
                self.exec_module('ansible.builtin.file',
                   modargs={'state': 'absent', 'path': str(src)}
                )

            if tmp_dest:
                # move tmp dir content to final dest
                self.exec_module('ansible.builtin.copy',
                  modargs={'src': str(tmp_dest) + '/',
                    'dest': str(dest) + '/', 'remote_src': True
                  }
                )

        finally:

            if tmp_dest:
                # remove tmp workdir
                self.exec_module('ansible.builtin.file',
                   modargs={'state': 'absent', 'path': tmp_dest}
                )

        # TODO: add meta infos for what is going on here
        return result

