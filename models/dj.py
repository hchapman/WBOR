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
from base_models import (CachedModel, QueryError, ModelError)
from base_models import quantummethod, as_key

# Global python imports
import datetime
import random
import string

def fix_bare_email(email):
  if email[-1] == "@":
    return email + "bowdoin.edu"
  if "@" not in email:
    return email + "@bowdoin.edu"
  return email

class NoSuchUsernameError(QueryError):
  pass
class NoSuchEmailError(QueryError):
  pass

class InvalidLoginError(ModelError):
  pass

class Dj(CachedModel):
  ENTRY = "dj_key%s"

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

  def __init__(self, parent=None, key_name=None, cached=True, **kwargs):
    super(Dj, self).__init__(parent=parent, 
                             key_name=key_name, cached=cached, **kwargs)

  @quantummethod
  def add_username_cache(obj, inst, key=None, username=None):
    if inst:
      key = obj.key()
      username = obj.p_username
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
    self.add_email_cache(self.key(), self.p_email)
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
      if as_key(other) != as_key(self.key()):
        raise ModelError("There is already a Dj with this username", other)
    except NoSuchUsernameError:
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
      if other is not None and other != self.key():
        print other
        raise ModelError("There is already a Dj with this email", other)
    except NoSuchEmailError:
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
    raise NoSuchUsernameError()

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
    raise NoSuchEmailError()

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
      raise NoSuchUsernameError()

    if not dj.password_matches(password):
      raise InvalidLoginError()
    
    return dj

  @classmethod
  def recovery_login(cls, username, reset_key):
    dj = cls.get_by_username(username)
    if dj is None:
      raise NoSuchUsernameError()

    if (dj.pw_reset_expire is None or
        dj.pw_reset_hash is None or
        datetime.datetime.now() > dj.pw_reset_expire):
      raise InvalidLoginError()

    elif check_password(dj.pw_reset_hash, reset_key):
      dj.pw_reset_expire = datetime.datetime.now()
      dj.reset_hash = None
      dj.put()
      return dj
