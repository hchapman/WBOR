#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file will hold parent classes of types of models

from __future__ import with_statement

# GAE Imports
from google.appengine.api import memcache
from google.appengine.ext import db, ndb
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

import re
from unicodedata import normalize

_punct_re = re.compile(r'[!"#$%&\'()*/<=>?@\[\\\]^`{|},.]+')
_space_re = re.compile(r'[\t \-_]')

def slugify(text, delim=u'-'):
  """Generates an slightly worse ASCII-only slug."""
  result = []
  text = unicode(text)
  for word in _space_re.split(_punct_re.sub("", text.lower())):
    word = normalize('NFKD', word).encode('ascii', 'ignore')
    if word:
      result.append(word)
  return unicode(delim.join(result))

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
  return (isinstance(obj, ndb.Key) or
          isinstance(obj, str) or
          isinstance(obj, unicode))

def as_key(obj):
  if isinstance(obj, str) or isinstance(obj, unicode):
    return ndb.Key(urlsafe=obj)
  if isinstance(obj, ndb.Key):
    return obj
  if isinstance(obj, ndb.Model):
    return obj.key
  if isinstance(obj, CachedModel):
    return obj.key
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
  def __init__(self, cachekey, table=None, more=True):
    if table is None:
      table = {}
    super(CountTableCache, self).__init__(cachekey)
    self.set(table=table, more=more)

  @classmethod
  def fetch(cls, cachekey):
    result = CachedModel.cache_get(cachekey)

    if result is None:
      return cls(cachekey)
    return cls(cachekey, **result)

  def save(self):
    super(CountTableCache, self).save({'table': self._table,
                                       'more': self._more})

  def need_fetch(self, num):
    logging.error(self._more)
    return ((num > len(self.results)) and self._more) or len(self.results) < 1

  def increment(self, key, amt=1):
    if key in self._table: self._table[key] += amt
    else: self._table[key] = amt

  def set(self, table, more=None):
    if more is not None:
      self._more = more
    self._table = table

  def extend(self, keys, more=None):
    if more is not None:
      self._more = more
    for key in keys: self.increment(key)

  @property
  def results(self):
    return self._table

class QueryCache(CacheItem):
  ''' An object representing a list of keys in the datastore
  pertaining to a query called commonly and worthy of caching.

  _dblen represents the most recent guesstimate of the (minimum)
  number of keys that an actual query would return'''
  def __init__(self, cachekey, data=None, cursor=None, more=True, keylen=0):
    if data is None: data = []
    super(QueryCache, self).__init__(cachekey)
    self.set(data=data, cursor=cursor, more=more, keylen=keylen)

  @classmethod
  def fetch(cls, cachekey):
    result = CachedModel.cache_get(cachekey)

    if result is None:
      return cls(cachekey)
    elif not isinstance(result, dict):
      raise Exception("Result is not dict: %s" % result)
    else:
      return cls(cachekey, **result)

  def save(self):
    super(QueryCache, self).save({'data': self._data,
                                  'cursor': self._cursor,
                                  'more': self._more})

  def insert(self, idx, key):
    self._data.insert(idx, key)

  def append(self, key):
    self._data.append(key)

  def extend(self, keys):
    self._data.extend(keys)

  def prepend(self, key):
    self.insert(0, key)

  def remove(self, key):
    self._data.remove(key)

  def __len__(self):
    return len(self._data)

  def set(self, data, cursor=None, more=True, keylen=0):
    ''' Set the data for this QueryCache with real results from
    a datastore query'''
    self._data = data
    self._cursor = cursor
    self._more = more

  def extend_by(self, data, cursor=None, more=True, keylen=0):
    ''' Extend the data for this QueryCache with real results from
    a datastore query'''
    self.extend(data)
    self._cursor = cursor
    self._more = more

  def need_fetch(self, num):
    ''' Determines if we need a new fetch from the datastore
    We need a new fetch if:
      a. We have fewer keys than the desired number AND
      b. We don't have maximal cache'''
    return (num > len(self) and self._more) or len(self) <= 0

  def __getitem__(self, key):
    return self._data[key]

  @property
  def results(self):
    return self._data

  @property
  def cursor(self):
    return self._cursor
  @cursor.setter
  def cursor(self, cursor):
    self._cursor = cursor

  @property
  def more(self):
    return self._more
  @more.setter
  def more(self, more):
    self._more = more

class SetQueryCache(QueryCache):
  def __init__(self, cachekey, data=None, cursor=None, more=True, keylen=0,
               sort_fn=None):
    if data is None: data = set()
    super(SetQueryCache, self).__init__(cachekey, data=data, cursor=cursor,
                                     more=more, keylen=keylen)

  def set(self, data, **kwargs):
    super(SetQueryCache, self).set(set(data), **kwargs)

  def append(self, key):
    self._data.add(key)
  def prepend(self, key):
    """We're dealing with sets, so prepending and appending are the same"""
    self.append(key)
  def add(self, key):
    self.append(key)

  def remove(self, key):
    self._data.remove(key)
  def discard(self, key):
    self._data.discard(key)

  def extend(self, data):
    self._data.update(data)

class SortedQueryCache(QueryCache):
  def __init__(self, cachekey, data=None, cursor=None, more=True, keylen=0,
               sort_fn=None):
    if data is None: data = []
    super(SortedQueryCache, self).__init__(cachekey, data=data, cursor=cursor,
                                           more=more, keylen=keylen)

  def __getitem__(self, key):
    return self._data[key][0]

  def ordered_unique_insert(self, new_key, new_val, f=None):
    """Run through data until we find where to add the new key. Don't
    add the key if no spot is found"""
    for i, (key, val) in enumerate(self._data):
      if (new_val >= val if f is None else f(new_val, val)):
        if key != new_key:
          self._data.insert(i, (new_key, new_val))
        break

  def remove(self, key):
    self._data.remove(zip(*self._data)[0].index(key))

  @property
  def results(self):
    if self._data:
      return zip(*self._data)[0]
    return []

def accepts_raw(cls):
  old_init = cls.__init__
  def __init__(self, raw=None, raw_key=None, **kwargs):
    if raw is not None:
      super(cls, self).__init__(raw=raw)
      #if raw_cb: raw_cb()
      return
    elif raw_key is not None:
      super(cls, self).__init__(raw_key=raw_key)
      #if raw_cb: raw_cb()
      return
    else:
      logging.error(kwargs)
      old_init(self, **kwargs)
  cls.__init__ = __init__
  return cls

class CachedModel(object):
  _RAW = None
  ''' A CachedModel is a database model which tries its best to keep
  its information synced in the memcache so that fewer database hits
  are used.
  '''

  UNCACHED_READ = "@@@noncached_count"

  LOG_SET_DEBUG = "Memcache set (%s, %s) required"
  LOG_SET_FAIL = "Memcache set(%s, %s) failed"
  LOG_DEL_ERROR = "Memcache delete(%s) failed with error code %s"

  @property
  def key(self):
    if self._dbentry:
      return self._dbentry.key
    elif self._dbkey:
      return self._dbkey
    else:
      return None
      
  @property
  def id(self):
    return self.key.id()

  @property
  def raw(self):
    if self._dbentry is None and self._dbkey is not None:
      self._dbentry = self._dbkey.get()
    return self._dbentry

  @classmethod
  def as_object(cls, thing):
    """ Tries really, really hard to make thing into an instance of cls. """
    if isinstance(thing, cls): return thing
    if isinstance(thing, cls._RAW): return cls(raw=thing)
    if isinstance(thing, str) or isinstance(thing, unicode):
      thing = ndb.Key(urlsafe=thing)
    if isinstance(thing, ndb.Key): return cls.get(thing)
    return None

  def __init__(self, raw=None, raw_key=None, parent=None, cached=True,
               **kwargs):
    self._cached = cached
    self._dbentry = None

    if raw is not None:
      if not isinstance(raw, self._RAW):
        raise Exception(
          "Passed raw object must be of type %s or a child. "
          "Raw object was of kind %s."%
          (self._RAWKIND, raw.__class__.__name__))
      self._dbentry = raw

    elif raw_key is not None:
      if not isinstance(raw_key, ndb.Key):
        raise Exception("raw_key must be of type ndb.Key")
      if raw_key.kind() != self._RAWKIND:
        raise Exception(
          "raw_key must point to an entry of type %s"%self._RAWKIND)
      self._dbkey = raw_key
      self._dbentry = None

    else:
      self._dbentry = self._RAW(parent=parent, **kwargs)

  @classmethod
  def cache_set(cls, value, cache_key, *args):
    '''
    Classmethod to access memcache.set

    Returns the cached value, for chaining purposes.
    '''
    logging.debug(cls.LOG_SET_DEBUG %(cache_key %args, value))
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
    result = memcache.get(cache_key %args)
    return result

  def add_to_cache(self):
    '''
    Populate the memcache with self. The base only stores the object
    associated to its key, but children may wish to also cache queries
    e.g. username.

    For chaining purposes, returns self
    '''
    return self

  def purge_from_cache(self):
    '''
    Remove self from the memcache where applicable. The opposite of
    "add_to_cache".
    '''
    return self

  @classmethod
  def get(cls, keys, use_datastore=True, one_key=False):
    '''
    Get the data for (a) model(s) by its key(s) using the cache first,
    and then possibly datastore if necessary
    '''
    # TODO: Don't idiot-proof this, make rest of code more observant
    if keys is None:
      return None
    if isinstance(keys, cls):
      return keys
    elif cls._RAW is not None and isinstance(keys, cls._RAW):
      return cls(raw=keys)

    if is_key(keys) or one_key:
      return cls(raw=as_key(keys).get())

    raw_objs = filter(None, ndb.get_multi(keys))
    rslt = [cls(raw=raw) for raw in raw_objs]
    return rslt

  @classmethod
  def _get_helper(cls, page, cursor, **kwargs):
    keys = cls.get_key(page=page, cursor=cursor, **kwargs)
    if page:
      keys, cursor, more = keys

    if keys is not None:
      if page:
        return (cls.get(keys=keys),
                cursor, more)
      else:
        return cls.get(keys=keys)

    if page:
      return None, cursor, more
    else:
      return None

  @classmethod
  def get_by_index(cls, index, *args, **kwargs):
    keys_only = kwargs.get("keys_only") or False
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
    if self._dbentry:
      ret_val = self._dbentry.put()
      if ret_val:
        self.add_to_cache()
      return ret_val

    raise Exception("Cannot put() nonexistant raw database model")

  def delete(self):
    '''
    Remove self from memcache, then from datastore.
    '''
    self.purge_from_cache()
    self.key.delete()

  @classmethod
  def delete_key(cls, key):
    cls(raw_key=key).delete()

  def __isempty__(self):
    return self.raw is None

class ApiModel(CachedModel):
  def to_json():
    pass
