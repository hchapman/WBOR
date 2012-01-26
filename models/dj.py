#!/usr/bin/env python
#
# Author: Harrison Chapman
# This file will hold parent classes of types of models

from __future__ import with_statement

# GAE Imports
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext import blobstore
from google.appengine.api import files

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import CachedModel

# Global python imports
import logging
import datetime
import logging
import itertools

def fixBareEmail(email):
  if email[-1] == "@":
    return email + "bowdoin.edu"
  if "@" not in email:
    return email + "@bowdoin.edu"
  return email

class Dj(CachedModel):
  ENTRY = "dj_key%s"

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
      return cls.cacheGet(keys, models.Dj, ENTRY, 
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
          password=None, fix_email=True):
    if None in (email, fullname, username, password):
      raise Exception("Insufficient fields for new Dj")

    dj = cls(fullname=fullname, 
             lowername=fullname.lower(),
             email=fixBareEmail(email) if fix_email else email,
             username=username, 
             password_hash=hash_password(password))
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
