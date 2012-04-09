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

class Play(CachedModel):
  '''A Play is an (entirely) immutable datastore object which represents
  a charted song
  '''
  LAST = "last_plays_b%s_a%s" # Tuple of last_plays_list, db_count
  SHOW_LAST = "last_plays_show%s" #possibly keep with show instead
  ENTRY = "play_key%s"

  # GAE Datastore properties
  song = db.ReferenceProperty(Song)
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()
  isNew = db.BooleanProperty()
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

    self.is_fresh = True

    return play

  @classmethod
  def add_to_last_cache(cls, key,
                        play_date=None):
    if play_date is None:
      play_date = datetime.datetime.now()

    last_plays, last_db_count = cls.get_by_index(cls.LAST, keys_only=True)
    # Realistically, we never add new plays unless they're new.
    # so we don't have to be all fancy here. Feel free to do so.
    if not last_plays:
      last_plays = [key,]
      last_db_count = (None if last_db_count is None
                       else last_db_count + 1)
    elif play_date > Play.get(last_plays[0]).play_date:
      last_plays.insert(0, key)
      last_db_count = (None if last_db_count is None
                       else last_db_count + 1)

    cls.cache_set((last_plays, last_db_count), cls.LAST)

  def add_own_last_cache(self):
    self.add_to_last_cache(self.key(), play_date=self.play_date)

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
      logging.error(keys)
      return super(Play, cls).get(keys, use_datastore=use_datastore,
                                        one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, before=None, after=None,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self):
    super(Play, self).put()

  @property
  def p_song(self):
    return self.song
  @property
  def p_program(self):
    return self.program
  @property
  def p_play_date(self):
    return self.program
  @property
  def p_is_new(self):
    return self.isNew
  @property
  def p_artist(self):
    return self.p_artist

  @classmethod
  def get_last(cls, num=-1,
               program=None, before=None, after=None,
               keys_only=False):
    if num != -1 and num < 1:
      return None

    if program is not None:
      return program.get_last_plays(num=num, before=before, after=after)

    cached = cls.get_cached_query(cls.LAST, before, after)

    if not cached or cached.need_fetch(num):
      cached.set(
        cls.get_keys(num=num, before=before, after=after))

    cached.save()

    if not cached:
      return []

    if keys_only:
      return cached[:num]
    else:
      return sorted(cls.get(cached[:num]),
                    key=lambda play: play.play_date)

  @classmethod
  def get_last_keys(cls, num=1,
                    program=None, before=None, after=None):
    cls.get_last(num=num, program=program, before=before, after=after)

class Psa(db.Model):
  desc = db.StringProperty()
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()

class StationID(db.Model):
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()