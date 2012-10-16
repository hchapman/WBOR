#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Play model, and auxiliary functions.
#  A Play object corresponds to a row in the Play table in the
# datastore, which itself refers to a charted song by a Dj.


from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from base_models import *
from tracks import Album, Song
from dj import Dj
from program import Program

# Global python imports
import logging
import datetime
import logging
import itertools
import random

# Here's the idea behind last-caching:
# TODO: write description of last-caching'

class LastCachedModel(CachedModel):
  '''A model for which there is a global cache of "Last instances",
  e.g. a cache of all recently charted songs (see the Play class)'''

  LAST = None #Important that children overwrite this to avoid clashes
  LAST_ORDER = 1 #One of 1, -1
  LAST_ORDERBY = None #Get last X based on this ordering

  @classmethod
  def get_last(cls, num=-1, keys_only=False,
               before=None, after=None):
    if num != -1 and num < 1:
      return None

    only_one = False
    if num == -1:
      only_one = True
      num = 1

    cached = cls.get_cached_query(cls.LAST)

    order_str = "%s" if cls.LAST_ORDER>0 else "-%s"
    order_str = order_str%cls.LAST_ORDERBY

    if cached is None or cached.need_fetch(num):
      cached.set(cls.get_keys(num=num, order=order_str), num)

    cached.save()
    cached.need_fetch(num)

    if not cached:
      return []

    if keys_only:
      if only_one:
        return cached[-1]

      return cached[:num]
    else:
      if only_one:
        return cls.get(cached[-1])

      return sorted(cls.get(cached[:num]),
                    key=lambda elt: getattr(elt, cls.LAST_ORDERBY))

  @classmethod
  def get_last_keys(cls, num=-1, before=None, after=None):
    return cls.get_last(num=num, before=before, after=after)

  # Method to add a new element to the lastcache for this class
  @classmethod
  def add_to_last_cache(cls, key, orderby):
    cached_result = cls.get_by_index(cls.LAST, keys_only=True)
    if cached_result is None:
      last_elts = []
      last_db_count = None
    else:
      last_elts, last_db_count = cached_result

    # Realistically, we never add new plays/PSAs/etc. unless they're new.
    # so we don't have to be all fancy here. Feel free to do so.
    if not last_elts:
      last_elts = [key,]
      last_db_count = (None if last_db_count is None
                       else last_db_count + 1)
    elif orderby > getattr(cls.get(last_elts[0]), cls.LAST_ORDERBY):
      last_elts.insert(0, key)
      last_db_count = (None if last_db_count is None
                       else last_db_count + 1)

    cls.cache_set((last_elts, last_db_count), cls.LAST)

  # Utility method so that a last-cacheable entry knows how to
  # lastcache itself.
  def add_own_last_cache(self):
    self.add_to_last_cache(self.key(), orderby=getattr(self, self.LAST_ORDERBY))


class Play(LastCachedModel):
  '''A Play is an (entirely) immutable datastore object which represents
  a charted song
  '''
  LAST = "@@last_plays" # Tuple of last_plays_list, db_count
  LAST_ORDER = -1 # Sort from most recent backwards
  LAST_ORDERBY = "play_date" # How plays should be ordered in last cache
  SHOW_LAST = "last_plays_show%s" #possibly keep with show instead
  ENTRY = "play_key%s"

  # GAE Datastore properties
  song = db.ReferenceProperty(Song)
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()
  isNew = db.BooleanProperty() # TODO: Change from CamelCase to under_scores
  artist = db.StringProperty()

  @property
  def program_key(self):
    return Play.program.get_value_for_datastore(self)
  @property
  def song_key(self):
    return Play.song.get_value_for_datastore(self)

  def to_json(self):
    return {
      'key': str_or_none(self.key()),
      'song_key': str_or_none(self.song_key),
      'program_key': str_or_none(self.program_key),
      'play_date': time.mktime(self.play_date.utctimetuple()) * 1000
    }

  @classmethod
  def new(cls, song, program, artist,
          is_new=None, play_date=None,
          parent=None, key_name=None, **kwds):
    if parent is None:
      parent = program

    if play_date is None:
      play_date = datetime.datetime.now()

    play = cls(parent=parent, key_name=key_name,
               song=song, program=program,
               artist=artist, play_date=play_date,
               is_new=is_new, **kwds)

    play.is_fresh = True

    return play

  def add_to_cache(self):
    super(Play, self).add_to_cache()
    try:
      if self.is_fresh:
        self.add_own_last_cache()
    except AttributeError:
      pass
    return self

  def purge_from_cache(self):
    super(Play, self).purge_from_cache()

    return self

  @classmethod
  def get(cls, keys=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Play, cls).get(keys=keys,
                                  use_datastore=use_datastore,
                                  one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_keys(cls, before=None, after=None,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self):
    super(Play, self).put()

  # We override the get_last method to use, e.g., the parent program
  # in our queries
  @classmethod
  def get_last(cls, num=-1, keys_only=False,
               program=None, before=None, after=None):
    # We may want to get the last plays of a specific program
    # Otherwise, use the already defined super method.
    if program is None:
      return super(Play, cls).get_last(num=num, keys_only=keys_only,
                                       before=before, after=after)

    # TODO: Pass other parameters to program's method
    return program.get_last_plays(num=num)

  @classmethod
  def get_last_keys(cls, num=-1, program=None, before=None, after=None):
    return cls.get_last(num=num, keys_only=True,
                        program=program, before=before, after=after)

  ## Properties
  @property
  def p_song(self):
    return self.song
  @property
  def p_program(self):
    return self.program
  @property
  def p_play_date(self):
    return self.play_date
  @property
  def p_is_new(self):
    return self.isNew
  @property
  def p_artist(self):
    return self.artist

  ## Custom queries pertaining to plays

  # Get top-played songs and albums.
  @classmethod
  def get_top(cls, start, end, song_num=0, album_num=0, keys_only=False):
    already_cached = True
    if song_num > 0:
      cached_songs = cls.get_cached_query(cls.TOP_SONGS)
      need_fetch &= bool(cached_songs)
    if album_num > 0:
      cached_albums = cls.get_cached_query(cls.TOP_ALBUMS)
      need_fetch &= bool(cached_songs)

    if not already_cached:
      plays = cls.get_last(num=1000, after=start, before=end, new=True)



class Psa(db.Model):
  desc = db.StringProperty()
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()

class StationID(db.Model):
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()