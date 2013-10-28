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

from cache_models import *

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

from operator import itemgetter
from itertools import izip

def last_week_span(date=None):
  if date is None:
    date = datetime.date.today()
  elif isinstance(date,datetime.datetime):
    date = date.date()

  before = date + datetime.timedelta(days=1)
  after = date - datetime.timedelta(days=6)
  return before, after

## Exceptions for Programs, Plays, PSAs, StationIDs
class NoSuchProgramSlug(ModelError):
  pass

@accepts_raw
class Program(Searchable, NewCacheable):
  _RAW = RawProgram

  ## Functions for getting and setting Programs
  EXPIRE = 360  # Program cache lasts for one hour maximum

  BY_DJ_ENTRY = "@@programs_by_dj%s"
  SLUG = "@program_slug%s"
  NEW = "@newest_programs"
  COMPLETE = "@@@program_prefix%s"

  AC_FETCH_NUM = 10
  MIN_AC_CACHE = 10
  MIN_AC_RESULTS = 5

  @property
  def _autocomplete_fields(self):
    return set(self.title.lower().strip().split() + self.slug.split("-"))

  @classmethod
  def _autocomplete_queries(cls, prefix):
    yield (cls._autocomplete_query(cls._RAW.lower_title, prefix), "title")
    yield (cls._autocomplete_query(cls._RAW.slug, prefix), "slug")

  def __init__(self, title="", slug="", desc="",
               dj_list=None, page_html="", current=True,
               **kwargs):
    if dj_list is None: dj_list = []

    super(Program, self).__init__(title=title,
                                  slug=slugify(slug if slug else title),
                                  desc=desc,
                                  dj_list=[as_key(dj) for dj in dj_list if dj],
                                  page_html=page_html,
                                  current=bool(current), **kwargs)

  @classmethod
  def new(cls, title, slug, desc, dj_list, page_html, current=True):
    if not title:
      raise ModelError("Insufficient data to create show")

    return cls(title=title, slug=slug, desc=desc, dj_list=dj_list,
               page_html=page_html, current=current, _new=True)

  def put(self):
    return super(Program, self).put()

  @quantummethod
  def add_slug_cache(obj, key=None, slug=None):
    key = obj.key if key is None else key
    slug = obj.slug if slug is None else slug
    return obj.cache_set(key, obj.SLUG, slug)

  @quantummethod
  def purge_slug_cache(obj, key=None, slug=None):
    key = obj.key if key is None else key
    slug = obj.slug if slug is None else slug

    cache = obj.cache_get(obj.SLUG, slug)
    if cache and cache == key:
      obj.cache_delete(obj.SLUG, slug)

  @quantummethod
  def add_dj_cache(obj, key=None, dj_list=None):
    key = obj.key if key is None else key
    dj_list = obj.dj_list if dj_list is None else dj_list

    if key is None or dj_list is None:
      return

    caches = [SetQueryCache.fetch(obj.BY_DJ_ENTRY % dj_key) for
                  dj_key in dj_list]
    logging.info(caches)
    logging.info(dj_list)
    for dj_cache in caches:
      dj_cache.append(key)
      dj_cache.save()

  @quantummethod
  def purge_dj_cache(obj, key=None, dj_list=None):
    key = obj.key if key is None else key
    dj_list = obj.dj_list if dj_list is None else dj_list

    if key is None or dj_list is None:
      return

    caches = [SetQueryCache.fetch(obj.BY_DJ_ENTRY % dj_key) for
              dj_key in dj_list]
    logging.info(caches)
    logging.info(dj_list)
    for dj_cache in caches:
      dj_cache.discard(key)
      dj_cache.save() 

  def add_to_cache(self):
    super(Program, self).add_to_cache()
    self.add_slug_cache()
    self.add_dj_cache()
    self.add_to_new_cache()
    return self

  def purge_from_cache(self):
    super(Program, self).purge_from_cache()
    self.purge_slug_cache()
    self.purge_dj_cache()
    self.purge_from_new_cache(self.key)
    return self

  @classmethod
  def get(cls, keys=None, use_datastore=True, one_key=False,
          page=False, cursor=None, **kwargs):
    # We're getting the program by key
    if keys is not None:
      return super(Program, cls).get(keys,
                                     use_datastore=use_datastore,
                                     one_key=one_key)

    return cls._get_helper(page=page, cursor=cursor, **kwargs)

  @classmethod
  def get_key(cls, slug=None, dj=None, order=None, num=-1,
              page=False, cursor=None):
    query = cls._RAW.query()

    if slug is not None:
      query = query.filter(RawProgram.slug == slug)
    if dj is not None:
      query = query.filter(RawProgram.dj_list == as_key(dj))

    if order is not None:
      query = query.order(order)

    # Consider adding query caching here, if necessary
    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  def get_last_plays(self, num=-1, keys_only=False,
                     before=None, after=None, force_cached=False):
    return Play.get_last(num=num, program=self, keys_only=keys_only,
                         before=before, after=after, force_cached=force_cached)

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

    cached = SetQueryCache.fetch(cls.BY_DJ_ENTRY % dj)

    if cached.need_fetch(num):
      cached.set(cls.get_key(dj=dj, num=num))
      cached.save()

    if not cached:
      return []

    if keys_only:
      if only_one:
        return list(cached.results)[-1]
      return list(cached.results)[:num]
    else:
      if only_one:
        return cls.get(list(cached.results)[-1])
      return cls.get(list(cached.results)[:num])

  @classmethod
  def get_by_slug(cls, slug, keys_only=False):
    cached = cls.get_by_index(cls.SLUG, slug, keys_only=keys_only)
    if cached is not None:
      return cached

    slug = slug.strip()
    key = cls.get_key(slug=slug)
    if key is not None:
      if keys_only:
        return cls.add_slug_cache(key, slug)
      program = cls.get(key)
      if program is not None:
        program.add_slug_cache()
        return program
    raise NoSuchProgramSlug()

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

  def __contains__(self, item):
    dj_key = as_key(item)
    if dj_key is not None:
      return dj_key in self.dj_list
    return False

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
    logging.debug(playcounts)
    if artist in playcounts:
      playcounts[artist] = playcounts[artist] + 1
    else:
      playcounts[artist] = self.get_artist_play_count(artist)

    logging.debug(playcounts)
    playcounts = list(playcounts.iteritems())
    logging.debug(playcounts)
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

@accepts_raw
class LastCachedModel(CachedModel):
  '''A model for which there is a global cache of "Last instances",
  e.g. a cache of all recently charted songs (see the Play class)'''

  LAST = None #Important that children overwrite this to avoid clashes
  LAST_ORDER = 1 #One of 1, -1
  LAST_ORDERBY = None #Get last X based on this ordering

  def __init__(self, **kwargs):
    super(LastCachedModel, self).__init__(**kwargs)

  @classmethod
  def get_last(cls, num=-1, keys_only=False,
               before=None, after=None, force_cached=False,
               cachekey=None, getargs=None):
    if not getargs: getargs = {}
    if not cachekey: cachekey = cls.LAST
    if num != -1 and num < 1:
      return None

    only_one = False
    if num == -1:
      only_one = True
      num = 1

    ## I really just want this to make datetimes into dates too
    if before is None and after is None:
      pass
      #before, after = last_week_span()
    elif before is None:
      before = last_week_span(after + datetime.timedelta(6))[0]
    elif after is None:
      after = last_week_span(before)[1]

    cached = SortedQueryCache.fetch(cachekey % (before, after))
    logging.info("Grabbed Lastcache %s"%cachekey % (before, after))

    logging.debug((before, after))

    last = []
    cached_keys = []
    if cached.need_fetch(num) and not force_cached:
      try:
        num_to_fetch = num - len(cached)
        last, cursor, more = cls.get(num=num_to_fetch,
                                     order=cls.LAST_ORDERBY,
                                     before=before, after=after,
                                     page=True, cursor=cached.cursor,
                                     **getargs)
        cached_keys = tuple(cached.results)
        cached.extend_by([(obj.key, obj._orderby) for obj in last],
                         cursor=cursor, more=more)
      except db.BadRequestError:
        last, cursor, more = cls.get(num=num, order=cls.LAST_ORDERBY,
                                     before=before, after=after,
                                     page=True, cursor=None, **getargs)
        cached_keys = []
        cached.set([(obj.key, obj._orderby) for obj in last],
                   cursor=cursor, more=more)

      cached.save()
    else:
      cached_keys = tuple(cached.results)

    if not cached:
      return None if only_one else []

    if keys_only:
      if only_one:
        return cached.results[0]

      return cached.results
    else:
      if only_one:
        return cls.get(cached.results[0])

      rslt = (cls.get(cached_keys) + last)[:num]
      return rslt

  @classmethod
  def get_last_keys(cls, num=-1, before=None, after=None, force_cached=False):
    return cls.get_last(num=num, before=before, after=after, keys_only=True,
                        force_cached=force_cached)

  # Method to add a new element to the lastcache for this class
  @classmethod
  def add_to_last_cache(cls, obj, cachekey=None, 
                        before=None, after=None):
    if not cachekey: cachekey=cls.LAST
    cached = SortedQueryCache.fetch(cachekey%(before, after))
    logging.info("Cached Lastcache; %s"%cachekey%(before, after))
    try:
      f = obj._last_cmp
    except AttributeError:
      f = None
    cached.ordered_unique_insert(obj.key, obj._orderby, f=f)
    cached.save()

  @classmethod
  def purge_from_last_cache(cls, key, cachekey=None,
                            before=None, after=None):
    if not cachekey: cachekey=cls.LAST
    cached = SortedQueryCache.fetch(cachekey%(before, after))
    try:
      cached.remove(key)
      cached.save()
    except:
      pass

  # Utility method so that a last-cacheable entry knows how to
  # lastcache itself.
  def add_own_last_cache(self):
    self.add_to_last_cache(self)

@accepts_raw
class Play(LastCachedModel):
  _RAW = RawPlay
  _RAWKIND = "Play"

  '''A Play is an (entirely) immutable datastore object which represents
  a charted song
  '''
  LAST = "@last_plays_before%s_after%s" # Tuple of last_plays_list, db_count
  LAST_ORDER = -1 # Sort from most recent backwards
  LAST_ORDERBY = (-_RAW.play_date,) # How plays should be ordered in last cache
  LAST_BY_PROGRAM = "last_plays_before%s_after%s_show%s"
  #possibly keep with show instead

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
  def album(self):
    if self.song_key:
      song = self.song
      if song:
        return song.album
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

  def __init__(self, song=None, program=None, artist=None,
               is_new=None, play_date=None,
               parent=None,
               is_fresh=False, **kwargs):
    if parent is None:
      parent = program

    if play_date is None:
      play_date = datetime.datetime.now()

    super(Play, self).__init__(parent=parent,
                               song=as_key(song),
                               program=as_key(program),
                               artist=artist,
                               play_date=play_date,
                               isNew=is_new, **kwargs)

    self.is_fresh = is_fresh

  @classmethod
  def new(cls, song, program, artist, is_new=False, is_fresh=True, **kwargs):
    return cls(song=song, program=program, artist=artist,
               is_new=is_new, is_fresh=is_fresh)

  def add_to_cache(self):
    super(Play, self).add_to_cache()
    try:
      if self.is_fresh:
        self.add_own_last_cache()
        self.add_own_top_cache()
    except AttributeError:
      pass
    return self

  # Method to add a new element to the lastcache for this class
  @classmethod
  def add_to_top_cache(cls, obj):
    if not self.is_new:
      return

    # We can only cache so much, so only add this guy to today's last
    # week of top plays.
    # MAYBETODO: Use a big table with aaall songs/albums instead?
    before, after = last_week_span()
    if not (self.play_date < before and self.play_date >= after):
      return

    if obj.song_key is not None:
      song_cache = CountTableCache.fetch(cls.TOP_SONGS%(before, after))
      if len(song_cache.results) > 0:
        song_cache.increment(obj.song_key)
        song_cache.save()

      song = obj.song
      if song.album_key is not None:
        album_cache = CountTableCache.fetch(cls.TOP_ALBUMS%(before, after))
        if len(album_cach.results) > 0:
          album_cache.increment(song.album_key)
          album_cache.save()

  # Utility method so that a last-cacheable entry knows how to
  # lastcache itself.
  def add_own_last_cache(self):
    self.add_to_last_cache(self)
    self.add_to_last_cache(self, cachekey=self.LAST_BY_PROGRAM%
                           ("%s", "%s", self.program_key))

  def purge_from_cache(self):
    super(Play, self).purge_from_cache()
    self.purge_from_last_cache(self.key)
    self.purge_from_last_cache(self.key, cachekey=self.LAST_BY_PROGRAM%
                           ("%s", "%s", self.program_key))
    return self

  @classmethod
  def get(cls, keys=None, page=False, cursor=None, one_key=False,
          **kwargs):
    if keys is not None:
      return super(Play, cls).get(keys=keys,
                                  one_key=one_key)

    return cls._get_helper(page=page, cursor=cursor, **kwargs)

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

    self.is_fresh = False
    return key

  @classmethod
  def delete_key(cls, key, program=None):
    cls.purge_from_last_cache(key)
    cls.purge_from_last_cache(key, cachekey=cls.LAST_BY_PROGRAM%
                              ("%s", "%s", program))
    super(Play, cls).delete_key(key=key)

  # We override the get_last method to use, e.g., the parent program
  # in our queries
  @classmethod
  def get_last(cls, num=-1, keys_only=False,
               program=None, before=None, after=None,
               force_cached=False):
    # We may want to get the last plays of a specific program
    # Otherwise, use the already defined super method.
    if program is None:
      return super(Play, cls).get_last(num=num, keys_only=keys_only,
                                       before=before, after=after,
                                       force_cached=force_cached)

    # TODO: Pass other parameters to program's method
    program = as_key(program)
    if program is not None:
      return super(Play, cls).get_last(
        num=num, keys_only=keys_only,
        before=before, after=after,
        force_cached=force_cached,
        cachekey=cls.LAST_BY_PROGRAM%("%s","%s",program),
        getargs={"program": program})

    return None if num == -1 else []

  @classmethod
  def get_last_keys(cls, num=-1, program=None, before=None, after=None,
                    force_cached=None):
    return cls.get_last(num=num, keys_only=True,
                        program=program, before=before, after=after,
                        force_cached=force_cached)

  ## Custom queries pertaining to plays

  # Get top songs and albums
  # returns a tuple(songs, albums)
  @classmethod
  def get_top(cls, after=None, before=None,
              song_num=10, album_num=10, keys_only=False):
    # Sanitize our range dates. Dates instead of times make caching
    # more convenient, and I don't even think we can ask for times
    # anyway
    if before is None and after is None:
      before, after = last_week_span()
    elif before is None:
      before = last_week_span(after + datetime.timedelta(6))[0]
    elif after is None:
      after = last_week_span(before)[1]

    cached_songs = CountTableCache.fetch(cls.TOP_SONGS%(before, after))
    cached_albums = CountTableCache.fetch(cls.TOP_ALBUMS%(before, after))
    cached = False

    # If our caches exist and are sufficient
    if not (True or cached_songs.need_fetch(song_num) or
            cached_albums.need_fetch(album_num)):
      song_counts = cached_songs.results
      album_counts = cached_albums.results
      cached = True

    else:
      new_plays, cursor, more = cls.get(
        before=before, after=after, is_new=True, num=1000, page=True)
      song_counts = {}
      album_counts = {}

      for play in new_plays:
        song_key = play.song_key
        if song_key in song_counts:
          song_counts[song_key] += 1
        else:
          song_counts[song_key] = 1
        if play.song_key is not None and play.song.album_key is not None:
          album_key = play.song.album_key
          if album_key in album_counts:
            album_counts[album_key] += 1
          else:
            album_counts[album_key] = 1

    logging.debug(song_counts)

    if not keys_only:
      if song_counts:
        songs = zip(Song.get(song_counts.keys()), song_counts.values())
      else:
        songs = []

      if album_counts:
        albums = zip(Album.get(album_counts.keys()), album_counts.values())
      else:
        albums = []

    else:
      songs = song_counts.iteritems()
      albums = album_counts.iteritems()

    if not cached:
      cached_songs.set(song_counts, more)
      cached_albums.set(album_counts, more)
      cached_songs.save()
      cached_albums.save()

    songs = sorted(songs,
                   key=itemgetter(1), reverse=True)[:song_num]
    albums = sorted(albums,
                    key=itemgetter(1), reverse=True)[:album_num]

    return (songs, albums)

@accepts_raw
class Psa(LastCachedModel):
  _RAW = RawPsa
  _RAWKIND = "Psa"

  LAST = "@@last_psas_before%s_after%s" # Tuple of last_plays_list, db_count
  LAST_ORDER = -1 # Sort from most recent backwards
  LAST_ORDERBY =  (-_RAW.play_date,) # How psas should be ordered in last cache
  SHOW_LAST = "last_psas_show%s" #possibly keep with show instead

  @property
  def _orderby(self):
    return self.play_date

  @property
  def program_key(self):
    return self.raw.program

  @property
  def program(self):
    return Program.get(self.program_key)
  @property
  def play_date(self):
    return self.raw.play_date
  @property
  def desc(self):
    return self.raw.desc

  def __init__(self,
               program=None, play_date=None,
               desc=None, parent=None, **kwargs):
    if parent is None:
      parent = program

    if play_date is None:
      play_date = datetime.datetime.now()

    super(Psa, self).__init__(desc=desc, parent=parent, program=program,
                              play_date=play_date, **kwargs)

  @classmethod
  def new(cls, desc, program, play_date=None):
    psa = cls(desc=desc, program=program, play_date=play_date)
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
          num=-1, use_datastore=True, one_key=False, page=False,
          cursor=None):
    if keys is not None:
      return super(Psa, cls).get(keys=keys,
                                 use_datastore=use_datastore,
                                 one_key=one_key)

    if page:
      keys, cursor, more = cls.get_key(before=before, after=after,
                                       order=order, num=num,
                                       page=True, cursor=cursor)
    else:
      keys = cls.get_key(before=before, after=after,
                         order=order, num=num, cursor=cursor)

    if keys is not None:
      objs = cls.get(keys=keys, use_datastore=use_datastore)
      if not page:
        return objs
      else:
        return objs, cursor, more

    return None if not page else None, cursor, more

  @classmethod
  def get_key(cls, before=None, after=None,
             order=None, num=-1, page=False, cursor=None):
    query = cls._RAW.query()

    if after is not None:
      query = query.filter(cls._RAW.play_date > after)
    if before is not None:
      query = query.filter(cls._RAW.play_date <= before)
    if order is not None:
      query = query.order(*order)

    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  @classmethod
  def delete_key(cls, key, program=None):
    if program is not None:
      pass # Inform parent program that we're deleting this psa'

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

@accepts_raw
class StationID(LastCachedModel):
  _RAW = RawStationID
  _RAWKIND = "StationID"

  LAST = "@@last_ids_before%s_after%s" # Tuple of last_plays_list, db_count
  LAST_ORDER = -1 # Sort from most recent backwards
  LAST_ORDERBY =  (-_RAW.play_date,) # How plays should be ordered in last cache
  SHOW_LAST = "last_ids_show%s" #possibly keep with show instead

  @property
  def _orderby(self):
    return self.play_date

  @property
  def program_key(self):
    return self.raw.program

  @property
  def program(self):
    return Program.get(self.program_key)
  @property
  def play_date(self):
    return self.raw.play_date

  def __init__(self, program=None, play_date=None,
               parent=None, **kwargs):
    if parent is None:
      parent = program

    if play_date is None:
      play_date = datetime.datetime.now()

    super(StationID, self).__init__(parent=parent, program=program,
                                    play_date=play_date, **kwargs)

  @classmethod
  def new(cls, program, play_date=None):
    sid = cls(program=program, play_date=play_date)
    sid.is_fresh = True
    return sid

  def add_to_cache(self):
    super(StationID, self).add_to_cache()
    try:
      if self.is_fresh:
        self.add_own_last_cache()
    except AttributeError:
      pass
    return self

  @classmethod
  def get(cls, keys=None, before=None, after=None, order=None,
          num=-1, use_datastore=True, one_key=False, page=False,
          cursor=None):
    if keys is not None:
      return super(StationID, cls).get(keys=keys,
                                 use_datastore=use_datastore,
                                 one_key=one_key)

    if page:
      keys, cursor, more = cls.get_key(before=before, after=after,
                         order=order, num=num,
                         page=True, cursor=cursor)
    else:
      keys = cls.get_key(before=before, after=after,
                         order=order, num=num, cursor=cursor)
    if keys is not None:
      objs = cls.get(keys=keys, use_datastore=use_datastore)
      if not page:
        return objs
      else:
        return objs, cursor, more

    return None if not page else None, cursor, more

  @classmethod
  def get_key(cls, before=None, after=None,
             order=None, num=-1, page=False, cursor=None):
    query = cls._RAW.query()

    if after is not None:
      query = query.filter(cls._RAW.play_date > after)
    if before is not None:
      query = query.filter(cls._RAW.play_date <= before)
    if order is not None:
      query = query.order(*order)

    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  @classmethod
  def delete_key(cls, key, program=None):
    if program is not None:
      pass # Inform parent program that we're deleting this sid'

    super(StationID, cls).delete_key(key=key)

  # We override the get_last method to use, e.g., the parent program
  # in our queries
  @classmethod
  def get_last(cls, num=-1, keys_only=False,
               program=None, before=None, after=None):
    # We may want to get the last psas of a specific program
    # Otherwise, use the already defined super method.
    if program is None:
      return super(StationID, cls).get_last(num=num, keys_only=keys_only,
                                       before=before, after=after)

    # TODO: Pass other parameters to program's method
    if program is not None:
      program = Program.as_object(program)
      return program.get_last_ids(num=num)
    return None if num == -1 else []

  @classmethod
  def get_last_keys(cls, num=-1, program=None, before=None, after=None):
    return cls.get_last(num=num, keys_only=True,
                        program=program, before=before, after=after)