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
  '''A Song is an (entirely) immutable datastore object which represents
  a song; e.g. one played in the past or an element in a list of tracks.
  '''
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

  def __init__(self, title, artist, album=None, 
               parent=None, key_name=None, **kwds):
    if parent is None:
      parent = kwargs.get("album")
    
    super(Song, self).__init__(parent=parent, key_name=key_name,
                               title=title, artist=artist, **kwds)
    if album is not None:
      self.album = album

  def add_to_cache(self):
    super(Song, self).add_to_cache()
    return self

  def purge_from_cache(self):
    super(Song, self).purge_from_cache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Song, cls).get(keys, use_datastore=use_datastore, 
                                        one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)  
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self):
    return super(Song, self).put()

  @property
  def p_title(self):
    return self.title
  @property
  def p_artist(self):
    return self.artist
  @property
  def p_album(self):
    return self.album
