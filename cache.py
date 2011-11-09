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

# GAE Imports
from google.appengine.api import memcache
from google.appengine.ext import db

# Local module imports
import models

# Global python imports
import datetime
import logging

## Functions generally for getting and setting new Plays.
### Constants representing key templates for the memcache.
LAST_PLAYS = "last_plays"
LAST_PLAYS_SHOW = "last_plays_%s"

DAY_PLAYS = "day_plays_day%s"
DAY_PLAYS_SHOW = "day_plays_day%s_show%s"

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
  if program is None:
    last_plays = memcache.get(LAST_PLAYS)
    if last_plays is None or num > len(last_plays):
      logging.debug("Have to update %s memcache"%LAST_PLAYS)
      play_query = models.Play.all(keys_only=True).order("-play_date")
      if num == 1:
        last_plays = [play_query.get()]
      else:
        last_plays = play_query.fetch(num)
      if not memcache.set(LAST_PLAYS, last_plays):
        logging.error("Memcache set %s failed"%LAST_PLAYS)
    return last_plays[:num]
  else:
    # TODO: Implement caching for program and other possible queries
    pass
  return plays

def getPlay(key):
  """Get a play from its db key."""
  play = memcache.get(PLAY_ENTRY %key)
  if play is None:
    logging.debug("Have to update %s memcache" %PLAY_ENTRY%key)
    play = db.get(key)
    if not memcache.set(PLAY_ENTRY%key, play):
      logging.error("Memcache set %s failed"%PLAY_ENTRY%key)
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

def getLastPsaKey():
  psa = memcache.get(LAST_PSA)
  if psa is None:
    logging.debug("Have to updates %s memcache" %LAST_PSA)
    psa = models.Psa.all(keys_only=True).order("-play_date").get()
    if psa:
      if not memcache.set(LAST_PSA, psa):
        logging.error("Memcache set %s failed"%LAST_PSA)
  return psa

def getPsa(key):
  psa = memcache.get(PSA_ENTRY %key)
  if psa is None:
    logging.debug("Have to update %s memcache"%PSA_ENTRY%key)
    psa = db.get(key)
    if not memcache.set(PSA_ENTRY%key, psa):
      logging.error("Memcache set %s failed"%PSA_ENTRY%key)
  return psa
    
def getLastPsa():
  return getPsa(getLastPsaKey())

