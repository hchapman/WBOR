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
  LABEL = "permission_label%s"

  # Other memcache key constants
  BY_LABEL = "permission_label%s"
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
  def getAll(cls):
    return cls.get(order="title", num=1000)

  @classmethod
  def getByTitle(cls, title):
    return cls.get(title=title)

  @classmethod
  def login(cls, username, password):
    dj = cls.getByUsername(username)
    if dj is not None and check_password(dj.password_hash, password):
      return dj
    return None
