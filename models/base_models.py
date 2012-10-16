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

class NoSuchEntry(QueryError):
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
      if instance is None:
        # Class method was requested
        return self.make_unbound(klass)
      return self.make_bound(instance)

    def make_unbound(self, klass):
      @wraps(self.f)
      def wrapper(*args, **kwargs):
        pass
      return wrapper

    def make_bound(self, instance):
      @wraps(self.f)
      def wrapper(*args, **kwargs):
        return self.f(instance, *args, **kwargs)
      # This instance does not need the descriptor anymore,
      # let it find the wrapper directly next time:
      #setattr(instance, self.f.__name__, wrapper)
      return wrapper

  return descript(f)

def is_key(obj):
  return (isinstance(obj, db.Key) or
          isinstance(obj, str) or
          isinstance(obj, unicode))

def as_key(obj):
  if isinstance(obj, str) or isinstance(obj, unicode):
    return db.Key(obj)
  if isinstance(obj, db.Key):
    return obj
  if isinstance(obj, db.Model):
    return obj.key()
  return None

def as_keys(key_list):
  return filter(None, [as_key(key) for key in key_list])

class CacheItem(object):
  def __init__(self, cachekey):
    self._key = cachekey

  @classmethod
  def fetch(self, cachekey):
    pass
  def save(self, data):
    CachedModel.cache_set(data, self._key)

class CountTableCache(CacheItem):
  ''' Represents a table of keys/values in cache '''
  def __init__(self, cachekey, table=dict()):
    super(CountTableCache, self).__init__(cachekey)

class QueryCache(CacheItem):
  ''' An object representing a list of keys in the datastore
  pertaining to a query called commonly and worthy of caching.

  _dblen represents the most recent guesstimate of the (minimum)
  number of keys that an actual query would return'''
  def __init__(self, cachekey, keylist=[], maxl=False, keylen=0):
    super(QueryCache, self).__init__(cachekey)
    self.set(keylist, maxl, keylen)

  @classmethod
  def fetch(cls, cachekey):
    return cls(cachekey, *CachedModel.cache_get(cachekey))
  def save(self):
    super(QueryCache, self).save((self._data, self._maxl))

  def insert(self, idx, key):
    self._data.insert(idx, key)

  def append(self, key):
    self._data.append(key)

  def prepend(self, key):
    self.insert(0, key)

  def __len__(self):
    return len(self._data)

  def set(self, keylist, maxl=False, keylen=0):
    ''' Set the data for this QueryCache with real results from
    a datastore query'''
    self._data = keylist
    self._maxl = maxl or (len(keylist) < keylen and keylen >= 0)

  def need_fetch(self, num):
    ''' Determines if we need a new fetch from the datastore
    We need a new fetch if:
      a. We have fewer keys than the desired number AND
      b. We don't have maximal cache'''
    return (num > len(self) and not self._maxl)

  def __getitem__(self, key):
    return self._data[key]

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
                                      key_name=key_name, **kwargs)

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

    logging.error("poop")

    if is_key(keys) or one_key:
      keys = (as_key(keys),)
      one_key = True

    if not one_key:
      objs = []
      db_fetch_keys = []

    logging.error(keys)

    for i, key in enumerate(keys):
      if key is None:
        return None,
      if isinstance(key, cls):
        return key
      obj = cls.cache_get(cls.ENTRY %key)

      if not one_key and obj is not None:
        objs.append(obj)

      if one_key:
        logging.error("poop %s"% key)
        return super(CachedModel, cls).get(key)

      # Store the key to batch fetch, and the position to place it
      if use_datastore:
        db_fetch_keys.append((i, key))

    if not use_datastore:
      return keys

    # Improve this if possible. Use a batch fetch on non-memcache
    # keys.
    logging.error("Fetch keys")
    logging.error(db_fetch_keys)
    db_fetch_zip = zip(*db_fetch_keys) #[0]: idx, [1]: key
    logging.error(db_fetch_zip)
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

  @classmethod
  def get_cached_query(cls, index, *args, **kwargs):
    return QueryCache.fetch(index % args)

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
