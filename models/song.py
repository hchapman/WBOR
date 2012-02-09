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

class Song(CachedModel):
  ENTRY = "song_key%s"

  # GAE Datastore properties
  title = db.StringProperty()
  artist = db.StringProperty()
  album = db.ReferenceProperty(Album)

  @property
  def album_key(self):
    return Song.album.get_value_for_datastore(self)

  def to_json(self):
    return {
      'key': str_or_none(self.key()),
      'title': self.title,
      'artist': self.artist,
      'album_key': str_or_none(self.album_key),
      }

  def __init__(self, parent=None, key_name=None, **kwds):
    if parent is None:
      parent = kwargs.get("album")

    super(Song, self).__init__(parent=parent, key_name=key_name, **kwds)

  def addToCache(self):
    super(Song, self).addToCache()
    return self

  def purgeFromCache(self):
    super(Song, self).purgeFromCache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Song, cls).get(keys, use_datastore=use_datastore, 
                                        one_key=one_key)

    keys = cls.getKey(title=title, order=order, num=num)  
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def getKey(cls,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self, title=None, artist=None, album=None):
    if title is not None:
      self.p_title = title
    if artist is not None:
      self.p_artist = artist
    if album is not None:
      self.p_album = album

    super(Song, self).put()

  @property
  def p_title(self):
    return self.title
  @p_title.setter
  def p_title(self, title):
    self.title = title

  @property
  def p_artist(self):
    return self.artist
  @p_artist.setter
  def p_artist(self, artist):
    self.artist = artist

  @property
  def p_album(self):
    return self.album
  @p_album.setter
  def p_album(self, album):
    self.album = album
