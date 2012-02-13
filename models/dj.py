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

# Global python imports
import datetime
import random

def fixBareEmail(email):
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

  @classmethod
  def addUsernameCache(cls, key, username):
    return cls.cacheSet(key, cls.USERNAME, username)
  @classmethod
  def purgeUsernameCache(cls, username):
    cls.cacheDelete(cls.USERNAME, username)

  def addOwnUsernameCache(self):
    self.addUsernameCache(self.key(), self.p_username)
    return self
  def purgeOwnUsernameCache(self):
    self.purgeUsernameCache(self.p_username)
    return self

  @classmethod
  def addEmailCache(cls, key, email):
    return cls.cacheSet(key, cls.EMAIL, email)
  @classmethod
  def purgeEmailCache(cls, email):
    cls.cacheDelete(cls.EMAIL, email)

  def addOwnEmailCache(self):
    self.addEmailCache(self.key(), self.p_email)
    return self
  def purgeOwnEmailCache(self):
    self.purgeEmailCache(self.p_email)
    return self

  def addToCache(self):
    super(Dj, self).addToCache()
    self.addOwnUsernameCache()
    self.addOwnEmailCache()
    return self

  def purgeFromCache(self):
    super(Dj, self).purgeFromCache()
    self.purgeOwnUsernameCache()
    self.purgeOwnEmailCache()
    return self

  @classmethod
  def get(cls, keys=None,
          username=None, email=None, order=None,
          num=-1, use_datastore=True, one_key=False):
    if keys is not None:
      return super(Dj, cls).get(keys, 
                                use_datastore=use_datastore, one_key=one_key)

    keys = cls.getKey(username=username, email=email, order=order, num=num)  
    if keys is not None:
      return cls.get(keys=keys, use_datastore=use_datastore)
    return None

  @classmethod
  def getKey(cls, username=None, email=None, program=None, 
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
             email=fixBareEmail(email) if fix_email else email,
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

  def resetPassword(self, put=True):
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
  
  @p_fullname.setter
  def p_username(self, username):
    username = username.strip()
    other = self.getKeyByUsername(username)
    if other is not None and other_dj != self.key():
      raise ModelError("There is already a Dj with this username", other)
    else:
      self.purgeOwnUsernameCache()
      self.username = username

  @property
  def p_email(self):
    return self.email

  @p_email.setter
  def p_email(self, email):
    email = fixBareEmail(email.strip())
    other = self.getKeyByEmail(email)
    print other, self.key()
    if other is not None and other != self.key():
      raise ModelError("There is already a Dj with this email", other)
    else:
      self.purgeOwnEmailCache()
      self.email = email

  @property
  def p_password(self):
    return self.pasword_hash

  @p_password.setter
  def p_password(self, password):
    self.password_hash = hash_password(password)

  # TODO: instead use paging and cursors (is that what they're called)
  # to return part of all the Djs (in case there end up being more than 1000!)
  @classmethod
  def getAll(cls):
    return cls.get(order="fullname", num=1000)

  @classmethod
  def getByUsername(cls, username, keys_only=False):
    cached = cls.getByIndex(cls.USERNAME, username, keys_only=keys_only)
    if cached is not None:
      return cached

    key = cls.getKey(email=email)
    if key is not None:
      if keys_only:
        return cls.addUsernameCache(key, username)
      dj = cls.get(key)
      if dj is not None:
        return dj.addOwnUsernameCache()
    raise NoSuchUsernameError()

  @classmethod
  def getKeyByUsername(cls, username):
    return cls.getByUsername(username, keys_only=True)

  @classmethod
  def getByEmail(cls, email, keys_only=False):
    email = fixBareEmail(email)
    cached = cls.getByIndex(cls.EMAIL, email, keys_only=keys_only)
    if cached is not None:
      return cached

    key = cls.getKey(email=email)
    if key is not None:
      if keys_only:
        return cls.addEmailCache(key, email)
      dj = cls.get(key)
      if dj is not None:
        return dj.addOwnEmailCache()
    raise NoSuchEmailError()

  @classmethod
  def getKeyByEmail(cls, email):
    return cls.getByEmail(email=email, keys_only=True)

  def emailMatches(self, email):
    return self.p_email == fixBareEmail(email)

  def passwordMatches(self, password):
    return check_password(self.p_password, password)

  @classmethod
  def login(cls, username, password):
    dj = cls.getByUsername(username)
    if dj is None:
      raise NoSuchUsernameError()

    if not dj.passwordMatches(password):
      raise InvalidLoginError()
    
    return dj

  @classmethod
  def recoveryLogin(cls, username, reset_key):
    dj = cls.getByUsername(username)
    if dj is None:
      raise NoSuchUserError()

    if (dj.pw_reset_expire is None or
        dj.pw_reset_hash is None or
        datetime.datetime.now() > dj.pw_reset_expire):
      raise InvalidLoginError()

    elif check_password(dj.pw_reset_hash, reset_key):
      dj.pw_reset_expire = datetime.datetime.now()
      dj.reset_hash = None
      dj.put()
      return dj
