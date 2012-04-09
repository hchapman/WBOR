from __future__ import with_statement

# GAE Imports
from google.appengine.ext import db

# Local module imports
from passwd_crypto import hash_password, check_password
from base_models import (CachedModel, QueryError, ModelError, NoSuchEntry)
from base_models import quantummethod, as_key

# Global python imports
import datetime
import random
import string


class BlogPost(db.Model):
  title = db.StringProperty()
  text = db.TextProperty()
  post_date = db.DateTimeProperty()
  slug = db.StringProperty()

class Event(db.Model):
  title = db.StringProperty()
  event_date = db.DateTimeProperty()
  desc = db.TextProperty()
  url = db.StringProperty()