#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Album model, and auxiliary functions.
#  An Album object corresponds to a row in the Album table in the datastore

from __future__ import with_statement

# GAE Imports
from google.appengine.ext import ndb

# Local module imports
from base_models import *

from _raw_models import Album as RawAlbum
from _raw_models import Song as RawSong
from _raw_models import ArtistName as RawArtistName

from _raw_models import search_namify

# Global python imports
import logging
import itertools

class Album(CachedModel):
  _RAW = RawAlbum
  _RAWKIND = "Album"

  NEW = "new_albums" # Keep the newest albums cached.
  MIN_NEW = 50 # We want to keep so many new albums in cache, since it's the
               # most typically ever encountered in normal website usage.
  MAX_NEW = 75 # There should be no reason to have more than this many
               # cached new albums, and beyond this is wasteful.

  @property
  def cover_small_key(self):
    return self.raw.cover_small

  @property
  def cover_large_key(self):
    return self.raw.cover_large

  def to_json(self):
    return {
      'key': str(self.key),
      'title': self.title,
      'artist': self.artist,
      #'add_date': self.add_date,
      'song_list': [str_or_none(song) for song in self.tracklist],
      'cover_small_key': str_or_none(self.cover_small_key),
      'cover_large_key': str_or_none(self.cover_large_key),
    }

  def __init__(self, raw=None, raw_key=None, title=None,
               artist=None, tracks=None,
               add_date=None, asin=None,
               cover_small=None, cover_large= None, is_new=True,
               key=None, **kwds):
    if raw is not None:
      super(Album, self).__init__(raw=raw)
      return
    elif raw_key is not None:
      super(Album, self).__init__(raw_key=raw_key)
      return

    if tracks is None: tracks = []
    if not title:
      raise Exception("Cannot have an Album without a title")
    if add_date is None:
      add_date = datetime.datetime.now()
    if key is None:
      batch = RawAlbum.allocate_ids(1)
      key = ndb.Key(RawAlbum, batch[0])

    # Instantiate the tracks, put them (Model.put() returns keys)
    if tracks:
      tracks = self._put_tracks(tracks, artist, key)

    super(Album, self).__init__(key=key, title=title,
                                artist=artist,
                                add_date=add_date,
                                isNew=is_new,
                                songList=tracks,
                                cover_small=cover_small,
                                cover_large=cover_large,
                                asin=asin,
                                **kwds)

  # Right now, creating an album creates a bunch of new Songs on the spot
  # so you're probably going to want to put the album right after you make it
  # If you don't, you're a bad person and you hate good things
  # TODO: Make some transactional shortcut to all that mess
  @classmethod
  def new(cls, title, artist, tracks,
          add_date=None, asin=None,
          cover_small=None, cover_large=None, is_new=True,
          key=None, **kwds):
    return cls(title=title, artist=artist, tracks=tracks,
               add_date=add_date, asin=asin, cover_small=cover_small,
               cover_large=cover_large,
               is_new=is_new, key=key, **kwds)

  @staticmethod
  @ndb.transactional
  def _put_tracks(tracks, artist, album_key):
    tracks = [Song(title=trackname,
                   artist=artist,
                   album=album_key,).put() for trackname in tracks]
    return tracks


  # TODO: make this a classmethod/instancemethod hybrid??? I wish I knew what
  # to friggin' Google.
  # TODO: generalize this interface (caches some "new" elements)
  @classmethod
  def add_to_new_cache(cls, key, add_date=None):
    if add_date is None:
      add_date = datetime.datetime.now()

    cached = SetQueryCache.fetch(cls.NEW)
    cached.append(key)
    cached.save()

  @classmethod
  def purge_from_new_cache(cls, key):
    cached = SetQueryCache.fetch(cls.NEW)
    cached.discard(key)
    cached.save()

  def add_to_cache(self):
    super(Album, self).add_to_cache()
    if self.is_new:
      self.add_to_new_cache(self.key, add_date=self.add_date)
    return self

  def purge_from_cache(self):
    super(Album, self).purge_from_cache()
    self.purge_from_new_cache(self.key)
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          artist=None,
          asin=None,
          order=None,
          num=-1,
          is_new=None,
          use_datastore=True, one_key=False):
    if keys is not None:
      return super(Album, cls).get(keys, use_datastore=use_datastore,
                                        one_key=one_key)

    keys = cls.get_key(title=title, is_new=is_new,
                       artist=artist, asin=asin,
                       order=order, num=num)

    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, title=None, artist=None, is_new=None,
              asin=None, order=None, num=-1, page=False,
              cursor=None):
    query = RawAlbum.query()

    if title is not None:
      query = query.filter(RawAlbum.title == title)
    if artist is not None:
      query = query.filter(RawAlbum.artist == artist)
    if is_new is not None:
      query = query.filter(RawAlbum.isNew == is_new)
    if asin is not None:
      query = query.filter(RawAlbum.asin == asin)

    # Usual album orders: 'add_date'
    if order is not None:
      query = query.order(*order)

    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)


  def put(self):
    # If we've toggled the newness of the album, update cache.
    try:
      logging.debug(self._was_new)
      if self._was_new != self.is_new:
        logging.debug("We're about to update newcache")
        new_albums = self.get_new_keys()
        if self.is_new:
          if not new_albums:
            new_albums = [self.key,]
          else:
            new_albums.append(self.key)
        else:
          new_albums.remove(self.key)

        self.cache_set(new_albums, self.NEW)
    except AttributeError:
      pass

    return super(Album, self).put()

  # Albums are immutable Datastore entries, except for is_new status.
  @property
  def title(self):
    return self.raw.title
  @property
  def artist(self):
    return self.raw.artist
  @property
  def tracklist(self):
    return self.raw.songList
  @property
  def add_date(self):
    return self.raw.add_date
  @property
  def is_new(self):
    return self.raw.isNew

  def set_new(self):
    self._was_new = self.is_new
    self.raw.isNew = True
  def unset_new(self):
    self._was_new = self.is_new
    self.raw.isNew = False

  @classmethod
  def get_new(cls, num=36, keys_only=False, sort=None):
    if num < 1:
      return None

    cached = SetQueryCache.fetch(cls.NEW)
    if not cached or cached.need_fetch(num):
      num_to_fetch = num - len(cached)
      keys, cursor, more = cls.get_key(is_new=True,
                                       order=(-RawAlbum.add_date,), num=num,
                                       page=True, cursor=cached.cursor)
      cached.extend(keys)
      cached.cursor = cursor
      cached.more = more
      cached.save()

    if not cached:
      return []

    if keys_only:
      return list(cached.results)[:num]
    else:
      if sort == "artist":
        return sorted(cls.get(list(cached.results)[:num]),
                      key=lambda album: album.artist.lower())
      else:
        return sorted(cls.get(list(cached.results)[:num]),
                      key=lambda album: album.add_date)


  @classmethod
  def get_new_keys(cls, num=36, sort=None):
    return cls.get_new(num, keys_only=True)

class Song(CachedModel):
  _RAW = RawSong
  _RAWKIND = "Song"
  '''A Song is an (entirely) immutable datastore object which represents
  a song; e.g. one played in the past or an element in a list of tracks.
  '''

  @property
  def album_key(self):
    return self.raw.album

  def to_json(self):
    return {
      'key': str_or_none(self.key),
      'title': self.title,
      'artist': self.artist,
      'album_key': str_or_none(self.album_key),
      }

  def __init__(self, raw=None, raw_key=None,
               title=None, artist=None, album=None,
               parent=None, **kwds):
    if raw is not None:
      super(Song, self).__init__(raw=raw)
      return
    elif raw_key is not None:
      super(Song, self).__init__(raw_key=raw_key)
      return

    if parent is None:
      parent = album

    super(Song, self).__init__(parent=parent,
                               title=title, artist=artist, album=album,
                               **kwds)
    if album is not None:
      self.raw.album = album

  @classmethod
  def new(cls, title, artist, album=None,
               parent=None, **kwds):
    return Song(title=title, artist=artist, album=album,
                parent=parent,  **kwds)

  def add_to_cache(self):
    super(Song, self).add_to_cache()
    return self

  def purge_from_cache(self):
    super(Song, self).purge_from_cache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None, order=None,
          num=-1, one_key=False):
    if keys is not None:
      return super(Song, cls).get(keys, one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys)
    return None

  @classmethod
  def get_key(cls, title=None, order=None, num=-1):
    query = cls._RAW.query()

    if order is not None:
      query = query.order(order)

    if num == -1:
      return query.get(keys_only=True)
    return query.fetch(num, keys_only=True)

  def put(self):
    return super(Song, self).put()

  @property
  def title(self):
    return self.raw.title
  @property
  def artist(self):
    return self.raw.artist
  @property
  def album(self):
    return Album.get(self.album_key)

class ArtistName(CachedModel):
  _RAW = RawArtistName
  _RAWKIND = "ArtistName"

  ## Functions for getting and setting Artists,
  ## Specifically, caching artist name autocompletion
  COMPLETE = "@artist_pref%s"

  # Minimum number of entries in the cache with which we would even consider
  # not rechecking the datastore. Figit with this number to balance reads and
  # autocomplete functionality. Possibly consider algorithmically determining
  # a score for artist names and prefixes?
  AC_FETCH_NUM = 10
  MIN_AC_CACHE = 10
  MIN_AC_RESULTS = 5

  @property
  def _search_fields(self):
    return set(self.lower_name.split() + self.search_name.split())

  @classmethod
  def _search_queries(cls, prefix):
    yield (cls._autocomplete_query(cls._RAW.search_name, prefix), "search")
    yield (cls._autocomplete_query(cls._RAW.lower_name, prefix), "lower")

  def __init__(self, raw=None, raw_key=None,
               artist_name=None, **kwds):
    if raw is not None:
      super(ArtistName, self).__init__(raw=raw)
      return
    elif raw_key is not None:
      super(ArtistName, self).__init__(raw_key=raw_key)
      return
    else:
      super(ArtistName, self).__init__(artist_name=artist_name, **kwds)
      return

  @property
  def artist_name(self):
    return self.raw.artist_name
  @property
  def lower_name(self):
    return self.raw.lowercase_name
  @property
  def search_name(self):
    return self.raw.search_name

  @classmethod
  def new(cls, artist_name, **kwds):
    return cls(artist_name=artist_name, **kwds)

  @classmethod
  def try_put(cls, artist_name, **kwds):
    artist = cls.get(artist_name=artist_name)
    if artist:
      return artist

    artist = cls(
      artist_name=artist_name,
      **kwds)

    artist.put()
    return artist

  @classmethod
  def get(cls, keys=None, artist_name=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(ArtistName, cls).get(
        keys=keys,
        use_datastore=use_datastore,
        one_key=one_key)

    keys = cls.get_key(artist_name=artist_name, num=num)
    if keys is not None:
      return super(ArtistName, cls).get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, artist_name=None, num=-1):
    query = RawArtistName.query()
    if artist_name:
      query = query.filter(RawArtistName.lowercase_name == artist_name.lower())

    if num == -1:
      return query.get(keys_only=True)
    return query.fetch(num, keys_only=True)

  @staticmethod
  def get_search_name(artist_name):
    SEARCH_IGNORE_PREFIXES = (
      "the ",
      "a ",
      "an ",)

    name = artist_name.lower()

    for prefix in SEARCH_IGNORE_PREFIXES:
      if name.startswith(prefix):
        name = name[len(prefix):]

    return name

  def has_prefix(self, prefix):
    prefixes = prefix.split()

    if self.search_name is None:
      self.put() # Maybe updates computed properties??
      assert(self.search_name is not None)

    for name_part in self.search_name.split():
      check_prefixes = prefixes
      for prefix in check_prefixes:
        if name_part.startswith(prefix):
          prefixes.remove(prefix)
          if len(prefixes) == 0:
            return True
          break

    return False

  @staticmethod
  def name_has_prefix(name, prefix):
    prefixes = prefix.split()

    for name_part in search_namify(name).split():
      check_prefixes = prefixes
      for prefix in check_prefixes:
        if name_part.startswith(prefix):
          prefixes.remove(prefix)
          if len(prefixes) == 0:
            return True
            break

    return False

  # As it is now, autocomplete is a little wonky. One thing worth
  # noting is that we search cache a bit more effectively than the
  # datastore: for example, if you've got a cached prefix "b" and
  # bear in heaven was there, then you're able to just search "b i
  # h" and cut out other stragglers like "Best Band Ever". Right
  # now, we can't search datastore this efficiently, so this is kind
  # of hit or miss.
  @classmethod
  def autocomplete(cls, prefix):
    prefix = prefix.lower().strip()

    # Go into memory and grab all (some?) of the caches for this
    # prefix and earlier
    cache_list = [SetQueryCache.fetch(cls.COMPLETE %prefix[:i+1]) for
                  i in range(len(prefix))]

    best_data = set()
    for prelen, cached_query in enumerate(cache_list):
      if len(cached_query) > 0:
        best_data = cached_query.results
      else:
        best_data = set(
          filter(lambda an: ArtistName.name_has_prefix(an, prefix[:prelen+1]),
                 best_data))
        cached_query.set(best_data)
        cached_query.save()

    cached = cache_list.pop() # Get the cache for the relevant prefix
    if cached.need_fetch(cls.AC_FETCH_NUM):
      # We have to fetch some keys from the datastore
      if cached.cursor is None:
        cached.cursor = {'lower': None, 'search': None}

      # Prep the queries
      lower_query = RawArtistName.query().filter(
        ndb.AND(RawArtistName.lowercase_name >= prefix,
                RawArtistName.lowercase_name < (prefix + u"\ufffd")))
      search_query = RawArtistName.query().filter(
        ndb.AND(RawArtistName.search_name >= prefix,
                RawArtistName.search_name < (prefix + u"\ufffd")))

      try:
        # Try to continue an older query
        num = cls.AC_FETCH_NUM - len(cached)

        lower_raw_artists, lower_cursor, l_more = lower_query.fetch_page(
          num, start_cursor=cached.cursor['lower'],
          projection=[RawArtistName.artist_name])
        search_raw_artists, search_cursor, s_more = search_query.fetch_page(
          num, start_cursor=cached.cursor['search'],
          projection=[RawArtistName.artist_name])

        cache_results = cached.results

      except db.BadRequestError:
        # Unable to continue the older query. Run a new one.
        lower_raw_artists, lower_cursor, l_more = lower_query.fetch_page(
          num,
          projection=[RawArtistName.artist_name])
        search_raw_artists, search_cursor, s_more = search_query.fetch_page(
          num,
          projection=[RawArtistName.artist_name])

        cache_results = set()

      add_artists = (set(a.artist_name for a in search_raw_artists) |
                     set(a.artist_name for a in lower_raw_artists))
      artist_names = cached.results | add_artists

      # We've got a bunch of artistnames for this prefix, so let's
      # update all of our cached queries: this one, and all supqueries
      cached.extend_by(add_artists,
                       {'lower': lower_cursor, 'search': search_cursor},
                       l_more or s_more)
      cached.save()

      for cached_query in reversed(cache_list):
        cached_query.extend(add_artists)
        cached_query.save()
    else:
      # We don't have to fetch anything!
      artist_names = cached.results

    return sorted(artist_names, key=lambda x: search_namify(x))