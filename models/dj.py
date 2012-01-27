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
from base_models import *

# Global python imports
import logging
import datetime
import logging
import itertools
import random

def fixBareEmail(email):
  if email[-1] == "@":
    return email + "bowdoin.edu"
  if "@" not in email:
    return email + "@bowdoin.edu"
  return email

class NoSuchUserException(Exception):
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

  def __init__(self, parent=None, key_name=None, **kwds):
    super(Dj, self).__init__(parent=parent, key_name=key_name, **kwds)

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
      query.filter("email =", username)

    if order is not None:
      query.order(order)

    if num == -1:
      return query.get()
    return query.fetch(num)

  @classmethod
  def new(cls, email=None, fullname=None, username=None, 
          password=None, fix_email=True, put=True):
    if None in (email, fullname, username, password):
      raise Exception("Insufficient fields for new Dj")

    dj = cls(fullname=fullname, 
             lowername=fullname.lower(),
             email=fixBareEmail(email) if fix_email else email,
             username=username, 
             password_hash=hash_password(password))
    if put:
      dj.put()
    return dj

  def put(self, email=None, fullname=None, username=None, 
          password=None, fix_email=True):
    if fullname is not None:
      self.fullname = fullname
      self.lowername = fullname.lower()
    if email is not None:
      self.email = fixBareEmail(email) if fix_email else email
    if username is not None: # Although this should be an immutable property
      self.username = username
    if password is not None:
      self.password_hash = hash_password(password)

    super(Dj, self).put()

  def resetPassword(self, put=True):
    reset_key = ''.join(random.choice(string.ascii_letters +
                                      string.digits) for x in range(20))
 
    self.pw_reset_expire=datetime.datetime.now() + datetime.timedelta(2)
    self.pw_reset_hash=hash_password(reset_key)

    if put:
      self.put()
    
    return reset_key

  @classmethod
  def getAll(cls):
    return cls.get(order="fullname", num=1000)

  @classmethod
  def getByUsername(cls, username):
    cached = cls.cacheGet(cls.USERNAME, username)
    if cached is not None:
      return cached

    return cls.cacheSet(cls.USERNAME, cls.get(username=username))

  @classmethod
  def getByEmail(cls, email):
    return cls.get(email=email)

  @classmethod
  def getByUsernameCheckEmail(cls, username, email):
    dj = cls.get(username=username)
    if dj is None:
      raise NoSuchUserException("There is no user by that username.")
    if fixBareEmail(email).strip() != dj.email.strip():
      raise NoSuchUserException("Email address is inconsistent.")

    return dj

  @classmethod
  def login(cls, username, password):
    dj = cls.getByUsername(username)
    if dj is not None and check_password(dj.password_hash, password):
      return dj
    return None
