#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Permission model, and auxiliary functions.
#  A Permission object corresponds to a row in the Permission table in the datastore

from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from base_models import *
from dj import Dj

# Global python imports
import logging
import datetime
import logging
import itertools
import random

class NoSuchTitle(NoSuchEntry):
  pass

class Permission(CachedModel):
  ENTRY = "permission_key%s"

  # Other memcache key constants
  TITLE = "permission_title%s"
  ALL = "all_permissions_cache"

  DJ_EDIT = "Manage DJs"
  PROGRAM_EDIT = "Manage Programs"
  PERMISSION_EDIT = "Manage Permissions"
  ALBUM_EDIT = "Manage Albums"
  GENRE_EDIT = "Manage Genres"
  BLOG_EDIT = "Manage Blog"
  EVENT_EDIT = "Manage Events"

  PERMISSIONS = (DJ_EDIT,
                 PROGRAM_EDIT,
                 PERMISSION_EDIT,
                 ALBUM_EDIT,
                 GENRE_EDIT,
                 BLOG_EDIT,
                 EVENT_EDIT,)

  # GAE Datastore properties
  title = db.StringProperty()
  dj_list = db.ListProperty(db.Key)

  def __init__(self, parent=None, key_name=None, **kwds):
    super(Permission, self).__init__(parent=parent, key_name=key_name, **kwds)

  @classmethod
  def add_title_cache(cls, key, title):
    return cls.cache_set(key, cls.TITLE, title)
  @classmethod
  def purge_title_cache(cls, title):
    return cls.cache_delete(cls.TITLE, title)

  def add_own_title_cache(self):
    self.add_title_cache(self.key(), self.title)
    return self
  def purge_own_title_cache(self):
    self.purge_title_cache(self.title)

  @classmethod
  def set_all_cache(cls, key_set):
    return cls.cache_set(set([as_key(key) for key in key_set]), cls.ALL)
  @classmethod
  def add_all_cache(cls, key):
    allcache = cls.cache_get(cls.ALL)
    if not allcache:
      cls.cache_set((key,), cls.ALL)
    else:
      cls.cache_set(set(allcache).add(key))
    return key
  @classmethod
  def purge_all_cache(cls, key):
    allcache = cls.cache_get(cls.ALL)
    if allcache:
      try:
        cls.cache_set(set(allcache).remove(key))
      except KeyError:
        pass
    return key

  def add_own_all_cache(self):
    self.add_all_cache(self.key())
    return self
  def purge_own_all_cache(self):
    self.purge_all_cache(self.key())
    return self

  def add_to_cache(self):
    super(Permission, self).add_to_cache()
    self.add_own_title_cache()
    return self

  def purge_from_cache(self):
    super(Permission, self).purge_from_cache()
    self.purge_own_title_cache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Permission, cls).get(keys, use_datastore=use_datastore,
                                        one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, title=None,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if title is not None:
      query.filter("title =", title)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self, dj_list=None):
    if dj_list is not None:
      self.dj_list = dj_list

    return super(Permission, self).put()

  def add_dj(self, djs):
    if is_key(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.dj_list = list(set(self.dj_list).
                        union(as_keys(dj_list)))

  def remove_dj(self, djs):
    if is_key(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.dj_list = list(set(self.dj_list).
                        difference(as_keys(dj_list)))

  def has_dj(self, dj):
    return dj is not None and as_key(dj) in self.dj_list

  @property
  def p_title(self):
    return self.title

  @classmethod
  def get_all(cls, keys_only=False):
    allcache = cls.get_by_index(cls.ALL, keys_only=keys_only)
    if allcache:
      return allcache

    if keys_only:
      return cls.set_all_cache(cls.get_key(order="title", num=1000))
    return cls.get(keys=cls.set_all_cache(cls.get_key(order="title", num=1000)))

  @classmethod
  def get_by_title(cls, title, keys_only=False):
    cached = cls.get_by_index(cls.TITLE, title, keys_only=keys_only)
    if cached is not None:
      return cached

    key = cls.get_key(title=title)
    if key is not None:
      if keys_only:
        return cls.add_title_cache(key, title)
      permission = cls.get(key)
      if permission is not None:
        return permission.add_own_title_cache()
    raise NoSuchTitle()

  @classmethod
  def get_key_by_title(cls, title):
    return cls.get_by_title(title=title, keys_only=True)
