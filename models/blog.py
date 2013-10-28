from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key, accepts_raw

from play import LastCachedModel

from _raw_models import BlogPost as RawBlogPost
from _raw_models import Event as RawEvent

# Global python imports
import datetime
import random
import string
import logging

@accepts_raw
class BlogPost(LastCachedModel):
  _RAW = RawBlogPost
  _RAWKIND = "BlogPost"

  LAST = "last_posts_before%s_after%s"
  LAST_ORDER = -1
  LAST_ORDERBY = (-_RAW.post_date,)

  BY_SLUG = "@blogpost_slug%s_date%s"

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
  @property
  def post_date_as_date(self):
    return self.post_date.date()

  def __init__(self, is_fresh=False,
               title=None, text=None, post_date=None,
               slug=None, parent=None, **kwargs):
    if post_date is None:
      post_date = datetime.datetime.now()

    super(BlogPost, self).__init__(
      title=title, text=text,
      post_date=post_date, slug=slug, parent=parent, **kwargs)
    self.is_fresh = is_fresh

  @classmethod
  def new(cls, title, text, slug, post_date=None, parent=None, **kwds):
    return cls(title=title, text=text, slug=slug, post_date=post_date,
               parent=parent, is_fresh=True, **kwds)

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
      query = query.filter(cls._RAW.post_date >=
                           datetime.datetime.combine(after, datetime.time()))
    if before is not None:
      query = query.filter(cls._RAW.post_date <
                           datetime.datetime.combine(before, datetime.time()))

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

  @classmethod
  def get_by_slug(cls, slug, post_date=None):
    before = None
    after = None

    if post_date is not None:
      if isinstance(post_date, datetime.date):
        after = datetime.datetime.combine(
          post_date, datetime.time())
      else:
        after = datetime.datetime.combine(
          post_date.date(), datetime.time())
      before = after + datetime.timedelta(days=1)

    logging.error("what")
    logging.error(before)
    logging.error(after)
    cached = cls._get_slug_cache(slug, after)
    if cached is not None:
      return cached
    dateless_cached = cls._get_slug_cache(slug)
    if dateless_cached is not None:
      if (dateless_cached.post_date >= before and
          dateless_cached.post_date < after):
        cls._add_slug_cache(dateless_cached.key, slug, after)
        return dateless_cached


    post = cls.get(slug=slug, before=before, after=after)
    if post is not None:
      # Add post to appropriate caches
      cls._add_slug_cache(post.key, slug, after)
      if dateless_cached is None:
        cls._add_slug_cache(post.key, slug)

      return post
    return None


  def put(self):
    super(BlogPost, self).put()
    self.is_fresh = False

  @classmethod
  def _get_slug_cache(cls, slug, date=None, keys_only=False):
    return cls.get_by_index(cls.BY_SLUG, slug, date, keys_only=keys_only)
  @classmethod
  def _add_slug_cache(cls, key, slug, date=None):
    return cls.cache_set(key, cls.BY_SLUG, slug, date)

  def add_to_cache(self):
    super(BlogPost, self).add_to_cache()

    # Add self to slug caches
    self._add_slug_cache(self.key, self.slug)
    self._add_slug_cache(self.key, self.slug,
                         datetime.datetime.combine(
                           self.post_date.date(), datetime.time()))

    try:
      if self.is_fresh:
        self.add_own_last_cache()
    except AttributeError:
      pass

  # Utility method so that a last-cacheable entry knows how to
  # lastcache itself.
  def add_own_last_cache(self):
    self.add_to_last_cache(self) # We don't do anything special for BlogPosts

  def purge_from_cache(self):
    super(BlogPost, self).purge_from_cache()

    # Purge slug caches, if appropriate
    if self.key == self._get_slug_cache(self.slug,
                                        self.post_date_as_date,
                                        keys_only=True):
      self.cache_delete(self.BY_SLUG, self.slug, self.post_date_as_date)
    if self.key == self._get_slug_cache(self.slug, keys_only=True):
      self.cache_delete(self.BY_SLUG, self.slug, None)
    self.purge_from_last_cache(self.key)

@accepts_raw
class Event(LastCachedModel):
  _RAW = RawEvent
  _RAWKIND = "Event"

  LAST = "upcoming_events_before%s_after%s"
  LAST_ORDER = 1
  LAST_ORDERBY = (_RAW.event_date,)

  BY_SLUG = "@event_slug%s_date%s"

  # Hidden properties, for caching parent classes
  @property
  def _orderby(self):
    return self.event_date

  @staticmethod
  def _last_cmp(new_date, old_date):
    return new_date <= old_date

  # Properties to access datastore data
  @property
  def title(self):
    return self.raw.title
  @title.setter
  def title(self, title):
    self.raw.title = title

  @property
  def slug(self):
    return self.raw.url
  @slug.setter
  def slug(self, slug):
    self.raw.url = slug

  @property
  def text(self):
    return self.raw.desc
  @text.setter
  def text(self, text):
    self.raw.desc = text

  @property
  def event_date(self):
    return self.raw.event_date
  @event_date.setter
  def event_date(self, date):
    self.raw.event_date = date

  @property
  def event_date_as_date(self):
    return self.event_date.date()

  def __init__(self, 
               title=None, text=None, event_date=None,
               slug=None, parent=None, is_fresh=False, **kwargs):
    if event_date is None:
      raise ModelError("It makes no sense to have an event without a date")

    super(Event, self).__init__(
      title=title, desc=text,
      event_date=event_date, url=slug, parent=parent, **kwargs)
    self.is_fresh = is_fresh

  @classmethod
  def new(cls, title, text, slug, event_date=None, parent=None, **kwds):
    return cls(title=title, text=text, slug=slug, event_date=event_date,
               parent=parent, is_fresh=True, **kwds)

  @classmethod
  def get(cls, keys=None, slug=None, before=None,
          after=None, order=None, num=-1, page=False,
          cursor=None, one_key=False):
    if keys is not None:
      return super(Event, cls).get(keys=keys,
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
      query = query.filter(cls._RAW.url == slug)
    if after is not None:
      query = query.filter(cls._RAW.event_date >=
                           datetime.datetime.combine(after, datetime.time()))
    if before is not None:
      query = query.filter(cls._RAW.event_date <
                           datetime.datetime.combine(before, datetime.time()))

    if order is not None:
      query = query.order(*order)

    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  @classmethod
  def get_last(cls, num=3, keys_only=False, **kwargs):
    return super(Event, cls).get_last(num=num, keys_only=keys_only, **kwargs)

  @classmethod
  def get_upcoming(cls, num=3, keys_only=False):
    return cls.get_last(num=num, keys_only=keys_only, 
                        after=datetime.date.today(), before=datetime.date.max)

  @classmethod
  def get_by_slug(cls, slug, event_date=None):
    before = None
    after = None
    if event_date is not None:
      if isinstance(event_date, datetime.date):
        after = datetime.datetime.combine(
          event_date, datetime.time())
      else:
        after = datetime.datetime.combine(
          event_date.date(), datetime.time())
      before = after + datetime.timedelta(days=1)

    cached = cls._get_slug_cache(slug, after)
    if cached is not None:
      return cached
    dateless_cached = cls._get_slug_cache(slug)
    if dateless_cached is not None:
      if (dateless_cached.event_date >= before and
          dateless_cached.event_date < after):
        cls._add_slug_cache(dateless_cached.key, slug, after)
        return dateless_cached

    event = cls.get(slug=slug, before=before, after=after)
    if event is not None:
      # Add event to appropriate caches
      cls._add_slug_cache(event.key, slug, after)
      if dateless_cached is None:
        cls._add_slug_cache(event.key, slug)

      return event
    return None

  def put(self):
    super(Event, self).put()
    self.is_fresh = False

  @classmethod
  def _get_slug_cache(cls, slug, date=None, keys_only=False):
    return cls.get_by_index(cls.BY_SLUG, slug, date, keys_only=keys_only)
  @classmethod
  def _add_slug_cache(cls, key, slug, date=None):
    return cls.cache_set(key, cls.BY_SLUG, slug, date)

  def add_to_cache(self):
    super(Event, self).add_to_cache()

    # Add self to slug caches
    self._add_slug_cache(self.key, self.slug)
    self._add_slug_cache(self.key, self.slug,
                         datetime.datetime.combine(
                           self.event_date.date(), datetime.time()))

    try:
      if self.is_fresh:
        self.add_own_last_cache()
    except AttributeError:
      pass

  def purge_from_cache(self):
    super(Event, self).purge_from_cache()

    # Purge slug caches, if appropriate
    if self.key == self._get_slug_cache(self.slug,
                                        self.event_date_as_date,
                                        keys_only=True):
      self.cache_delete(self.BY_SLUG, self.slug, self.event_date_as_date)
    if self.key ==  self._get_slug_cache(self.slug, keys_only=True):
      self.cache_delete(self.BY_SLUG, self.slug, None)
    self.purge_from_last_cache(self.key)

  # Utility method so that a last-cacheable entry knows how to
  # lastcache itself.
  def add_own_last_cache(self):
    self.add_to_last_cache(self)
    self.add_to_last_cache(self, 
                           after=datetime.date.today(), 
                           before=datetime.date.max)
