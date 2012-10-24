from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key
from base_models import slugify

# Global python imports
import datetime
import random
import string
import logging

class Program(CachedModel):
  ## Functions for getting and setting Programs
  ENTRY = "program_key%s"
  EXPIRE = 360  # Program cache lasts for one hour maximum

  BY_DJ_ENTRY = "programs_by_dj%s"

  @classmethod
  def new(cls, title, slug, desc, dj_list, page_html, current=True):
    if not title:
      raise Exception("Insufficient data to create show")

    program = cls(title=title,
                  slug=slugify(slug if slug else title),
                  desc=desc,
                  dj_list=[as_key(dj) for dj in dj_list if dj],
                  page_html=page_html,
                  current=bool(current))

    return program

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

  @property
  def p_title(self):
    return self.title
  @p_title.setter
  def p_title(self, title):
    if not title:
      raise ModelError("A show's title cannot be blank")
    self.title = title.strip()

  @property
  def p_slug(self):
    return self.slug
  @p_slug.setter
  def p_slug(self, slug):
    self.slug = slugify(slug if slug else title)

  @property
  def p_desc(self):
    return self.desc
  @p_desc.setter
  def p_desc(self, desc):
    self.desc = desc.strip() if desc else ""

  @property
  def p_page_html(self):
    return self.page_html
  @p_page_html.setter
  def p_page_html(self, page_html):
    self.page_html = page_html.strip() if page_html else ""

  @property
  def p_current(self):
    return self.current
  @p_current.setter
  def p_current(self, current):
    self.current = bool(current)

  @property
  def p_dj_list(self):
    return self.dj_list
  @p_dj_list.setter
  def p_dj_list(self, dj_list):
    self.dj_list = [as_key(dj) for dj in dj_list if dj]

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