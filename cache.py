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
import models

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

  if isinstance(keys, str) or isinstance(keys, db.Key) or one_key:
    keys = (keys,)
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
        logging.info(len(entry))
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
  
## Functions for getting and setting Songs
SONG_ENTRY = "song_key%s"

def getSong(keys, use_datastore=True, one_key=False):
  return cacheGet(keys, models.Song, SONG_ENTRY, 
                  use_datastore=use_datastore, one_key=one_key)

def putSong(title, artist, album=None):
  song = models.Song(parent=album,
                     title=title, artist=artist)
  if album is not None:
    song.album = album
  song.put()
  return mcset(song, SONG_ENTRY %song.key())

## Functions for getting and setting DJs
DJ_ENTRY = "dj_key%s"

## Primary Dj getting functions
def getDj(keys=None,
          username=None, email=None, order=None,
          num=-1, use_datastore=True, one_key=False):
  if keys is not None:
    return cacheGet(keys, models.Dj, DJ_ENTRY, 
                    use_datastore=use_datastore, one_key=one_key)

  keys = getDjKey(username=username, email=email, order=order, num=num)  
  if keys is not None:
    return getDj(keys=keys, use_datastore=use_datastore)
  return None

def getDjKey(username=None, email=None, program=None, order=None, num=-1):
  query = models.Dj.all(keys_only=True)

  if username is not None:
    query.filter("username =", username)
  if email is not None:
    query.filter("email =", username)

  if order is not None:
    query.order(order)

  if num == -1:
    return query.get()
  return query.fetch(num)

## Primary Dj setting functions    
def putDj(email=None, fullname=None, username=None, 
          password=None, edit_dj=None,
          fix_email=True):
  if edit_dj is None:
    if None in (email, fullname, username, password):
      raise Exception("Insufficient fields for new Dj")
    if fix_email: # Add @bowdoin.edu to undressed emails
      if email[-1] == "@":
        email += "bowdoin.edu"
      if "@" not in email:
        email += "@bowdoin.edu"
    dj = models.Dj(fullname=fullname, 
                   lowername=fullname.lower(),
                   email=email,
                   username=username, 
                   password_hash=hash_password(password))
  else:
    dj = getDj(edit_dj) # In case they passed a key
    if dj is None:
      raise Exception("Quantum Dj nonexistance error")
    
    if fullname is not None:
      dj.fullname = fullname
      dj.lowername = fullname.lower()
    if email is not None:
      if fix_email: # Add @bowdoin.edu to undressed emails
        if email[-1] == "@":
          email += "bowdoin.edu"
        if "@" not in email:
          email += "@bowdoin.edu"
      dj.email = email
    if username is not None: # Although this should be an immutable property
      dj.username = username
    if password is not None:
      dj.password_hash = hash_password(password)

  if dj is not None:
    dj.put()
    return mcset(dj, DJ_ENTRY %dj.key())

  return None

## Primary Dj deleting functions
def deleteDj(dj):
  if dj is None:
    raise Exception("No Dj to delete")
  try:
    dj = getDj(dj)
  except:
    raise Exception("Unable to determine Dj to delete")

  if dj is not None:
    mcset(None, DJ_ENTRY %dj.key())
    dj.delete()
  
## Auxiliary Dj functions
def getAllDjs():
  return getDj(order="fullname", num=1000)
  
def getDjByUsername(username):
  return getDj(username=username)

def getDjByEmail(email):
  return getDj(email=email)
  
def djLogin(username, password):
  dj = getDj(username=username)
  if dj is not None:
    if check_password(dj.password_hash, password):
      return dj
  return None
  

## Functions for getting and setting Programs
PROGRAM_ENTRY = "program_key%s"
PROGRAM_EXPIRE = 360  # Program cache lasts for one hour maximum

DJ_PROGRAMS = "programs_by_dj%s"

def getProgram(keys=None, slug=None, order=None, num=-1,
               use_datastore=True, one_key=False):
  # We're getting the program by key
  if keys is not None:
    return cacheGet(keys, models.Program, PROGRAM_ENTRY, 
                    use_datastore=use_datastore, one_key=one_key)

  # We're using a query on programs instead
  keys = getProgramKey(slug=slug, order=order, num=num)
  if keys is not None:
    return getProgram(keys=keys, use_datastore=use_datastore)
  return None
  
def getProgramKey(slug=None, order=None, num=-1):
  query = models.Program.all(keys_only=True)

  if slug is not None:
    query.filter("slug =", slug)

  if order is not None:
    query.order(order)

  # Consider adding query caching here, if necessary
  if num == -1:
    return query.get()
  return query.fetch(num)

def getAllPrograms():
  return filter(None, [getProgram(key) for key in
                       getProgramKeys(order="title")])

def getPrograms(dj=None, order=None):
  program_keys = getProgramKeys(dj=dj, order=order)
  return filter(None, [getProgram(key) for key in program_keys])
  
def getProgramKeys(dj=None, order=None):
  query = models.Program.all(keys_only=True)

  if dj is not None:
    if isinstance(dj, models.Dj):
      dj = dj.key()
    if dj is not None:
      query.filter("dj_list =", dj)

  if order is not None:
    query.order(order)

  # TODO if more filters are added, be sure to modify this
  cached = memcache.get(DJ_PROGRAMS %dj)
  if cached is not None:
    return cached  

  return mcset(query.fetch(1000), DJ_PROGRAMS %dj)

## Functions for getting and setting Albums
NEW_ALBUMS = "new_albums"
ALBUM_ENTRY = "album_key%s"

def putAlbum(title, artist, tracks, add_date=None, asin=None, 
             cover_small=None, cover_large=None, isNew=True):
  if add_date is None:
    add_date = datetime.datetime.now()

  album_fake_key = db.Key.from_path("Album", 1)
  batch = db.allocate_ids(album_fake_key, 1)
  album_key = db.Key.from_path('Album', batch[0])

  song_keys = [putSong(title=trackname,
                       artist=artist,
                       album=album_key,
                       ).key()
               for trackname in tracks]

  tryPutArtist(artist)

  album = models.Album(
    key=album_key,
    title=title,
    lower_title=title.lower(),
    artist=artist,
    add_date=add_date,
    isNew=isNew,
    songList=song_keys,
    )

  if cover_small is not None:
    album.cover_small = cover_small
  if cover_large is not None:
    album.cover_large = cover_large
  if asin is not None:
    album.asin = asin

  album.put()

  if isNew:
    pass

  return mcset(album, ALBUM_ENTRY, album.key())

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

# Functions for getting and setting Permissions
# As it stands, permissions are only dealt with using human-readable
# permission labels.
PERMISSION_ENTRY = "permission_key%s"
PERMISSION_LABEL = "permission_label%s"

PERMISSIONS = "all_permissions_cache"

def getPermissionKey(label):
  if label is None:
    return None
  if isinstance(label, models.Permission):
    return label

  cached = memcache.get(PERMISSION_LABEL %label)
  if cached is not None:
    return cached
  
  key = Permission.all(keys_only=True).filter("title =", label).get(),
  return mcset(key, PERMISSION_LABEL %label)

def getPermissions():
  keys = memcache.get(PERMISSIONS)
  if keys is None:
    keys = Permission.all(keys_only=True).order("-title").fetch(100)
    mcset(keys, PERMISSIONS)

  return filter(None, [getPermission(key) for key in keys])

def getPermission(keys=None, label=None, use_datastore=True, one_key=False):
  if label is not None and keys is None:
    if isinstance(label, models.Permission):
      return label
    keys = getPermissionKey(label)

  return cacheGet(keys, models.Permission, PERMISSION_ENTRY, 
                  use_datastore=use_datastore, one_key=one_key)

def hasPermission(dj, label):
  if isinstance(dj, models.Dj):
    dj_key = dj.key()
  else:
    dj_key = dj

  if dj_key is None:
    return False

  # For now we have a fixed set of possible permissions
  if label in models.Permission.PERMISSIONS:
    return dj_key in getPermission(label)

  return False

## Functions for getting and setting Artists,
## Specifically, caching artist name autocompletion 
ARTIST_COMPLETE = "artist_pref%s"
ARTIST_ENTRY = "artist_key%s"

# Minimum number of entries in the cache with which we would even consider
# not rechecking the datastore. Figit with this number to balance reads and
# autocomplete functionality. Possibly consider algorithmically determining
# a score for artist names and prefixes?
ARTIST_MIN_AC_CACHE = 10
ARTIST_MIN_AC_RESULTS = 5

# Another suggestion: implement a "search accuracy" probabilistic system by
# which results repeatedly based off of previous cache results have less
# and less validity and more likeliness to not "Be everything"

def tryPutArtist(artist_name):
  # See if the artist is in the datastore already
  key = getArtistKey(artist_name)
  if key:
    # We have a new album, so we might as well memcache the artist.
    return getArtist(key)
  
  artist = models.ArtistName(
    artist_name=artist_name,
    lowercase_name=artist_name.lower(),
    search_names=models.artistSearchName(artist_name).split())
  artist.put()
  mcset(artist, ARTIST_ENTRY, artist.key())
  injectArtistAutocomplete(artist)
  return artist

def getArtistKey(a_name=None):
  artist = models.ArtistName.all(keys_only=True).filter(
    "lowercase_name =", a_name.lower()).get()
  if artist:
    return artist
  return None

def getArtist(key, use_datastore=True, one_key=False):
  return cacheGet(keys, models.ArtistName, ARTIST_ENTRY, 
                  use_datastore=use_datastore, one_key=one_key)

# Replace with batch get of uncached database entities
def getArtists(keys):
  return filter(None,
                [getArtist(key) for key in keys if key is not None])

def injectArtistAutocomplete(artist):
  # I don't know if it's a good idea or not to
  # flood memcache with a new artist; if it ends up being that
  # way then write this function
  pass

def artistAutocomplete(prefix):
  prefix = prefix.lower()
  # First, see if we have anything already cached for us in memstore.
  # We start with the most specific prefix, and widen our search
  cache_prefix = prefix
  cached_results = None
  perfect_hit = True
  while cached_results is None:
    if len(cache_prefix) > 0:
      cached_results = memcache.get(ARTIST_COMPLETE %cache_prefix)
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
       len(cached_results["artists"]) >= ARTIST_MIN_AC_CACHE)):
    logging.debug("Trying to use cached results")

    cache_artists = sorted(cached_results["artists"],
                           key=lambda x: getArtist(x).search_name)

    # If the cache is perfect (exact match!), just return it
    if perfect_hit:
      # There is no need to update the cache in this case.
      return getArtists(cache_artists)

    # Otherwise we're going to have to search in the cache.
    results = filter(lambda a: (getArtist(a).lowercase_name.startswith(prefix) or
                                (getArtist(a).search_name is not None and 
                                 getArtist(a).search_name.startswith(prefix))),
                     cache_artists)
    if cached_results["max_results"]:
      # We're as perfect as we can be, so cache the results
      cached_results["recache_count"] += 1
      cached_results["artists"] = results
      mcset(cached_results, ARTIST_COMPLETE, prefix)
      return getArtists(results)
    elif len(results) > ARTIST_MIN_AC_RESULTS:
      if len(results) > ARTIST_MIN_AC_CACHE:
        cached_results["recache_count"] += 1
        cached_results["artists"] = results
        mcset(cached_results, ARTIST_COMPLETE, prefix)
        return getArtists(results)
      return getArtists(results)
  
  artists_full = models.ArtistName.all(keys_only=True).filter("lowercase_name >=", prefix
             ).filter("lowercase_name <", prefix + u"\ufffd").fetch(10)
  artists_sn = models.ArtistName.all(keys_only=True).filter("search_name >=", prefix
             ).filter("search_name <", prefix + u"\ufffd").fetch(10)
  max_results = len(artists_full) < 10 and len(artists_sn) < 10
  artist_dict = {}
  all_artists = getArtists(artists_full + artists_sn)
  for a in all_artists:
    artist_dict[a.artist_name] = a
  artists = []
  for a in artist_dict:
    artists.append(artist_dict[a])
  artists = sorted(artists, key=lambda x: x.search_name)

  results_dict = {"recache_count": 0,
                  "max_results": max_results,
                  "artists": [artist.key() for artist in artists]}
  mcset(results_dict, ARTIST_COMPLETE, prefix)
  return artists
