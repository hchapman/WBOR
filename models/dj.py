#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Dj model, and auxiliary functions.
#  A Dj object corresponds to a row in the Dj table in the datastore

from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db, ndb

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key, as_keys, is_key
from base_models import SetQueryCache, accepts_raw

from _raw_models import Dj as RawDj
from _raw_models import DjRegistrationToken as RawToken
from _raw_models import Permission as RawPermission

from autocomplete import *
from cache_models import Searchable, NewCacheable

# Global python imports
import datetime
import random
import string
import logging

from itertools import chain

def fix_bare_email(email):
  if email[-1] == "@":
    return email + "bowdoin.edu"
  if "@" not in email:
    return email + "@bowdoin.edu"
  return email

class NoSuchUsername(NoSuchEntry):
  pass
class NoSuchEmail(NoSuchEntry):
  pass

class NoSuchTitle(NoSuchEntry):
  pass

class InvalidLogin(ModelError):
  pass

@accepts_raw
class Dj(Searchable, NewCacheable):
  _RAW = RawDj
  _RAWKIND = "Dj"

  COMPLETE = "@dj_pref%s"
  NEW = "dj_newest"

  # Minimum number of entries in the cache with which we would even consider
  # not rechecking the datastore. Figit with this number to balance reads and
  # autocomplete functionality. Possibly consider algorithmically determining
  # a score for artist names and prefixes?
  AC_FETCH_NUM = 10
  MIN_AC_CACHE = 10
  MIN_AC_RESULTS = 5

  USERNAME = "dj_username%s"
  EMAIL = "dj_email%s"

  @property
  def _autocomplete_fields(self):
    for name_part in self.lowername.split():
      yield name_part
    for email_part in self.email.split("@"):
      yield email_part
    yield self.username

  @classmethod
  def _autocomplete_queries(cls, prefix):
    yield (cls._autocomplete_query(cls._RAW.username, prefix), "user")
    yield (cls._autocomplete_query(cls._RAW.lowername, prefix), "lower")
    yield (cls._autocomplete_query(cls._RAW.email, prefix), "email")

  @quantummethod
  def add_username_cache(obj, key=None, username=None):
    key = obj.key if key is None else key
    username = obj.username if username is None else username
    return obj.cache_set(key, obj.USERNAME, username)

  @classmethod
  def purge_username_cache(cls, username):
    cls.cache_delete(cls.USERNAME, username)

  def purge_own_username_cache(self):
    self.purge_username_cache(self.username)
    return self

  @classmethod
  def add_email_cache(cls, key, email):
    return cls.cache_set(key, cls.EMAIL, email)
  @classmethod
  def purge_email_cache(cls, email):
    cls.cache_delete(cls.EMAIL, email)

  def add_own_email_cache(self):
    self.add_email_cache(self.key, self.email)
    return self
  def purge_own_email_cache(self):
    self.purge_email_cache(self.email)
    return self

  @quantummethod
  def add_autocomplete_cache(obj, key=None,
                             username=None, email=None, lowername=None):
    key = obj.key if key is None else key
    username = obj.username if username is None else username
    email = obj.email if email is None else email
    lowername = obj.lowername if lowername is None else lowername

    if not key: return
    lower_prefixes = set(prefixize(lowername, " ")) if lowername else set()
    user_prefixes = set(prefixize(username)) if username else set()
    email_prefixes = set(prefixize(email, " ")) if email else set()

    add_to_autocomplete_caches(
      key, obj.COMPLETE,
      lower_prefixes | user_prefixes | email_prefixes)

  def update_autocomplete_cache(self):
    lower_prefixes = set(
      prefixize(self.lowername, " ")) if self.lowername else set()
    old_lower_prefixes = set(
      prefixize(self.old_lowername, " ")) if self.old_lowername else set()
    user_prefixes = set(
      prefixize(self.username)) if self.username else set()
    old_user_prefixes = set(
      prefixize(self.old_username)) if self.old_username else set()
    email_prefixes = set(
      prefixize(self.email, " ")) if self.email else set()
    old_email_prefixes = set(
      prefixize(self.old_email, " ")) if self.old_email else set()

    old_prefixes = (old_lower_prefixes |
                    old_email_prefixes |
                    old_user_prefixes)
    new_prefixes = (lower_prefixes |
                    user_prefixes |
                    email_prefixes)
    add_prefixes = (new_prefixes - old_prefixes)
    purge_prefixes = (old_prefixes - new_prefixes)

    purge_from_autocomplete_caches(
      self.key, self.COMPLETE, purge_prefixes)
    add_to_autocomplete_caches(
      self.key, self.COMPLETE, add_prefixes)


  @quantummethod
  def purge_autocomplete_cache(obj, key=None,
                             username=None, email=None, lowername=None):
    key = obj.key if key is None else key
    username = obj.username if username is None else username
    email = obj.email if email is None else email
    lowername = obj.lowername if lowername is None else lowername

    if not key: return
    lower_prefixes = set(prefixize(lowername, " ")) if lowername else set()
    user_prefixes = set(prefixize(username)) if username else set()
    email_prefixes = set(prefixize(email, " ")) if email else set()

    purge_from_autocomplete_caches(
      key, obj.COMPLETE,
      lower_prefixes | user_prefixes | email_prefixes)


  def add_to_cache(self):
    super(Dj, self).add_to_cache()
    self.add_username_cache()
    self.add_own_email_cache()
    self.add_autocomplete_cache()
    self.add_to_new_cache(self.key)
    return self

  def purge_from_cache(self):
    super(Dj, self).purge_from_cache()
    self.purge_own_username_cache()
    self.purge_own_email_cache()
    self.purge_autocomplete_cache()
    self.purge_from_new_cache(self.key)
    return self

  @classmethod
  def get(cls, keys=None,
          page=False, cursor=None,
          use_datastore=True, one_key=False, **kwargs):
    if keys is not None:
      try:
        return super(Dj, cls).get(keys,
                                  use_datastore=use_datastore,
                                  one_key=one_key)
      except ModelError:
        return None
      

    return cls._get_helper(page=page, cursor=cursor, **kwargs)

  @classmethod
  def get_key(cls, username=None, email=None, program=None,
             order=None, num=-1, page=False, cursor=None):
    query = RawDj.query()

    if username is not None:
      query = query.filter(RawDj.username == username)
    if email is not None:
      query = query.filter(RawDj.email == email)

    if order is not None:
      query = query.order(order)

    # Consider adding query caching here, if necessary
    if num == -1:
      return query.get(keys_only=True, start_cursor=cursor)
    elif not page:
      return query.fetch(num, keys_only=True, start_cursor=cursor)
    else:
      return query.fetch_page(num, keys_only=True, start_cursor=cursor)

  def __init__(self,
               email=None, fullname=None, username=None,
               password=None, fix_email=True, **kwargs):
    if None in (email, fullname, username, password):
      raise ModelError("Insufficient fields for new Dj")

    super(Dj, self).__init__(fullname=fullname,
                             email=(fix_bare_email(email) if fix_email
                                    else email),
                             username=username,
                             password_hash=hash_password(password), **kwargs)

  @classmethod
  def new(cls, email, fullname, username, password, fix_email=True):
    return cls(email=email, fullname=fullname, username=username,
               password=password, fix_email=fix_email, _new=True)

  @ndb.transactional(xg=True)
  def put(self, token=None):
    # TODO: inject dj into autocompletion
    self.update_autocomplete_cache()

    key = super(Dj, self).put()
    if token:
      token.use_token()
      token.put()
    elif token is not None and not token:
      raise ModelError("Trying to put new DJ with invalid registration token")

    return key

  def reset_password(self, put=True):
    reset_key = ''.join(random.choice(string.ascii_letters +
                                      string.digits) for x in range(20))

    self.pw_reset_expire=datetime.datetime.now() + datetime.timedelta(2)
    self.pw_reset_hash=hash_password(reset_key)

    if put:
      self.put()

    return reset_key

  @property
  def fullname(self):
    return self.raw.fullname
  @property
  def lowername(self):
    return self.raw.lowername
  @fullname.setter
  def fullname(self, fullname):
    self._old_lowername = self.raw.lowername
    self.raw.fullname = fullname.strip()

  @property
  def username(self):
    return self.raw.username
  @username.setter
  def username(self, username):
    username = username.strip()
    try:
      other = self.get_key_by_username(username)
      logging.error(username)
      logging.error(other)
      if other is not None and as_key(other) != as_key(self.key):
        raise ModelError("There is already a Dj with this username", other)
    except NoSuchUsername:
      pass

    self.purge_own_username_cache()
    self._old_username = self.raw.username
    self.raw.username = username

  @property
  def email(self):
    return self.raw.email
  @email.setter
  def email(self, email):
    email = fix_bare_email(email.strip())
    try:
      other = self.get_key_by_email(email)
      if other is not None and other != self.key:
        raise ModelError("There is already a Dj with this email", other)
    except NoSuchEmail:
      pass

    self.purge_own_email_cache()
    self._old_email = self.raw.email
    self.raw.email = email

  @property
  def password(self):
    return self.raw.password_hash
  @password.setter
  def password(self, password):
    self.raw.password_hash = hash_password(password)

  @property
  def old_lowername(self):
    try:
      return self._old_lowername
    except AttributeError:
      return self.lowername
  @property
  def old_username(self):
    try:
      return self._old_username
    except AttributeError:
      return self.username
  @property
  def old_email(self):
    try:
      return self._old_email
    except AttributeError:
      return self.email

  def to_json(self):
    return {
      'key': str_or_none(self.key),
      'name': self.name,
      'email': self.email,
      'username': self.username,
    }


  # TODO: instead use paging and cursors (is that what they're called)
  # to return part of all the Djs (in case there end up being more than 1000!)
  @classmethod
  def get_all(cls):
    return cls.get(order="fullname", num=1000)

  @classmethod
  def get_by_username(cls, username, keys_only=False):
    cached = cls.get_by_index(cls.USERNAME, username, keys_only=keys_only)
    if cached is not None:
      return cached

    key = cls.get_key(username=username)
    if key is not None:
      if keys_only:
        return cls.add_username_cache(key, username)
      dj = cls.get(key)
      if dj is not None:
        dj.add_username_cache()
        return dj
    raise NoSuchUsername()

  @classmethod
  def get_key_by_username(cls, username):
    return cls.get_by_username(username, keys_only=True)

  @classmethod
  def get_by_email(cls, email, keys_only=False):
    email = fix_bare_email(email)
    cached = cls.get_by_index(cls.EMAIL, email, keys_only=keys_only)
    if cached is not None:
      return cached

    key = cls.get_key(email=email)
    if key is not None:
      if keys_only:
        return cls.add_email_cache(key, email)
      dj = cls.get(key)
      if dj is not None:
        return dj.add_own_email_cache()
    raise NoSuchEmail()

  @classmethod
  def get_key_by_email(cls, email):
    return cls.get_by_email(email=email, keys_only=True)

  def email_matches(self, email):
    return self.email == fix_bare_email(email)

  def password_matches(self, password):
    return check_password(self.password, password)

  @classmethod
  def login(cls, username, password):
    dj = cls.get_by_username(username)
    if dj is None:
      raise NoSuchUsername()

    logging.error("dj is %s"%dj)
    if not dj.password_matches(password):
      raise InvalidLogin()

    return dj

  @classmethod
  def recovery_login(cls, username, reset_key):
    dj = cls.get_by_username(username)
    if dj is None:
      raise NoSuchUsername()

    if (dj.pw_reset_expire is None or
        dj.pw_reset_hash is None or
        datetime.datetime.now() > dj.pw_reset_expire):
      raise InvalidLogin()

    elif check_password(dj.pw_reset_hash, reset_key):
      dj.pw_reset_expire = datetime.datetime.now()
      dj.reset_hash = None
      dj.put()
      return dj


class Permission(CachedModel):
  _RAW = RawPermission
  _RAWKIND = "Permission"

  # Other memcache key constants
  TITLE = "permission_title%s"
  ALL = "all_permissions_cache"

  DJ_EDIT = "Manage DJs"
  PROGRAM_EDIT = "Manage Programs"
  PERMISSION_EDIT = "Manage Permissions"
  ALBUM_EDIT = "Manage Albums"
  GENRE_EDIT = "Manage Genres"
  BLOG_EDIT = "Manage Blog"
  EVENT_EDIT = "Manage Events"

  PERMISSIONS = (DJ_EDIT,
                 PROGRAM_EDIT,
                 PERMISSION_EDIT,
                 ALBUM_EDIT,
                 GENRE_EDIT,
                 BLOG_EDIT,
                 EVENT_EDIT,)

  # GAE Datastore properties

  def __init__(self, raw=None, raw_key=None,
               title=None, dj_list=None,
               parent=None, **kwds):
    if raw is not None:
      super(Permission, self).__init__(raw=raw)
      return
    elif raw_key is not None:
      super(Permission, self).__init__(raw_key=raw_key)
      return

    if dj_list is None: dj_list = []
    super(Permission, self).__init__(title=title, dj_list=dj_list,
                                     parent=parent, **kwds)

  @classmethod
  def new(cls, title, dj_list=None, parent=None, **kwargs):
    return cls(title=title, dj_list=dj_list, parent=parent, **kwargs)

  @classmethod
  def add_title_cache(cls, key, title):
    return cls.cache_set(key, cls.TITLE, title)
  @classmethod
  def purge_title_cache(cls, title):
    return cls.cache_delete(cls.TITLE, title)

  def add_own_title_cache(self):
    self.add_title_cache(self.key, self.title)
    return self
  def purge_own_title_cache(self):
    self.purge_title_cache(self.title)

  @classmethod
  def set_all_cache(cls, key_set):
    return cls.cache_set(set([as_key(key) for key in key_set]), cls.ALL)
  @classmethod
  def add_all_cache(cls, key):
    allcache = cls.cache_get(cls.ALL)
    if not allcache:
      cls.cache_set((key,), cls.ALL)
    else:
      cls.cache_set(set(allcache).add(key))
    return key
  @classmethod
  def purge_all_cache(cls, key):
    allcache = cls.cache_get(cls.ALL)
    if allcache:
      try:
        cls.cache_set(set(allcache).remove(key))
      except KeyError:
        pass
    return key

  def add_own_all_cache(self):
    self.add_all_cache(self.key)
    return self
  def purge_own_all_cache(self):
    self.purge_all_cache(self.key)
    return self

  def add_to_cache(self):
    super(Permission, self).add_to_cache()
    self.add_own_title_cache()
    return self

  def purge_from_cache(self):
    super(Permission, self).purge_from_cache()
    self.purge_own_title_cache()
    return self

  @classmethod
  def get(cls, keys=None,
          title=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Permission, cls).get(keys, use_datastore=use_datastore,
                                        one_key=one_key)

    keys = cls.get_key(title=title, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, title=None,
             order=None, num=-1):
    query = cls._RAW.query()

    if title is not None:
      query = query.filter(cls._RAW.title == title)

    if order is not None:
      query = query.order(order)

    if num == -1:
      return query.get(keys_only=True)
    return query.fetch(num, keys_only=True)

  def put(self, dj_list=None):
    if dj_list is not None:
      self.dj_list = dj_list

    return super(Permission, self).put()

  def add_dj(self, djs):
    if is_key(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.raw.dj_list = list(set(self.dj_list).
                            union(as_keys(djs)))

  def remove_dj(self, djs):
    if is_key(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.raw.dj_list = list(set(self.dj_list).
                        difference(as_keys(djs)))

  def has_dj(self, dj):
    return dj is not None and as_key(dj) in self.dj_list

  @property
  def title(self):
    return self.raw.title
  @property
  def dj_list(self):
    return self.raw.dj_list

  @classmethod
  def get_all(cls, keys_only=False):
    allcache = cls.get_by_index(cls.ALL, keys_only=keys_only)
    if allcache:
      return allcache

    if keys_only:
      return cls.set_all_cache(cls.get_key(
        order=RawPermission.title, num=1000))
    return cls.get(keys=cls.set_all_cache(
      cls.get_key(order=RawPermission.title, num=1000)))

  @classmethod
  def get_by_title(cls, title, keys_only=False):
    cached = cls.get_by_index(cls.TITLE, title, keys_only=keys_only)
    if cached is not None:
      return cached

    key = cls.get_key(title=title)
    if key is not None:
      if keys_only:
        return cls.add_title_cache(key, title)
      permission = cls.get(key)
      if permission is not None:
        return permission.add_own_title_cache()
    raise NoSuchTitle()

  @classmethod
  def get_key_by_title(cls, title):
    return cls.get_by_title(title=title, keys_only=True)

@accepts_raw
class DjRegistrationToken(CachedModel):
  _RAW = RawToken
  _RAWKIND = "DjRegistrationToken"

  @property
  def token(self):
    return self.id
  @property
  def uses(self):
    return self.raw.uses

  def use_token(self):
    if self.raw.uses > 0:
      self.raw.uses -= 1
    else:
      self.raw.uses = 0

  def __init__(self, token=None, uses=1, **kwargs):
    if not token:
      raise ModelError("Token must exist and be nontrivial")

    super(DjRegistrationToken, self).__init__(
      id=token, uses=uses, **kwargs)

  @classmethod
  def new(cls, token=None, uses=1):
    if not token:
      token = '%030x' % random.randrange(256**15)
    return DjRegistrationToken(token=token, uses=uses)

  @classmethod
  def get(cls, token_str):
    return DjRegistrationToken(raw_key=ndb.Key(cls._RAWKIND, token_str))

  def is_valid(self):
    return (self.raw is not None and
            self.uses > 0)

  def __nonzero__(self):
    return self.is_valid()