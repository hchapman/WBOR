#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Permission model, and auxiliary functions.
#  A Dj object corresponds to a row in the Permission table in the datastore

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
  LABEL = "permission_label%s"
  ALL = "all_permissions_cache"

  PERM_DJ_EDIT = "Manage DJs"
  PERM_PROGRAM_EDIT = "Manage Programs"
  PERM_PERMISSION_EDIT = "Manage Permissions"
  PERM_ALBUM_EDIT = "Manage Albums"
  PERM_GENRE_EDIT = "Manage Genres"
  PERM_BLOG_EDIT = "Manage Blog"
  PERM_EVENT_EDIT = "Manage Events"

  PERMISSIONS = (PERM_DJ_EDIT,
                 PERM_PROGRAM_EDIT,
                 PERM_PERMISSION_EDIT,
                 PERM_ALBUM_EDIT,
                 PERM_GENRE_EDIT,
                 PERM_BLOG_EDIT,
                 PERM_EVENT_EDIT,)

  # GAE Datastore properties
  title = db.StringProperty()
  dj_list = db.ListProperty(db.Key)

  def __init__(self, parent=None, key_name=None, **kwds):
    super(Permission, self).__init__(parent=parent, key_name=key_name, **kwds)

  @classmethod
  def addLabelCache(cls, key, label):
    return cls.cacheSet(key, cls.LABEL, label)
  @classmethod
  def purgeLabelCache(cls, label):
    return cls.cacheDelete(cls.LABEL, label)

  def addOwnLabelCache(self):
    self.addUsernameCache(self.key(), self.label)
    return self
  def purgeOwnLabelCache(self):
    self.purgeLabelCache(self.label)

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
    self.addOwnLabelCache()
    self.addOwnAllCache()
    return self

  def purgeFromCache(self):
    super(Permission, self).purgeFromCache()
    self.purgeOwnLabelCache()
    self.purgeOwnAllCache()
    return self

  @classmethod
  def get(cls, keys=None,
          label=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Permission, cls).get(keys, use_datastore=use_datastore, 
                                        one_key=one_key)

    keys = cls.getKey(label=label, order=order, num=num)  
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def getKey(cls, label=None,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if label is not None:
      query.filter("title =", label)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self, dj_list=None):
    if dj_list is not None:
      self.dj_list = dj_list

    super(Permission, self).put()

  def addDj(self, dj):
    if isKey(djs) or isinstance(djs, Dj):
      djs = (djs,)
    
    self.dj_list = list(set(dj_list).
                        union(asKeys(dj_list)))

  def removeDj(self, djs):
    if isKey(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.dj_list = list(set(dj_list).
                        difference(asKeys(dj_list)))

  @classmethod
  def p_label(self):
    return self.label

  @classmethod
  def p_dj_list(self):
    pass #TODO: implement cached list pointing to dj_list property
        

  @classmethod
  def getAll(cls, keys_only=False):
    allcache = cls.getByIndex(cls.ALL, keys_only=keys_only)
    if allcache:
      return allcache

    if keys_only:
      return cls.setAllCache(cls.getKey(order="title", num=1000))
    return cls.get(keys=cls.setAllCache(cls.getKey(order="title", num=1000)))

  @classmethod
  def getByLabel(cls, label, keys_only=False):
    cached = cls.getByIndex(cls.LABEL, email, keys_only=keys_only)
    if cached is not None:
      return cached

    if keys_only:
      return cls.addLabelCache(cls.getKey(label=label), label)
    return cls.get(label=label).addOwnLabelCache()

  @classmethod
  def getKeyByLabel(cls, label):
    return cls.getByLabel(label=label, keys_only=True)
