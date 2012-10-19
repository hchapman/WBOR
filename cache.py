#!/usr/bin/env python
#
# Written by Harrison Chapman,
#  based off code primarily by Seth Glickman
#
##############################
#   Any actual calls by the more forward-ends to access database
# elements should be through this file, as it is in this file that
# we cache items. This is critical now with the GAE's more strict
# database read quotas.

# This module is by no means threadsafe. Race conditions may occur
# TODO make this module work despite possible race conditions
#  e.g. implement memcache.Client() gets and cas functionality

# GAE Imports
from google.appengine.api import memcache
from google.appengine.ext import db

# Local module imports
import models_old as models
from models import *
from models.base_models import as_key

from passwd_crypto import hash_password, check_password

# Global python imports
import datetime
import logging
import itertools

LMC_SET_DEBUG = "Memcache set (%s, %s) required"
LMC_SET_FAIL = "Memcache set(%s, %s) failed"
LMC_DEL_ERROR = "Memcache delete(%s) failed with error code %s"

def mcset(value, cache_key, *args):
  logging.debug(LMC_SET_DEBUG %(cache_key %args, value))
  if not memcache.set(cache_key %args, value):
    logging.error(LMC_SET_FAIL % (cache_key %args, value))
  return value

def mcset_t(value, time, cache_key, *args):
  logging.debug(LMC_SET_DEBUG %(cache_key %args, value))
  if not memcache.set(cache_key %args, value, time=time):
    logging.error(LMC_SET_FAIL % (cache_key %args, value))
  return value

def mcdelete(cache_key, *args):
  response = memcache.delete(cache_key %args)
  if response < 2:
    logging.debug(LMC_DEL_ERROR %(cache_key, response))

def cacheGet(keys, model_class, cachekey_template,
             use_datastore=True, one_key=False):
  if keys is None:
    return None
  if isinstance(keys, model_class):
    return keys

  if (isinstance(keys, str) or
      isinstance(keys, unicode) or
      isinstance(keys, db.Key) or
      one_key):
    keys = (as_key(keys),)
    one_key = True

  if not one_key:
    objs = []
    db_fetch_keys = []

  for i, key in enumerate(keys):
    if key is None:
      return None,
    if isinstance(key, model_class):
      return key
    obj = memcache.get(cachekey_template %key)

    if obj is not None:
      if one_key:
        return obj
      objs.append(obj)

    if one_key:
      return model_class.get(key)

    # Store the key to batch fetch, and the position to place it
    if use_datastore:
      db_fetch_keys.append((i, key))

  # Improve this if possible. Use a batch fetch on non-memcache keys.
  db_fetch_zip = zip(db_fetch_keys) #[0]: idx, [1]: key
  for i, obj in zip(db_fetch_zip[0],
                    model_class.get(db_fetch_zip[1])):
    objs[i] = mcset(obj, cachekey_template %key)

  return filter(None, objs)

## Functions generally for getting and setting new Plays.
### Constants representing key templates for the memcache.
LAST_PLAYS = "last_plays"
LAST_PLAYS_SHOW = "last_plays_show%s"

LAST_PSA = "last_psa"

PLAY_ENTRY = "play_key%s"
PSA_ENTRY = "psa_key%s"


def getLastPlayKeys(num=1,
                    program=None, before=None, after=None):
  """Get the last num plays' keys. If num=1, return only the last play.
  Otherwise, return a list of plays.

  TODO: If we have k plays in memcache and want to get n > k plays,
  we should only need to read the latter k-n plays. Implement some sort
  of pagination to do this, if possible"""
  if num < 1:
    return None

  # Determine whether we are working with a program or not and get mc entry
  if program is None:
    lp_mc_key = LAST_PLAYS
  else:
    lp_mc_key = LAST_PLAYS_SHOW %program

  # We currently don't cache last plays for before/after queries.
  if before is None and after is None:
    last_plays = memcache.get(lp_mc_key)
    if last_plays is not None and None in last_plays:
      last_plays = [play for play in last_plays if play is not None]
  else:
    last_plays = None

  if last_plays is None or num > len(last_plays):
    logging.debug("Have to update %s memcache"%lp_mc_key)
    play_query = models.Play.all(keys_only=True).order("-play_date")

    # Add additional filters to the query, if applicable.
    # We do not currently cache before/after last plays
    should_cache = True
    if program is not None:
      play_query.filter("program =", program)
    if before is not None:
      play_query.filter("play_date <=", before)
      should_cache = False
    if after is not None:
      play_query.filter("play_date >=", after)
      should_cache = False

    if num == 1:
      last_plays = [play_query.get()]
    else:
      last_plays = play_query.fetch(num)

    if should_cache:
      mcset(last_plays, lp_mc_key)
  return last_plays[:num]

def getPlay(keys, use_datastore=True, one_key=False):
  """Get a play from its db key."""
  return cacheGet(keys, models.Play, PLAY_ENTRY,
                  use_datastore=use_datastore, one_key=one_key)

def getLastPlays(num=1,
                 program=None, before=None, after=None):
  """Get the last plays, rather than their keys."""

  return filter(None, [getPlay(key) for key in
                       getLastPlayKeys(num=num, program=program,
                                       before=before, after=after)])

def getLastPlay(program=None, before=None, after=None):
  play = getLastPlays(num=1, program=program, before=before, after=after)
  if play:
    return play[0]
  return None

def addNewPlay(song, program, artist,
               play_date=None, isNew=False):
  """If a DJ starts playing a song, add it and update the memcache."""
  if play_date is None:
    play_date = datetime.datetime.now()
  last_plays = memcache.get(LAST_PLAYS)
  play = models.Play(song=song,
                     program=program,
                     artist=artist,
                     play_date=play_date,
                     isNew=isNew)
  play.put()
  mcset(play, PLAY_ENTRY, play.key())
  if not last_plays:
    mcset([play], LAST_PLAYS)
  elif play_date > getPlay(last_plays[0]).play_date:
    last_plays.insert(0, play.key())
    mcset(last_plays, LAST_PLAYS)
  return play

def deletePlay(play_key, program=None):
  """Delete a play, and update appropriate memcaches"""
  # This is what you get when you find a stranger in the alps...
  # sorry, I mean don't link a program to this delete play call
  if program is None:
    play = getPlay(play_key).program.key()

  try_delete_keys = [LAST_PLAYS]
  if program is not None:
    try_delete_keys.append(LAST_PLAYS_SHOW %program)

  for key in try_delete_keys:
    entry = memcache.get(key)
    if entry is not None:
      try:
        entry.remove(db.Key(encoded=play_key))
        mcset(entry, key)
        logging.debug(len(entry))
      except:
        logging.error("%s not found in %s"%(db.Key(play_key), entry))

  # We've removed any other references to this play, so delete it
  db.delete(play_key)
  mcdelete(PLAY_ENTRY, play_key)

def getLastPsaKey():
  psa = memcache.get(LAST_PSA)
  if psa is None:
    logging.debug("Have to updates %s memcache" %LAST_PSA)
    psa = models.Psa.all(keys_only=True).order("-play_date").get()
    if psa:
      mcset(psa, LAST_PSA)
  return psa

def getPsa(keys, use_datastore=True, one_key=False):
  return cacheGet(keys, models.Psa, PSA_ENTRY,
                  use_datastore=use_datastore, one_key=one_key)

def getLastPsa():
  return getPsa(getLastPsaKey())

def addNewPsa(desc, program, play_date=None):
  """If a DJ charts a PSA, be sure to update the memcache"""
  if play_date is None:
    play_date = datetime.datetime.now()
  last_psa = getLastPsa()
  psa = models.Psa(desc=desc, program=program, play_date=play_date)
  psa.put()
  mcset(psa, PSA_ENTRY, psa.key())
  if last_psa is None or play_date > last_psa.play_date:
    mcset(psa.key(), LAST_PSA)


## Functions for getting and setting Albums
NEW_ALBUMS = "new_albums"
ALBUM_ENTRY = "album_key%s"

def setAlbumIsNew(key, is_new=True):
  album = getAlbum(key)
  if album is not None:

    album.isNew = is_new
    album.put()
    mcset(album, ALBUM_ENTRY, key)
    new_albums = memcache.get(NEW_ALBUMS)
    if not new_albums:
      mcset([key], NEW_ALBUMS)
    elif is_new:
      new_albums.append(key)
      mcset(new_albums, NEW_ALBUMS)
    else:
      new_albums.remove(db.Key(encoded=key))
      mcset(new_albums, NEW_ALBUMS)
    return True
  return False

def getNewAlbumKeys(num=50):
  """Get the last num new albums. Returns a list of album keys."""
  if num < 1:
    return None

  new_albums = memcache.get(NEW_ALBUMS)
  if new_albums is not None and None in new_albums:
    new_albums = [album for album in new_albums if album is not None]

  if new_albums is None or num > len(new_albums):
    logging.debug("Have to update %s memcache"%NEW_ALBUMS)
    album_query = models.Album.all(
      keys_only=True).filter("isNew =", True).order("-add_date")

    new_albums = album_query.fetch(num)
    mcset(new_albums, NEW_ALBUMS)

  return new_albums[:num]

def getAlbum(keys, use_datastore=True, one_key=False):
  return cacheGet(keys, models.Album, ALBUM_ENTRY,
                  use_datastore=use_datastore, one_key=one_key)

def getNewAlbums(num=50, by_artist=False):
  albums = filter(None, [getAlbum(key) for key in
                         getNewAlbumKeys(num=num)])
  if by_artist:
    return sorted(albums, key=lambda album: album.artist.lower())
  else:
    return sorted(albums, key=lambda album: album.add_date)
