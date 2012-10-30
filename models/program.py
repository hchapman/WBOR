from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key
from base_models import QueryCache
from base_models import slugify

from _raw_models import Program as RawProgram

# Global python imports
import datetime
import random
import string
import logging

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
    return self._dbentry.title
  @title.setter
  def title(self, title):
    if not title:
      raise ModelError("A show's title cannot be blank")
    self._dbentry.title = title.strip()

  @property
  def slug(self):
    return self._dbentry.slug
  @slug.setter
  def slug(self, slug):
    self._dbentry.slug = slugify(slug if slug else title)

  @property
  def desc(self):
    return self._dbentry.desc
  @desc.setter
  def desc(self, desc):
    self._dbentry.desc = desc.strip() if desc else ""

  @property
  def page_html(self):
    return self._dbentry.page_html
  @page_html.setter
  def page_html(self, page_html):
    self._dbentry.page_html = page_html.strip() if page_html else ""

  @property
  def current(self):
    return self._dbentry.current
  @current.setter
  def current(self, current):
    self._dbentry.current = bool(current)

  @property
  def dj_list(self):
    return self._dbentry.dj_list
  @dj_list.setter
  def dj_list(self, dj_list):
    self._dbentry.dj_list = [as_key(dj) for dj in dj_list if dj]

  @property
  def num_top_plays(self):
    return self._dbentry.top_playcounts[0]
  @property
  def top_artists(self):
    return izip(self._dbentry.top_artists, self._dbentry.top_playcounts)

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
    playcounts = dict.fromkeys(self.top_artists, self.top_playcounts)
    if artist in playcounts:
      playcounts[artist] = playcounts[artist] + 1
    else:
      playcounts[artist] = self.get_artist_play_count(artist)

    playcounts = list(iteritems(playcounts))
    playcounts.sort(lambda x: x[1], reverse=True)
    playcounts = playcounts[:10]
    self.top_artists = [str(p[1]) for p in playcounts]
    self.top_playcounts = [int(p[0]) for p in playcounts]

  def get_artist_play_count(self, artist):
    return len(Play.get(program=self, artist=artist, keys_only=True, num=1000))

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