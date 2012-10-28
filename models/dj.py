#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file contains the Dj model, and auxiliary functions.
#  A Dj object corresponds to a row in the Dj table in the datastore

from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key, as_keys, is_key

# Global python imports
import datetime
import random
import string
import logging

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

class Dj(CachedModel):
  COMPLETE = "dj_pref%s"
  ENTRY = "dj_key%s"

  # Minimum number of entries in the cache with which we would even consider
  # not rechecking the datastore. Figit with this number to balance reads and
  # autocomplete functionality. Possibly consider algorithmically determining
  # a score for artist names and prefixes?
  MIN_AC_CACHE = 10
  MIN_AC_RESULTS = 5

  USERNAME = "dj_username%s"
  EMAIL = "dj_email%s"

  # GAE Datastore properties
  fullname = db.StringProperty()
  lowername = db.StringProperty()
  email = db.StringProperty()
  username = db.StringProperty()
  password_hash = db.StringProperty()
  pw_reset_expire = db.DateTimeProperty()
  pw_reset_hash = db.StringProperty()

  @quantummethod
  def add_username_cache(obj, key=None, username=None):
    key = obj.key if key is None else key
    username = obj.p_username if username is None else username
    return obj.cache_set(key, obj.USERNAME, username)

  @classmethod
  def purge_username_cache(cls, username):
    cls.cache_delete(cls.USERNAME, username)

  def purge_own_username_cache(self):
    self.purge_username_cache(self.p_username)
    return self

  @classmethod
  def add_email_cache(cls, key, email):
    return cls.cache_set(key, cls.EMAIL, email)
  @classmethod
  def purge_email_cache(cls, email):
    cls.cache_delete(cls.EMAIL, email)

  def add_own_email_cache(self):
    self.add_email_cache(self.key, self.p_email)
    return self
  def purge_own_email_cache(self):
    self.purge_email_cache(self.p_email)
    return self

  def add_to_cache(self):
    super(Dj, self).add_to_cache()
    self.add_username_cache()
    self.add_own_email_cache()
    return self

  def purge_from_cache(self):
    super(Dj, self).purge_from_cache()
    self.purge_own_username_cache()
    self.purge_own_email_cache()
    return self

  @classmethod
  def get(cls, keys=None,
          username=None, email=None, order=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Dj, cls).get(keys,
                                use_datastore=use_datastore, one_key=one_key)

    keys = cls.get_key(username=username, email=email, order=order, num=num)
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def get_key(cls, username=None, email=None, program=None,
             order=None, num=-1):
    query = cls.all(keys_only=True)

    if username is not None:
      query.filter("username =", username)
    if email is not None:
      query.filter("email =", email)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  @classmethod
  def new(cls, email=None, fullname=None, username=None,
          password=None, fix_email=True):
    if None in (email, fullname, username, password):
      raise Exception("Insufficient fields for new Dj")

    dj = cls(fullname=fullname,
             lowername=fullname.lower(),
             email=fix_bare_email(email) if fix_email else email,
             username=username,
             password_hash=hash_password(password))

    return dj

  def put(self, fullname=None, username=None, email=None, password=None,
          fix_email=True):
    if fullname is not None:
      self.p_fullname = fullname
    if email is not None:
      self.p_email = email
    if username is not None: # Although this should be an immutable property
      self.p_username = username
    if password is not None:
      self.p_password = password

    # TODO: inject dj into autocompletion

    return super(Dj, self).put()

  def reset_password(self, put=True):
    reset_key = ''.join(random.choice(string.ascii_letters +
                                      string.digits) for x in range(20))

    self.pw_reset_expire=datetime.datetime.now() + datetime.timedelta(2)
    self.pw_reset_hash=hash_password(reset_key)

    if put:
      self.put()

    return reset_key

  @property
  def p_fullname(self):
    return self.fullname

  @property
  def p_lowername(self):
    return self.lowername

  @p_fullname.setter
  def p_fullname(self, fullname):
    self.fullname = fullname.strip()
    self.lowername = fullname.lower().strip()

  @property
  def p_username(self):
    return self.username

  @p_username.setter
  def p_username(self, username):
    username = username.strip()
    try:
      other = self.get_key_by_username(username)
      if as_key(other) != as_key(self.key):
        raise ModelError("There is already a Dj with this username", other)
    except NoSuchUsername:
      pass

    self.purge_own_username_cache()
    self.username = username

  @property
  def p_email(self):
    return self.email

  @p_email.setter
  def p_email(self, email):
    email = fix_bare_email(email.strip())
    try:
      other = self.get_key_by_email(email)
      if other is not None and other != self.key:
        print other
        raise ModelError("There is already a Dj with this email", other)
    except NoSuchEmail:
      pass

    self.purge_own_email_cache()
    self.email = email

  @property
  def p_password(self):
    return self.password_hash

  @p_password.setter
  def p_password(self, password):
    self.password_hash = hash_password(password)

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
        return dj.add_username_cache()
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
    return self.p_email == fix_bare_email(email)

  def password_matches(self, password):
    return check_password(self.p_password, password)

  @classmethod
  def login(cls, username, password):
    dj = cls.get_by_username(username)
    if dj is None:
      raise NoSuchUsername()

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

  @classmethod
  def has_prefix(cls, dj_key, prefix):
    prefixes = prefix.split()

    dj = cls.get(dj_key)

    for name_part in dj.lowername.split():
      check_prefixes = prefixes
      for prefix in check_prefixes:
        if name_part.startswith(prefix):
          prefixes.remove(prefix)
          if len(prefixes) == 0:
            return True
          break

    check_prefixes = prefixes
    for prefix in check_prefixes:
      if dj.email.startswith(prefix):
        prefixes.remove(prefix)
        if len(prefixes) == 0:
          return True
        break

    check_prefixes = prefixes
    for prefix in check_prefixes:
      if dj.username.startswith(prefix):
        prefixes.remove(prefix)
        if len(prefixes) == 0:
          return True
        break

    return False

  # As it is now, autocomplete is a little wonky. One thing worth
  # noting is that we search cache a bit more effectively than the
  # datastore: for example, if you've got a cached prefix "b" and
  # bear in heaven was there, then you're able to just search "b i
  # h" and cut out other stragglers like "Best Band Ever". Right
  # now, we can't search datastore this efficiently, so this is kind
  # of hit or miss.
  @classmethod
  def autocomplete(cls, prefix):
    prefix = prefix.lower().strip()
    # First, see if we have anything already cached for us in memstore.
    # We start with the most specific prefix, and widen our search
    cache_prefix = prefix
    cached_results = None
    perfect_hit = True
    while cached_results is None:
      if len(cache_prefix) > 0:
        cached_results = cls.cache_get(cls.COMPLETE %cache_prefix)
        if cached_results is None:
          cache_prefix = cache_prefix[:-1]
          perfect_hit = False
      else:
        cached_results = {"recache_count": -1,
                          "max_results": False,
                          "djs": None,}

    # If we have a sufficient number of cached results OR we
    #    have all possible results, search in 'em.
    logging.debug(cache_prefix)
    logging.debug(cached_results)
    logging.debug(perfect_hit)
    if (cached_results["recache_count"] >= 0 and
        (cached_results["max_results"] or
         len(cached_results["djs"]) >= cls.MIN_AC_CACHE)):
      logging.debug("Trying to use cached results")

      cache_djs = sorted(cached_results["djs"],
                             key=lambda x: cls.get(x).lowername)

      # If the cache is perfect (exact match!), just return it
      if perfect_hit:
        # There is no need to update the cache in this case.
        logging.debug(cache_djs)
        return cls.get(cache_djs)

      # Otherwise we're going to have to search in the cache.
      results = filter(lambda a: cls.has_prefix(a, prefix),
                       cache_djs)
      if cached_results["max_results"]:
        # We're as perfect as we can be, so cache the results
        cached_results["recache_count"] += 1
        cached_results["djs"] = results
        cls.cache_set(cached_results, cls.COMPLETE, prefix)
        return cls.get(results)
      elif len(results) > cls.MIN_AC_RESULTS:
        if len(results) > cls.MIN_AC_CACHE:
          cached_results["recache_count"] += 1
          cached_results["djs"] = results
          cls.cache_set(cached_results, cls.COMPLETE, prefix)
          return cls.get(results)
        return cls.get(results)

    djs_by_full = (cls.all(keys_only=True)
                    .filter("lowername >=", prefix)
                    .filter("lowername <", prefix + u"\ufffd").fetch(10))
    djs_by_email = (cls.all(keys_only=True)
                  .filter("email >=", prefix)
                  .filter("email <", prefix + u"\ufffd").fetch(10))
    djs_by_username = (cls.all(keys_only=True)
                       .filter("username >=", prefix)
                       .filter("username <", prefix + u"\ufffd").fetch(10))

    max_results = (len(djs_by_full) < 10 and
                   len(djs_by_email) < 10 and
                   len(djs_by_username) < 10)

    djs = Dj.get(list(set(djs_by_full + djs_by_email + djs_by_username)))
    djs = sorted(djs, key=lambda x: x.lowername)

    results_dict = {"recache_count": 0,
                    "max_results": max_results,
                    "djs": [dj.key for dj in djs]}

    cls.cache_set(results_dict, cls.COMPLETE, prefix)
    return djs



class Permission(CachedModel):
  ENTRY = "permission_key%s"

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
  title = db.StringProperty()
  dj_list = db.ListProperty(db.Key)

  def __init__(self, parent=None, key_name=None, **kwds):
    super(Permission, self).__init__(parent=parent, key_name=key_name, **kwds)

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
    query = cls.all(keys_only=True)

    if title is not None:
      query.filter("title =", title)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  def put(self, dj_list=None):
    if dj_list is not None:
      self.dj_list = dj_list

    return super(Permission, self).put()

  def add_dj(self, djs):
    if is_key(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.dj_list = list(set(self.dj_list).
                        union(as_keys(djs)))

  def remove_dj(self, djs):
    if is_key(djs) or isinstance(djs, Dj):
      djs = (djs,)

    self.dj_list = list(set(self.dj_list).
                        difference(as_keys(djs)))

  def has_dj(self, dj):
    return dj is not None and as_key(dj) in self.dj_list

  @property
  def p_title(self):
    return self.title

  @classmethod
  def get_all(cls, keys_only=False):
    allcache = cls.get_by_index(cls.ALL, keys_only=keys_only)
    if allcache:
      return allcache

    if keys_only:
      return cls.set_all_cache(cls.get_key(order="title", num=1000))
    return cls.get(keys=cls.set_all_cache(cls.get_key(order="title", num=1000)))

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
