from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key

from _raw_models import BlogPost as RawBlogPost
from _raw_models import Event as RawEvent

# Global python imports
import datetime
import random
import string

class BlogPost(CachedModel):
  _RAW = RawBlogPost
  _RAWKIND = "BlogPost"

  @property
  def title(self):
    return self.raw.title
  @title.setter
  def title(self, title):
    self.raw.title = title

  @property
  def slug(self):
    return self.raw.slug
  @slug.settter
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


class Event(CachedModel):
  _RAW = RawEvent
  _RAWKIND = "Event"