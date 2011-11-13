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

# Global python imports
import datetime
import logging

LMC_SET_FAIL = "Memcache set(%s, %s) failed"
LMC_DEL_ERROR = "Memcache delete(%s) failed with error code %s"

def mcset(value, cache_key, *args):
  if not memcache.set(cache_key %args, value):
    logging.error(LMC_SET_FAIL % (cache_key %args, value))

def mcdelete(cache_key, *args):
  response = memcache.delete(cache_key %args)
  if response < 2:
    logging.debug(LMC_DEL_ERROR %(cache_key, response))

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
  else:
    last_plays = None

  logging.error(last_plays)
  if last_plays is None or num > len(last_plays):
    logging.info("Have to update %s memcache"%lp_mc_key)
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

def getPlay(key):
  """Get a play from its db key."""
  play = memcache.get(PLAY_ENTRY %key)
  if play is None:
    logging.info("Have to update %s memcache" %PLAY_ENTRY%key)
    play = db.get(key)
    mcset(play, PLAY_ENTRY, key)
  return play

def getLastPlays(num=1,
                 program=None, before=None, after=None):
  """Get the last plays, rather than their keys. Please do not use
  this function unless you are trying to debug something rediculous,
  rapidly prototype some functionality, or you improve this 
  implementation

  ***HACK***"""
  return [getPlay(key) for key in getLastPlayKeys(num=num, program=program,
                                                  before=before, after=after)]

def addNewPlay(song, program, artist,
               play_date=None, isNew=False):
  """If a DJ starts playing a song, add it and update the memcache."""
  if play_date is None:
    play_date = datetime.datetime.now()
  last_play = memcache.get(LAST_PLAYS)
  play = models.Play(song=song,
                     program=program,
                     artist=artist,
                     play_date=play_date,
                     isNew=isNew)
  play.put()
  mcset(play, PLAY_ENTRY, play.key())
  if last_plays is None: 
    mcset([play], LAST_PLAYS)
  elif play_date > last_plays[0].play_date:
    last_plays.insert(0, play)
    mcset(last_plays, LAST_PLAYS)

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
        pass

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

def getPsa(key):
  psa = memcache.get(PSA_ENTRY %key)
  if psa is None:
    logging.debug("Have to update %s memcache"%PSA_ENTRY%key)
    psa = db.get(key)
    mcset(psa, PSA_ENTRY, key)
  return psa
    
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
  

