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

# Global python imports
import logging
import itertools

class Album(CachedModel):
  _RAW = RawAlbum

  NEW = "new_albums" # Keep the newest albums cached.
  MIN_NEW = 50 # We want to keep so many new albums in cache, since it's the
               # most typically ever encountered in normal website usage.
  MAX_NEW = 75 # There should be no reason to have more than this many
               # cached new albums, and beyond this is wasteful.

  @property
  def cover_small_key(self):
    return self._dbentry.cover_small

  @property
  def cover_large_key(self):
    return self._dbentry.cover_large

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

  def __init__(self, raw=None, raw_key=None, title=None, artist=None, tracks=[],
               add_date=None, asin=None,
               cover_small=None, cover_large= None, is_new=True,
               key=None, **kwds):
    if raw is not None:
      super(Album, self).__init__(raw=raw)
      return 
    elif raw_key is not None:
      super(Album, self).__init__(raw_key=raw_key)
      return

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
                                asin=asin
                                **kwds)

  # Right now, creating an album creates a bunch of new Songs on the spot
  # so you're probably going to want to put the album right after you make it
  # If you don't, you're a bad person and you hate good things
  # TODO: Make some transactional shortcut to all that mess
  @classmethod
  def new(cls, title, artist, tracks,
          add_date=None, asin=None,
          cover_small=None, cover_large= None, is_new=True,
          key=None, **kwds):
    return Album(title=title, artist=artist, tracks=tracks,
                 add_date=add_date, asin=asin, cover_small=cover_small,
                 is_new=is_new, key=key, **kwds)

  @ndb.transactional
  @staticmethod
  def _put_tracks(tracks, artist, album_key):
    tracks = [Song(title=trackname,
                   artist=artist,
                   album=key,).put() for trackname in tracks]
    return tracks


  # TODO: make this a classmethod/instancemethod hybrid??? I wish I knew what
  # to friggin' Google.
  # TODO: generalize this interface (caches some "new" elements)
  @classmethod
  def add_to_new_cache(cls, key, add_date=None):
    if add_date is None:
      add_date = datetime.datetime.now()
    new_cache = cls.cache_get(cls.NEW)
    if new_cache is not None:
      pass

  def add_to_cache(self):
    super(Album, self).add_to_cache()
    return self

  def purge_from_cache(self):
    super(Album, self).purge_from_cache()
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
              asin=None,
              order=None, num=-1):
    query = cls.query()

    if title is not None:
      query.filter(RawAlbum.title == title)
    if artist is not None:
      query.filter(RawAlbum.artist == artist)
    if is_new is not None:
      query.filter(RawAlbum.isNew == is_new)
    if asin is not None:
      query.filter(RawAlbum.asin == asin)

    # Usual album orders: 'add_date'
    if order is not None:
      query.order(order)

    if num == -1:
      return query.get(keys_only=True)
    return query.fetch(num, keys_only=True)

  def put(self):
    # If we've toggled the newness of the album, update cache.
    try:
      logging.debug(self.wasNew)
      if self.wasNew != self.is_new:
        logging.debug("We're about to update newcache")
        new_albums = self.get_new_keys()
        if self.isNew:
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
    return self._dbentry.title
  @property
  def artist(self):
    return self._dbentry.artist
  @property
  def tracklist(self):
    return self._dbentry.songList
  @property
  def add_date(self):
    return self._dbentry.add_date

  @property
  def is_new(self):
    return self._dbentry.isNew


  def set_new(self):
    self.wasNew = self.isNew
    self._dbentry.isNew = True
  def unset_new(self):
    self.wasNew = self.isNew
    self._dbentry.isNew = False

  @classmethod
  def get_new(cls, num=36, keys_only=False, sort=None):
    if num < 1:
      return None

    cached = cls.get_cached_query(cls.NEW)
    if not cached or cached.need_fetch(num):
      cached.set(
        cls.get_key(is_new=True, order="-add_date", num=num))

    cached.save()

    if not cached:
      return []

    if keys_only:
      return cached[:num]
    else:
      if sort == "artist":
        return sorted(cls.get(cached[:num]),
                      key=lambda album: album.artist.lower())
      else:
        return sorted(cls.get(cached[:num]),
                      key=lambda album: album.add_date)


  @classmethod
  def get_new_keys(cls, num=36, sort=None):
    return cls.get_new(num, keys_only=True)

class Song(CachedModel):
  '''A Song is an (entirely) immutable datastore object which represents
  a song; e.g. one played in the past or an element in a list of tracks.
  '''

  @property
  def album_key(self):
    return self._dbentry.album

  def to_json(self):
    return {
      'key': str_or_none(self.key),
      'title': self.title,
      'artist': self.artist,
      'album_key': str_or_none(self.album_key),
      }

  @classmethod
  def new(cls, title, artist, album=None,
               parent=None, key_name=None, **kwds):
    if parent is None:
      parent = album

    song = cls(parent=parent, key_name=key_name,
               title=title, artist=artist, **kwds)
    if album is not None:
      song.album = album

    return song

  def add_to_cache(self):
    super(Song, self).add_to_cache()
    return self

  def purge_from_cache(self):
    super(Song, self).purge_from_cache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None, order=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      logging.debug(keys)
      return super(Song, cls).get(keys, use_datastore=use_datastore,
                                        one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, title=None, order=None, num=-1):
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

class ArtistName(CachedModel):
  ## Functions for getting and setting Artists,
  ## Specifically, caching artist name autocompletion
  COMPLETE = "artist_pref%s"

  # Minimum number of entries in the cache with which we would even consider
  # not rechecking the datastore. Figit with this number to balance reads and
  # autocomplete functionality. Possibly consider algorithmically determining
  # a score for artist names and prefixes?
  MIN_AC_CACHE = 10
  MIN_AC_RESULTS = 5

  @classmethod
  def new(cls, artist_name, key_name=None, **kwds):
    artist = cls.get(artist_name=artist_name)
    if artist:
      return artist

    artist = cls(
      key_name=key_name,
      artist_name=artist_name,
      lowercase_name=artist_name.lower(),
      search_name=cls.get_search_name(artist_name),
      **kwds)
    return artist

  @classmethod
  def try_put(cls, artist_name, key_name=None, **kwds):
    artist = cls.get(artist_name=artist_name)
    if artist:
      return artist

    artist = cls(
      key_name=key_name,
      artist_name=artist_name,
      lowercase_name=artist_name.lower(),
      search_name=cls.get_search_name(artist_name),
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
      super(ArtistName, cls).get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, artist_name, num=-1):
    query = cls.all(keys_only=True)
    query.filter("lowercase_name =", artist_name.lower())

    if num == -1:
      return query.get()
    return query.fetch(num)

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

  @classmethod
  def has_prefix(cls, artist_key, prefix):
    prefixes = prefix.split()

    artist = cls.get(artist_key)
    if artist.search_name is None:
      if not artist.search_names:
        artist.search_name = cls.get_search_name(artist.artist_name)
      else:
        artist.search_name = " ".join(artist.search_names)
      artist.put()

    for name_part in artist.search_name.split():
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
    # First, see if we have anything already cached for us in memstore.
    # We start with the most specific prefix, and widen our search
    cache_prefix = prefix
    cached_results = None
    perfect_hit = True
    while cached_results is None:
      if len(cache_prefix) > 0:
        cached_results = cls.cache_get(cls.COMPLETE %cache_prefix)
        if cached_results is None:
          cache_prefix = cache_prefix[:-1]
          perfect_hit = False
      else:
        cached_results = {"recache_count": -1,
                          "max_results": False,
                          "artists": None,}

    # If we have a sufficient number of cached results OR we
    #    have all possible results, search in 'em.
    logging.debug(cache_prefix)
    logging.debug(cached_results)
    logging.debug(perfect_hit)
    if (cached_results["recache_count"] >= 0 and
        (cached_results["max_results"] or
         len(cached_results["artists"]) >= cls.MIN_AC_CACHE)):
      logging.debug("Trying to use cached results")

      cache_artists = sorted(cached_results["artists"],
                             key=lambda x: cls.get(x).search_name)

      # If the cache is perfect (exact match!), just return it
      if perfect_hit:
        # There is no need to update the cache in this case.
        logging.debug(cache_artists)
        return cls.get(cache_artists)

      # Otherwise we're going to have to search in the cache.
      results = filter(lambda a: cls.has_prefix(a, prefix),
                       cache_artists)
      if cached_results["max_results"]:
        # We're as perfect as we can be, so cache the results
        cached_results["recache_count"] += 1
        cached_results["artists"] = results
        cls.cache_set(cached_results, cls.COMPLETE, prefix)
        return cls.get(results)
      elif len(results) > cls.MIN_AC_RESULTS:
        if len(results) > cls.MIN_AC_CACHE:
          cached_results["recache_count"] += 1
          cached_results["artists"] = results
          cls.cache_set(cached_results, cls.COMPLETE, prefix)
          return cls.get(results)
        return cls.get(results)

    artists_full = (cls.all(keys_only=True)
                    .filter("lowercase_name >=", prefix)
                    .filter("lowercase_name <", prefix + u"\ufffd").fetch(10))
    artists_sn = (cls.all(keys_only=True)
                  .filter("search_name >=", prefix)
                  .filter("search_name <", prefix + u"\ufffd").fetch(10))
    max_results = len(artists_full) < 10 and len(artists_sn) < 10
    artist_dict = {}
    all_artists = cls.get(artists_full + artists_sn)
    for a in all_artists:
      artist_dict[a.artist_name] = a
    artists = []
    for a in artist_dict:
      artists.append(artist_dict[a])
    artists = sorted(artists, key=lambda x: x.search_name)

    results_dict = {"recache_count": 0,
                    "max_results": max_results,
                    "artists": [artist.key() for artist in artists]}
    cls.cache_set(results_dict, cls.COMPLETE, prefix)
    return artists