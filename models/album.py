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

# Global python imports
import logging
import itertools

class Album(CachedModel):
  ENTRY = "album_key%s"

  NEW = "new_albums" # Keep the newest albums cached.
  MIN_NEW = 50 # We want to keep so many new albums in cache, since it's the
               # most typically ever encountered in normal website usage.
  MAX_NEW = 75 # There should be no reason to have more than this many
               # cached new albums, and beyond this is wasteful.

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

  # Right now, creating an album creates a bunch of new Songs on the spot
  # so you're probably going to want to put the album right after you make it
  # If you don't, you're a bad person and you hate good things
  @classmethod
  def new(cls, title, artist, tracks,
          add_date=None, asin=None,
          cover_small=None, cover_large= None, is_new=True,
          key=None, parent=None, key_name=None, **kwds):
    if add_date is None:
      add_date = datetime.datetime.now()
    if key is None:
      proto_key = db.Key.from_path("Album", 1)
      batch = db.allocate_ids(proto_key, 1)
      key = db.Key.from_path('Album', batch[0])

    # Instantiate the tracks, put them (Model.put() returns keys)
    if tracks:
      tracks = [Song(title=trackname,
                     artist=artist,
                     album=key,).put() for trackname in tracks]

    album = cls(parent=parent, key_name=key_name,
                key=key, title=title,
                lower_title=title.lower(),
                artist=artist,
                add_date=add_date,
                isNew=is_new,
                songList=tracks,
                **kwds)

    if cover_small is not None:
      album.cover_small = cover_small
    if cover_large is not None:
      album.cover_large = cover_large
    if asin is not None: # Amazon isn't working still as of time of writing
      album.asin = asin

    return album

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
    query = cls.all(keys_only=True)

    if title is not None:
      query.filter("title =", title)
    if artist is not None:
      query.filter("artist =", artist)
    if is_new is not None:
      query.filter("isNew =", is_new)
    if asin is not None:
      query.filter("asin =", asin)

    # Usual album orders: 'add_date'
    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self, is_new=None):
    if is_new is not None:
      self.wasNew = self.isNew
      self.isNew = is_new

    # If we've toggled the newness of the album, update cache.
    try:
      logging.debug(self.wasNew)
      if self.wasNew != self.isNew:
        logging.debug("We're about to update newcache")
        new_albums = self.get_new_keys()
        if self.isNew:
          if not new_albums:
            new_albums = [self.key(),]
          else:
            new_albums.append(self.key())
        else:
          new_albums.remove(self.key())

        self.cache_set(new_albums, self.NEW)
    except AttributeError:
      pass

    return super(Album, self).put()

  # Albums are immutable Datastore entries, except for is_new status.
  @property
  def p_title(self):
    return self.title
  @property
  def p_artist(self):
    return self.artist
  @property
  def p_tracklist(self):
    return self.songList
  @property
  def p_add_date(self):
    return self.add_date

  @property
  def p_is_new(self):
    return self.isNew


  def set_new(self):
    self.wasNew = self.isNew
    self.isNew = True
  def unset_new(self):
    self.wasNew = self.isNew
    self.isNew = False

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
          title=None,
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

class ArtistName(db.Model):
  artist_name = db.StringProperty()
  lowercase_name = db.StringProperty()
  search_name = db.StringProperty()
  search_names = db.StringListProperty()