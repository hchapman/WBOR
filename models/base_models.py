#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file will hold parent classes of types of models

from __future__ import with_statement

# GAE Imports
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext import blobstore
from google.appengine.api import files

# Local module imports
from passwd_crypto import hash_password, check_password

# Global python imports
import logging
import datetime
import logging
import itertools

def isKey(obj):
  return isinstance(obj, db.Key) or isinstance(obj, str)

def asKey(obj):
  if isinstance(obj, str):
    return db.Key(obj)
  if isinstance(obj, db.Key):
    return obj
  if isinstance(obj, db.Model):
    return obj.key()
  return None

def asKeys(key_list):
  return filter(None, [asKey(key) for key in key_list])

class CachedModel(db.Model):
  ''' A CachedModel is a database model which tries its best to keep
  its information synced in the memcache so that fewer database hits
  are used.
  '''

  LOG_SET_DEBUG = "Memcache set (%s, %s) required"
  LOG_SET_FAIL = "Memcache set(%s, %s) failed"
  LOG_DEL_ERROR = "Memcache delete(%s) failed with error code %s"

  ENTRY = "cachedmodel_key%s"

  def __init__(self, parent=None, key_name=None, cached=True,
               **kwargs):
    self._cached = True
    super(CachedModel, self).__init__(parent=parent,
                                      key_nae=key_name, **kwargs)

  @classmethod
  def cacheSet(cls, value, cache_key, *args):
    '''
    Classmethod to access memcache.set

    Returns the cached value, for chaining purposes.
    '''
    logging.debug(cls.LOG_SET_DEBUG %(cache_key %args, value))
    if not memcache.set(cache_key %args, value):
      logging.error(cls.LOG_SET_FAIL % (cache_key %args, value))
    return value

  @classmethod
  def cacheDelete(cls, cache_key, *args):
    '''
    Classmethod to access memcache.delete
    '''
    response = memcache.delete(cache_key %args)
    if response < 2:
      logging.debug(cls.LOG_DEL_ERROR %(cache_key, response))

  @classmethod
  def cacheGet(cls, cache_key, *args):
    '''
    Classmethod to access memcache.get
    '''
    return memcache.get(cache_key %args)

  def addObjectCache(self):
    self.cacheSet(self, self.ENTRY %self.key())
  def purgeObjectCache(self):
    self.cacheDelete(self.ENTRY %self.key())

  def addToCache(self):
    '''
    Populate the memcache with self. The base only stores the object
    associated to its key, but children may wish to also cache queries
    e.g. username.

    For chaining purposes, returns self
    '''
    self.addObjectCache()
    return self

  def purgeFromCache(self):
    '''
    Remove self from the memcache where applicable. The opposite of
    "addToCache".
    '''
    self.purgeObjectCache()
    return self

  @classmethod
  def get(cls, keys, use_datastore=True, one_key=False):
    '''
    Get the data for (a) model(s) by its key(s) using the cache first,
    and then possibly datastore if necessary
    '''
    if keys is None:
      return None
    if isinstance(keys, cls):
      return keys

    if isKey(keys) or one_key:
      keys = (keys,)
      one_key = True

    if not one_key:
      objs = []
      db_fetch_keys = []

    for i, key in enumerate(keys):
      if key is None:
        return None,
      if isinstance(key, cls):
        return key
      obj = cacheGet(cls.ENTRY %key)

      if obj is not None:
        if one_key:
          return obj
        objs.append(obj)

      if one_key:
        return super(CachedModel, cls).get(key)

      # Store the key to batch fetch, and the position to place it
      if use_datastore:
        db_fetch_keys.append((i, key))

    # Improve this if possible. Use a batch fetch on non-memcache keys.
    db_fetch_zip = zip(db_fetch_keys) #[0]: idx, [1]: key
    for i, obj in zip(db_fetch_zip[0], 
                      super(CachedModel, cls).get(db_fetch_zip[1])):
      objs[i] = obj.addToCache()

    return filter(None, objs)

  @classmethod
  def getByIndex(cls, index, *args, **kwargs):
    keys_only = True if kwargs.get("keys_only") else False
    cached = cls.cacheGet(index, *args)

    if cached is not None:
      if keys_only:
        return cached
      obj = cls.get(cached)
      if obj is not None:
        return obj

    return None

  def put(self):
    '''
    Update datastore with self, and then update memcache for self.
    '''
    super(CachedModel, self).put()
    return self.addToCache()

  def delete(self):
    '''
    Remove self from memcache, then from datastore.
    '''
    super(CachedModel, self).delete()
    self.purgeFromCache()

class ApiModel(CachedModel):
  def to_json():
    pass
