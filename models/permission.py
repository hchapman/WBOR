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
  def addTitleCache(cls, key, title):
    return cls.cacheSet(key, cls.TITLE, title)
  @classmethod
  def purgeTitleCache(cls, title):
    return cls.cacheDelete(cls.TITLE, title)

  def addOwnTitleCache(self):
    self.addUsernameCache(self.key(), self.title)
    return self
  def purgeOwnTitleCache(self):
    self.purgeTitleCache(self.title)

  @classmethod
  def setAllCache(cls, key_set):
    return cls.cacheSet(set([asKey(key) for key in key_set]), cls.ALL)
  @classmethod
  def addAllCache(cls, key):
    allcache = cls.cacheGet(cls.ALL)
    if not allcache:
      cls.cacheSet((key,), cls.ALL)
    else:
      cls.cacheSet(set(allcache).add(key))
    return key
  @classmethod
  def purgeAllCache(cls, key):
    allcache = cls.cacheGet(cls.ALL)
    if allcache:
      try:
        cls.cacheSet(set(allcache).remove(key))
      except KeyError:
        pass
    return key

  def addOwnAllCache(self):
    self.addAllCache(self.key())
    return self
  def purgeOwnAllCache(self):
    self.purgeAllCache(self.key())
    return self

  def addToCache(self):
    super(Permission, self).addToCache()
    self.addOwnTitleCache()
    return self

  def purgeFromCache(self):
    super(Permission, self).purgeFromCache()
    self.purgeOwnTitleCache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Permission, cls).get(keys, use_datastore=use_datastore, 
                                        one_key=one_key)

    keys = cls.getKey(title=title, order=order, num=num)  
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def getKey(cls, title=None,
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

  def addDj(self, djs):
    if isKey(djs) or isinstance(djs, Dj):
      djs = (djs,)
    
    self.dj_list = list(set(self.dj_list).
                        union(asKeys(dj_list)))

  def removeDj(self, djs):
    if isKey(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.dj_list = list(set(self.dj_list).
                        difference(asKeys(dj_list)))

  def hasDj(self, dj):
    return dj is not None and asKey(dj) in self.dj_list

  @property
  def p_title(self):
    return self.title        

  @classmethod
  def getAll(cls, keys_only=False):
    allcache = cls.getByIndex(cls.ALL, keys_only=keys_only)
    if allcache:
      return allcache

    if keys_only:
      return cls.setAllCache(cls.getKey(order="title", num=1000))
    return cls.get(keys=cls.setAllCache(cls.getKey(order="title", num=1000)))

  @classmethod
  def getByTitle(cls, title, keys_only=False):
    cached = cls.getByIndex(cls.TITLE, email, keys_only=keys_only)
    if cached is not None:
      return cached

    if keys_only:
      return cls.addTitleCache(cls.getKey(title=title), title)
    return cls.get(title=title).addOwnTitleCache()

  @classmethod
  def getKeyByTitle(cls, title):
    return cls.getByTitle(title=title, keys_only=True)
