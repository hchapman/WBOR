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
from functools import wraps

class ModelError(Exception):
  pass

class QueryError(ModelError):
  pass

def quantummethod(f):
  '''
  Class method decorator specific to the instance.

  It uses a descriptor to delay the definition of the 
  method wrapper.
  '''
  class descript(object):
    def __init__(self, f):
      self.f = f
      
    def __get__(self, instance, klass):
      print "poop"
      if instance is None:
        # Class method was requested
        return self.make_unbound(klass)
      return self.make_bound(instance)

    def make_unbound(self, klass):
      @wraps(self.f)
      def wrapper(False, *args, **kwargs):
        pass
      return wrapper

    def make_bound(self, instance):
      @wraps(self.f)
      def wrapper(*args, **kwargs):
        return self.f(instance, True, *args, **kwargs)
      # This instance does not need the descriptor anymore,
      # let it find the wrapper directly next time:
      #setattr(instance, self.f.__name__, wrapper)
      return wrapper

  return descript(f)

def is_key(obj):
  return isinstance(obj, db.Key) or isinstance(obj, str)

def as_key(obj):
  if isinstance(obj, str):
    return db.Key(obj)
  if isinstance(obj, db.Key):
    return obj
  if isinstance(obj, db.Model):
    return obj.key()
  return None

def as_keys(key_list):
  return filter(None, [as_key(key) for key in key_list])

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
  def cache_set(cls, value, cache_key, *args):
    '''
    Classmethod to access memcache.set

    Returns the cached value, for chaining purposes.
    '''
    logging.error(cls.LOG_SET_DEBUG %(cache_key %args, value))
    if not memcache.set(cache_key %args, value):
      logging.error(cls.LOG_SET_FAIL % (cache_key %args, value))
    return value

  @classmethod
  def cache_delete(cls, cache_key, *args):
    '''
    Classmethod to access memcache.delete
    '''
    response = memcache.delete(cache_key %args)
    if response < 2:
      logging.error(cls.LOG_DEL_ERROR %(cache_key %args, response))

  @classmethod
  def cache_get(cls, cache_key, *args):
    '''
    Classmethod to access memcache.get
    '''
    return memcache.get(cache_key %args)

  def add_object_cache(self):
    self.cache_set(self, self.ENTRY %self.key())
  def purge_object_cache(self):
    self.cache_delete(self.ENTRY %self.key())

  def add_to_cache(self):
    '''
    Populate the memcache with self. The base only stores the object
    associated to its key, but children may wish to also cache queries
    e.g. username.

    For chaining purposes, returns self
    '''
    self.add_object_cache()
    return self

  def purge_from_cache(self):
    '''
    Remove self from the memcache where applicable. The opposite of
    "add_to_cache".
    '''
    self.purge_object_cache()
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

    if is_key(keys) or one_key:
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
      obj = cls.cache_get(cls.ENTRY %key)

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
      objs[i] = obj.add_to_cache()

    return filter(None, objs)

  @classmethod
  def get_by_index(cls, index, *args, **kwargs):
    keys_only = True if kwargs.get("keys_only") else False
    cached = cls.cache_get(index, *args)

    if cached is not None:
      if keys_only:
        return cached
      objs = cls.get(cached)
      if objs is not None:
        return objs

    return None

  def put(self):
    '''
    Update datastore with self, and then update memcache for self.
    '''
    ret_val = super(CachedModel, self).put()
    self.add_to_cache()
    return ret_val

  def delete(self):
    '''
    Remove self from memcache, then from datastore.
    '''
    self.purge_from_cache()
    super(CachedModel, self).delete()

class ApiModel(CachedModel):
  def to_json():
    pass
