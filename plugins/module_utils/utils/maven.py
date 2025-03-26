#!/usr/bin/env python

# TODO: copyright, owner license
#

"""
TODO module / file doc string
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import urllib
import xml.etree.ElementTree as ET

from ansible.errors import AnsibleAssertionError
##from ansible.module_utils.six import string_types

from ansible.module_utils import urls as ansible_urls

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import \
  ansible_assert


def get_metadata_file_url(art_id=None, group_id=None,
    repo_url='https://repo1.maven.org/maven2', **kwargs
):
    return "{}/{}/{}/maven-metadata.xml".format(
        repo_url, group_id.replace('.', '/'), art_id
    )


def parse_metadata_file(url_settings=None, **kwargs):
    url_settings = url_settings or {}

    try:
      rsp = ansible_urls.open_url(
         get_metadata_file_url(**kwargs), **url_settings
      )

    except urllib.error.HTTPError as e:
        if e.code == 404:
            e.msg = (
               "Unable to load maven-metadata file from url '{}'."\
               " Ensure that repo url and maven coordinates are correct"\
               " (artifactId: '{}', groupId: '{}')".format(e.url,
                  kwargs.get('art_id', None), kwargs.get('group_id', None)
               )
            )

        raise e

    return ET.fromstring(rsp.read())


def get_artifact_versions(versions_only=False,
    latest_only=False, release_only=False, **kwargs
):
    meta_xml = parse_metadata_file(**kwargs)

    res = {}

    get_latest = latest_only or (not release_only and not versions_only)
    get_release = release_only or (not latest_only and not versions_only)

    if get_latest:
        tmp = meta_xml.find("./versioning/latest")

        if tmp:
            tmp = tmp.text

        if latest_only:
            return tmp

        res['latest'] = tmp

    if get_release:
        tmp = meta_xml.find("./versioning/release")

        if tmp:
            tmp = tmp.text

        if release_only:
            return tmp

        res['release'] = tmp

    vers = []
    for x in meta_xml.findall("./versioning/versions/version"):
        vers.append(x.text)

    if versions_only:
        return vers

    res['versions'] = vers
    return res

