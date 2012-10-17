from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key

# Global python imports
import datetime
import random
import string

class Program(CachedModel):
  ## Functions for getting and setting Programs
  ENTRY = "program_key%s"
  EXPIRE = 360  # Program cache lasts for one hour maximum

  BY_DJ_ENTRY = "programs_by_dj%s"

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
    query = cls.all(keys_only=True)

    if slug is not None:
      query.filter("slug =", slug)
    if dj is not None:
      query.filter("dj_list =", as_key(dj))

    if order is not None:
      query.order(order)

    # Consider adding query caching here, if necessary
    if num == -1:
      return query.get()
    return query.fetch(num)

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

    cached = cls.get_cached_query(cls.BY_DJ_ENTRY, dj)

    if cached is None or cached.need_fetch(num):
      cached.set(cls.get_key(num=num), num)

    cached.save()
    if not cached:
      return []

    if keys_only:
      if only_one:
        return cached[-1]
      return cached[:num]
    else:
      if only_one:
        return cls.get(cached[-1])
      return cls.get(cached[:num])

  title = db.StringProperty()
  slug = db.StringProperty()
  desc = db.StringProperty(multiline=True)
  dj_list = db.ListProperty(db.Key)
  page_html = db.TextProperty()
  top_artists = db.StringListProperty()
  top_playcounts = db.ListProperty(int)
  current = db.BooleanProperty(default=False)

  def get_last_plays(self, *args, **kwargs):
    return []

  def to_json(self):
    return {
      'key': str_or_none(self.key()),
      'title': self.title,
      'slug': self.slug,
      'desc': self.desc,
      'dj_list': [str_or_none(dj_key) for dj_key in self.dj_list],
      'page_html': self.page_html,
      'top_artists': self.top_artists,
      'top_playcounts': self.top_playcounts,
      'current': self.current
    }