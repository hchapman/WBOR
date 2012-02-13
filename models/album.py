#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Album model, and auxiliary functions.
#  An Album object corresponds to a row in the Album table in the datastore

from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from base_models import *
from dj import Dj

# Global python imports
import logging

class Album(CachedModel):
  ENTRY = "album_key%s"

  # GAE Datastore properties
  title = db.StringProperty()
  asin = db.StringProperty()
  lower_title = db.StringProperty()
  artist = db.StringProperty()
  add_date = db.DateTimeProperty()
  isNew = db.BooleanProperty()
  songList = db.ListProperty(db.Key)
  cover_small = blobstore.BlobReferenceProperty()
  cover_large = blobstore.BlobReferenceProperty()

  @property
  def cover_small_key(self):
    return Album.cover_small.get_value_for_datastore(self)

  @property
  def cover_large_key(self):
    return Album.cover_large.get_value_for_datastore(self)

  def to_json(self):
    return {
      'key': str(self.key()),
      'title': self.title,
      'artist': self.artist,
      #'add_date': self.add_date,
      'song_list': [str_or_none(song) for song in self.songList],
      'cover_small_key': str_or_none(self.cover_small_key),
      'cover_large_key': str_or_none(self.cover_large_key),
      }

  def __init__(self, parent=None, key_name=None, **kwds):
    super(Album, self).__init__(parent=parent, key_name=key_name, **kwds)

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
    super(Album, self).addToCache()
    self.addOwnTitleCache()
    return self

  def purgeFromCache(self):
    super(Album, self).purgeFromCache()
    self.purgeOwnTitleCache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Album, cls).get(keys, use_datastore=use_datastore, 
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

    super(Album, self).put()

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
