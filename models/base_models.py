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
  return dj if isKey(dj) else dj.key()

class CachedModel(db.Model):
  ''' A CachedModel is a database model which tries its best to keep
  its information synced in the memcache so that fewer database hits
  are used.
  '''

  LOG_SET_DEBUG = "Memcache set (%s, %s) required"
  LOG_SET_FAIL = "Memcache set(%s, %s) failed"
  LOG_DEL_ERROR = "Memcache delete(%s) failed with error code %s"

  ENTRY = "cachedmodel_key%s"

  @classmethod
  def cacheSet(cls, value, cache_key, *args):
    logging.debug(cls.LOG_SET_DEBUG %(cache_key %args, value))
    if not memcache.set(cache_key %args, value):
      logging.error(cls.LOG_SET_FAIL % (cache_key %args, value))
    return value

  @classmethod
  def cacheDelete(cls, cache_key, *args):
    response = memcache.delete(cache_key %args)
    if response < 2:
      logging.debug(cls.LOG_DEL_ERROR %(cache_key, response))

  @classmethod
  def get(cls, keys, use_datastore=True, one_key=False):
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
      obj = memcache.get(cls.ENTRY %key)

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
      objs[i] = cls.cacheSet(obj, cls.ENTRY %key)

    return filter(None, objs)

  def put(self):
    super(CachedModel, self).put()
    self.cacheSet(self, self.ENTRY %self.key())

  def delete(self):
    self.cacheSet(None, self.ENTRY %self.key())
    super(CachedModel, self).delete()

class ApiModel(CachedModel):
  def to_json():
    pass
