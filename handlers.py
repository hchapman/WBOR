import logging

# Google App Engine imports
from google.appengine.ext import db

# Webapp2 imports
import webapp2
from webapp2_extras import sessions

class BaseHandler(webapp2.RequestHandler):
  """Enables session management"""
  def dispatch(self):
    self.session_store = sessions.get_store(request = self.request)
    
    try:
      webapp2.RequestHandler.dispatch(self)
    finally:
      self.session_store.save_sessions(self.response)

  @webapp2.cached_property
  def session(self):
    return self.session_store.get_session()

class UserHandler(BaseHandler):
  """Handler facilitating a currently logged in user (i.e. a DJ) and their programs, etc.
  """
  def set_session_user(self, dj):
    """Takes a Dj model, and stores values into the session"""
    self.session['dj'] = {
        'key' : str(dj.key()),
        'fullname' : dj.fullname,
        'lowername' : dj.lowername,
        'email' : dj.email,
        }
  
  def set_session_program(self, pgm):
    """Takes a Program model, and stores values to the session"""
    self.session['program'] = {
        'key' : str(pgm.key()),
        'slug' : pgm.slug,
        'title' : pgm.title,
        }

  def session_logout(self):
    """Logs the dj out, deleting program and dj keys in the session"""
    for key in ('dj', 'program'):
      if key in self.session:
        del self.session[key]

  def session_has_login(self):
    return self.session.has_key('dj')

  def session_has_program(self):
    return self.session.has_key('program')

  @property
  def flash(self):
    return self.session.get_flashes()

  @property
  def dj_key(self):
    key = self.session.get('dj').get('key')
    if key is not None:
      return db.Key(key)
    return None

  @property
  def program_key(self):
    key = self.session.get('program').get('key')
    if key is not None:
      return db.Key(key)
    return None
