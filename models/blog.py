from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key

from play import LastCachedModel

from _raw_models import BlogPost as RawBlogPost
from _raw_models import Event as RawEvent

# Global python imports
import datetime
import random
import string

class BlogPost(LastCachedModel):
  _RAW = RawBlogPost
  _RAWKIND = "BlogPost"

  LAST = "last_posts"
  LAST_ORDER = -1
  LAST_ORDERBY = (-_RAW.post_date,)

  @property
  def _orderby(self):
    return self.post_date

  @property
  def title(self):
    return self.raw.title
  @title.setter
  def title(self, title):
    self.raw.title = title

  @property
  def slug(self):
    return self.raw.slug
  @slug.setter
  def slug(self, slug):
    self.raw.slug = slug

  @property
  def text(self):
    return self.raw.text
  @text.setter
  def text(self, text):
    self.raw.text = text

  @property
  def post_date(self):
    return self.raw.post_date

  def __init__(self, raw=None, raw_key=None,
               title=None, text=None, post_date=None,
               slug=None, parent=None, **kwds):
    if raw is not None:
      super(BlogPost, self).__init__(raw=raw)
      return
    elif raw_key is not None:
      super(BlogPost, self).__init__(raw_key=raw_key)
      return

    else:
      if post_date is None:
        post_date = datetime.datetime.now()
      super(BlogPost, self).__init__(
        title=title, text=text,
        post_date=post_date, slug=slug, parent=parent)

  @classmethod
  def new(cls, title, text, slug, post_date=None, parent=None, **kwds):
    return cls(title=title, text=text, slug=slug, post_date=post_date,
               parent=parent, **kwds)

  @classmethod
  def get(cls, keys=None, slug=None, before=None,
          after=None, order=None, num=-1, page=False,
          cursor=None, one_key=False):
    if keys is not None:
      return super(BlogPost, cls).get(keys=keys,
                                  one_key=one_key)

    keys = cls.get_key(before=before, after=after, slug=slug,
                       order=order, num=num, page=page, cursor=cursor)
    if page:
      keys, cursor, more = keys

    if keys is not None:
      if page:
        return (cls.get(keys=keys), cursor, more)
      else:
        return cls.get(keys=keys)
    return None

  @classmethod
  def get_key(cls, slug=None, before=None, after=None, order=None,
              num=-1, page=False, cursor=None):
    query = cls._RAW.query()

    if slug is not None:
      query = query.filter(cls._RAW.slug == slug)
    if after is not None:
      query = query.filter(cls._RAW.play_date >=
                           datetime.datetime.combine(after, datetime.time()))
    if before is not None:
      query = query.filter(cls._RAW.play_date <
                           datetime.datetime.combine(after, datetime.time()))

    if order is not None:
      query = query.order(*order)

    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  @classmethod
  def get_last(cls, num=3, keys_only=False):
    return super(BlogPost, cls).get_last(num=num, keys_only=keys_only)

class Event(CachedModel):
  _RAW = RawEvent
  _RAWKIND = "Event"