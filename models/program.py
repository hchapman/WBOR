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

class Program(CachedModel):
  title = db.StringProperty()
  slug = db.StringProperty()
  desc = db.StringProperty(multiline=True)
  dj_list = db.ListProperty(db.Key)
  page_html = db.TextProperty()
  top_artists = db.StringListProperty()
  top_playcounts = db.ListProperty(int)
  current = db.BooleanProperty(default=False)

  def to_json(self):
    return {
      'key': str_or_none(self.key()),
      'title': self.title,
      'slug': self.slug,
      'desc': self.desc,
      'dj_list': [str_or_none(dj_key) for dj_key in self.dj_list],
      'page_html': self.page_html,
      'top_artists': self.top_artists,
      'top_playcounts': self.top_playcounts,
      'current': self.current
    }