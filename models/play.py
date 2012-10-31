#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Play model, and auxiliary functions.
#  A Play object corresponds to a row in the Play table in the
# datastore, which itself refers to a charted song by a Dj.


from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db, ndb

from _raw_models import Program as RawProgram
from _raw_models import Play as RawPlay
from _raw_models import Psa as RawPsa
from _raw_models import StationID as RawStationID

# Local module imports
from base_models import *
from tracks import Album, Song
from dj import Dj

# Global python imports
import logging
import datetime
import logging
import itertools
import random

from itertools import izip

class Program(CachedModel):
  _RAW = RawProgram

  ## Functions for getting and setting Programs
  EXPIRE = 360  # Program cache lasts for one hour maximum

  BY_DJ_ENTRY = "programs_by_dj%s"

  def __init__(self, raw=None, raw_key=None, title="", slug="", desc="",
               dj_list=None, page_html="", current=True):
    if raw is not None:
      super(Program, self).__init__(raw=raw)
      return
    elif raw_key is not None:
      super(Program, self).__init__(raw_key=raw_key)
      return

    if dj_list is None: dj_list = []
    if not title:
      raise Exception("Insufficient data to create show")

    super(Program, self).__init__(title=title,
                                  slug=slugify(slug if slug else title),
                                  desc=desc,
                                  dj_list=[as_key(dj) for dj in dj_list if dj],
                                  page_html=page_html,
                                  current=bool(current))

  @classmethod
  def new(cls, title, slug, desc, dj_list, page_html, current=True):
    return cls(title=title, slug=slug, desc=desc, dj_list=dj_list,
               page_html=page_html, current=True)

  def put(self):
    return super(Program, self).put()

  @classmethod
  def get(cls, keys=None, slug=None, dj=None, order=None, num=-1,
          use_datastore=True, one_key=False):
    # We're getting the program by key
    if keys is not None:
      return super(Program, cls).get(keys,
                                     use_datastore=use_datastore,
                                     one_key=one_key)

    # We're using a query on programs instead
    keys = cls.get_key(slug=slug, dj=dj, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, slug=None, dj=None, order=None, num=-1):
    query = cls._RAW.query()

    if slug is not None:
      query = query.filter(RawProgram.slug == slug)
    if dj is not None:
      query = query.filter(RawProgram.dj_list == as_key(dj))

    if order is not None:
      query = query.order(order)

    # Consider adding query caching here, if necessary
    if num == -1:
      return query.get(keys_only=True)
    return query.fetch(num, keys_only=True)

  # Query-caching method if searching by dj
  @classmethod
  def get_by_dj(cls, dj, keys_only=False, num=-1):
    if num != -1 and num < 1:
      return None

    dj = as_key(dj)

    only_one = False
    if num == -1:
      only_one = True
      num = 1

    cached = QueryCache.fetch(cls.BY_DJ_ENTRY % dj)

    if cached.need_fetch(num):
      cached.set(cls.get_key(num=num), num)
      cached.save()

    if not cached:
      return []

    if keys_only:
      if only_one:
        return cached.results[-1]
      return cached.results[:num]
    else:
      if only_one:
        return cls.get(cached.results[-1])
      return cls.get(cached.results[:num])

  @property
  def title(self):
    return self.raw.title
  @title.setter
  def title(self, title):
    if not title:
      raise ModelError("A show's title cannot be blank")
    self.raw.title = title.strip()

  @property
  def slug(self):
    return self.raw.slug
  @slug.setter
  def slug(self, slug):
    self.raw.slug = slugify(slug if slug else title)

  @property
  def desc(self):
    return self.raw.desc
  @desc.setter
  def desc(self, desc):
    self.raw.desc = desc.strip() if desc else ""

  @property
  def page_html(self):
    return self.raw.page_html
  @page_html.setter
  def page_html(self, page_html):
    self.raw.page_html = page_html.strip() if page_html else ""

  @property
  def current(self):
    return self.raw.current
  @current.setter
  def current(self, current):
    self.raw.current = bool(current)

  @property
  def dj_list(self):
    return self.raw.dj_list
  @dj_list.setter
  def dj_list(self, dj_list):
    self.raw.dj_list = [as_key(dj) for dj in dj_list if dj]

  @property
  def num_top_plays(self):
    return self.raw.top_playcounts[0]
  @property
  def top_artists(self):
    return zip(self.raw.top_artists, self.raw.top_playcounts)

  def get_last_plays(self, *args, **kwargs):
    return []

  # This is a helper method to update which artists are recorded as
  # the most-played artists for a given program.
  # If the artist just played is already within the top 10, then
  # increment the count by one and re-order.
  # Otherwise, make an 11-element list of the current top 10 artists played
  # along with the just-played artist's name and playcount;
  # sort this list, grab the first 10 elements and save them.
  def update_top_artists(self, artist):
    # a dictionary which looks like (artist_name => playcount)
    playcounts = dict(self.top_artists)
    logging.error(playcounts)
    if artist in playcounts:
      playcounts[artist] = playcounts[artist] + 1
    else:
      playcounts[artist] = self.get_artist_play_count(artist)

    logging.error(playcounts)
    playcounts = list(playcounts.iteritems())
    logging.error(playcounts)
    playcounts = sorted(playcounts, key=(lambda x: x[1]), reverse=True)
    playcounts = playcounts[:10]
    self.raw.top_artists = [str(p[0]) for p in playcounts]
    self.raw.top_playcounts = [int(p[1]) for p in playcounts]

  def get_artist_play_count(self, artist):
    return len(Play.get_key(program=self.key,
                            artist=artist, num=1000))

  def to_json(self):
    return {
      'key': str_or_none(self.key),
      'title': self.title,
      'slug': self.slug,
      'desc': self.desc,
      'dj_list': [str_or_none(dj_key) for dj_key in self.dj_list],
      'page_html': self.page_html,
      'top_artists': self.top_artists,
      'top_playcounts': self.top_playcounts,
      'current': self.current
    }

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

    cached = SortedQueryCache.fetch(cls.LAST)

    last = []
    cached_keys = []
    if cached.need_fetch(num):
      try:
        num_to_fetch = num - len(cached)
        last, cursor, more = cls.get(num=num_to_fetch,
                                     order=cls.LAST_ORDERBY,
                                     page=True, cursor=cached.cursor)
        cached_keys = cached.results
        cached.extend_by([(obj.key, obj._orderby) for obj in last],
                         cursor=cursor, more=more)
      except db.BadRequestError:
        last, cursor, more = cls.get(num=num, order=cls.LAST_ORDERBY,
                                 page=True, cursor=None)
        cached_keys = []
        cached.set([(obj.key, obj._orderby) for obj in last],
                   cursor=cursor, more=more)

      cached.save()
    else:
      cached_keys = cached.results

    if not cached:
      return []

    if keys_only:
      if only_one:
        return cached.results[-1]

      return cached.results
    else:
      if only_one:
        return cls.get(cached.results[-1])

      rslt = (cls.get(cached_keys) + last)[:num]
      return rslt

  @classmethod
  def get_last_keys(cls, num=-1, before=None, after=None):
    return cls.get_last(num=num, before=before, after=after, keys_only=True)

  # Method to add a new element to the lastcache for this class
  @classmethod
  def add_to_last_cache(cls, obj):
    cached = SortedQueryCache.fetch(cls.LAST)
    cached.ordered_unique_insert(obj.key, obj._orderby)
    cached.save()

  # Utility method so that a last-cacheable entry knows how to
  # lastcache itself.
  def add_own_last_cache(self):
    self.add_to_last_cache(self)

class Play(LastCachedModel):
  _RAW = RawPlay
  _RAWKIND = "Play"

  '''A Play is an (entirely) immutable datastore object which represents
  a charted song
  '''
  LAST = "@last_plays" # Tuple of last_plays_list, db_count
  LAST_ORDER = -1 # Sort from most recent backwards
  LAST_ORDERBY = (_RAW.play_date,) # How plays should be ordered in last cache
  SHOW_LAST = "last_plays_show%s" #possibly keep with show instead

  TOP_SONGS = "@top_songs_before%s_after%s"
  TOP_ALBUMS = "@top_albums_before%s_after%s"

  @property
  def _orderby(self):
    return self.play_date

  @property
  def program_key(self):
    return self.raw.program
  @property
  def song_key(self):
    return self.raw.song

  ## Properties
  @property
  def song(self):
    return Song.get(self.song_key)
  @property
  def program(self):
    return Program.get(self.program_key)
  @property
  def play_date(self):
    return self.raw.play_date
  @property
  def is_new(self):
    return self.raw.isNew
  @property
  def artist(self):
    return self.raw.artist

  def to_json(self):
    return {
      'key': str_or_none(self.key),
      'song_key': str_or_none(self.song_key),
      'program_key': str_or_none(self.program_key),
      'play_date': time.mktime(self.play_date.utctimetuple()) * 1000
    }

  def __init__(self, raw=None, song=None, program=None, artist=None,
               is_new=None, play_date=None,
               parent=None,
               is_fresh=False, **kwds):
    if raw is not None:
      super(Play, self).__init__(raw=raw)
    else:
      if parent is None:
        parent = program

      if play_date is None:
        play_date = datetime.datetime.now()

      super(Play, self).__init__(parent=parent,
                                 song=as_key(song),
                                 program=as_key(program),
                                 artist=artist,
                                 play_date=play_date,
                                 isNew=is_new, **kwds)

    self.is_fresh = is_fresh

  @classmethod
  def new(cls, song, program, artist, is_fresh=True, **kwds):
    return cls(song=song, program=program, artist=artist,
               is_fresh=is_fresh)

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
  def get(cls, keys=None, before=None, after=None, is_new=None,
          program=None, order=None, artist=None,
          num=-1, page=False, cursor=None, one_key=False):
    if keys is not None:
      return super(Play, cls).get(keys=keys,
                                  one_key=one_key)

    keys = cls.get_key(before=before, after=after,
                       is_new=is_new, order=order, num=num,
                       artist=artist,
                       program=program, page=page, cursor=cursor)
    if page:
      keys, cursor, more = keys

    if keys is not None:
      if page:
        return (cls.get(keys=keys),
                cursor, more)
      else:
        return cls.get(keys=keys)
    return None

  @classmethod
  def get_key(cls, before=None, after=None, program=None, is_new=None,
             artist=None, order=None, num=-1, page=False, cursor=None):
    if program is not None:
      query = cls._RAW.query(ancestor=program)
    else:
      query = cls._RAW.query()

    if artist is not None:
      query = query.filter(RawPlay.artist == artist)
    if is_new is not None:
      query = query.filter(RawPlay.isNew == is_new)
    if after is not None:
      query = query.filter(RawPlay.play_date >=
                           datetime.datetime.combine(after, datetime.time()))
    if before is not None:
      query = query.filter(RawPlay.play_date <=
                           datetime.datetime.combine(before, datetime.time()))
    if order is not None:
      query = query.order(*order)

    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  def put(self):
    key = super(Play, self).put()

    if key and self.is_fresh and self.program:
      program = self.program
      program.update_top_artists(self.artist)
      program.put()

    return key

  @classmethod
  def delete_key(cls, key, program=None):
    if program is not None:
      pass # Inform parent program that we're deleting this play'

    super(Play, cls).delete_key(key=key)

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
    program = Program.as_object(program)
    if program is not None:
      return program.get_last_plays(num=num)
    return None if num == -1 else []

  @classmethod
  def get_last_keys(cls, num=-1, program=None, before=None, after=None):
    return cls.get_last(num=num, keys_only=True,
                        program=program, before=before, after=after)

  ## Custom queries pertaining to plays

  # Get top songs and albums
  # returns a tuple(songs, albums)
  @classmethod
  def get_top(cls, after=None, before=None,
              song_num=10, album_num=10, keys_only=False):
    # Sanitize our range dates. Dates instead of times make caching
    # more convenient, and I don't even think we can ask for times
    # anyway
    if before is None:
      before = datetime.date.today() + datetime.timedelta(days=1)
    else:
      if isinstance(before, datetime.datetime):
        before = before.date()
      before += datetime.timedelta(days=1)
      if after is None:
        after = datetime.date.today() - datetime.timedelta(days=6)
      elif isinstance(after, datetime.datetime):
          after = after.date()

    cached_songs = cls.get_cached_query(cls.TOP_SONGS, before, after)
    cached_albums = cls.get_cached_query(cls.TOP_ALBUMS, before, after)

    # If our caches exist and are sufficient
    if not (cached_songs is None or
            cached_songs.need_fetch(song_num) or
            cached_albums is None or
            cached_albums.need_fetch(album_num)):
      songs = cached_songs.results
      albums = cached_albums.results

    else:
      new_plays = cls.get(before=before, after=after, is_new=True, num=1000)
      songs = {}
      albums = {}

      for play in new_plays:
        song_key = play.song_key
        if song_key in songs:
          songs[song_key] += 1
        else:
          songs[song_key] = 1
        if play.song_key is not None and play.song.album_key is not None:
          album_key = play.song.album_key
          if album_key in albums:
            albums[album_key] += 1
          else:
            albums[album_key] = 1

      songs = songs.items()
      albums = albums.items()

    if not keys_only:
      songs = [(Song.get(song), count) for song,count in songs]
    if not keys_only:
      albums = [(Album.get(album), count) for album,count in albums]

    songs = sorted(songs, key=(lambda x: x[1]), reverse=True)[:song_num]
    albums = sorted(albums, key=(lambda x: x[1]), reverse=True)[:album_num]

    cached_songs

    return (songs, albums)


class Psa(LastCachedModel):
  _RAW = RawPsa
  _RAWKIND = "Psa"

  LAST = "@@last_psas" # Tuple of last_plays_list, db_count
  LAST_ORDER = -1 # Sort from most recent backwards
  LAST_ORDERBY =  -_RAW.play_date # How plays should be ordered in last cache
  SHOW_LAST = "last_psas_show%s" #possibly keep with show instead
  ENTRY = "psa_key%s"

  @classmethod
  def new(cls, desc, program, play_date=None,
          parent=None, key_name=None, **kwds):
    if parent is None:
      parent = program

    if play_date is None:
      play_date = datetime.datetime.now()

    psa = cls(parent=parent, key_name=key_name,
               desc=desc, program=program, play_date=play_date, **kwds)

    psa.is_fresh = True

    return psa

  def add_to_cache(self):
    super(Psa, self).add_to_cache()
    try:
      if self.is_fresh:
        self.add_own_last_cache()
    except AttributeError:
      pass
    return self

  @classmethod
  def get(cls, keys=None, before=None, after=None, order=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Psa, cls).get(keys=keys,
                                 use_datastore=use_datastore,
                                 one_key=one_key)

    keys = cls.get_key(before=before, after=after,
                       order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, before=None, after=None,
             order=None, num=-1):
    query = Psa.all(keys_only=True)

    if after is not None:
      query = query.filter("play_date >=", after)
    if before is not None:
      query = query.filter("play_date <=", before)
    if order is not None:
      query.order(*order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self):
    super(Psa, self).put()

  @classmethod
  def delete_key(cls, key, program=None):
    if program is not None:
      pass # Inform parent program that we're deleting this play'

    super(Psa, cls).delete_key(key=key)

  # We override the get_last method to use, e.g., the parent program
  # in our queries
  @classmethod
  def get_last(cls, num=-1, keys_only=False,
               program=None, before=None, after=None):
    # We may want to get the last psas of a specific program
    # Otherwise, use the already defined super method.
    if program is None:
      return super(Psa, cls).get_last(num=num, keys_only=keys_only,
                                       before=before, after=after)

    # TODO: Pass other parameters to program's method
    if program is not None:
      program = Program.as_object(program)
      return program.get_last_psas(num=num)
    return None if num == -1 else []

  @classmethod
  def get_last_keys(cls, num=-1, program=None, before=None, after=None):
    return cls.get_last(num=num, keys_only=True,
                        program=program, before=before, after=after)

class StationID(object):
  pass