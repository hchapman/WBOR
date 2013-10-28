import logging

# Google App Engine imports
from google.appengine.ext import ndb

from models import Permission, Dj, Program

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
      logging.debug(self.session)
      self.session_store.save_sessions(self.response)

  @webapp2.cached_property
  def session(self):
    return self.session_store.get_session()

  @property
  def flash(self):
    flashes = self.session.get_flashes()
    if flashes:
      return flashes[0]

  @property
  def flashes(self):
    return self.session.get_flashes()

  @flash.setter
  def flash(self, value):
    self.session.add_flash(value)

class UserHandler(BaseHandler):
  """Handler facilitating a currently logged in user (i.e. a DJ) and
  their programs, etc.
  """
  def set_session_user(self, dj):
    """Takes a Dj model, and stores values into the session"""
    djkey = dj.key

    permissions = {
      'djs': Permission.DJ_EDIT,
      'programs': Permission.PROGRAM_EDIT,
      'albums': Permission.ALBUM_EDIT,
      'permissions': Permission.PERMISSION_EDIT,
      'genres': Permission.GENRE_EDIT,
      'blogs': Permission.BLOG_EDIT,
      'events': Permission.EVENT_EDIT,}
    permissions = dict((key,
                        Permission.get_by_title(perm).has_dj(djkey)) for
                       (key, perm) in permissions.iteritems())

    if not reduce(lambda x,y: x or y, permissions.values()):
      permissions = None
    self.session['dj'] = {
        'key' : dj.key.urlsafe(),
        'fullname' : dj.fullname,
        'lowername' : dj.lowername,
        'username': dj.username,
        'email' : dj.email,
        'permissions' : permissions,
        }

  @property
  def user(self):
    if self.dj_key is None:
      return None
    return Dj.get(self.dj_key)

  @user.setter
  def user(self, dj):
    self.set_session_user(dj)

  def set_session_program(self, pgm):
    """Takes a Program model, and stores values to the session"""
    self.session['program'] = {
        'key' : pgm.key.urlsafe(),
        'slug' : pgm.slug,
        'title' : pgm.title,
        }

  def clear_session_program(self):
    if "program" in self.session:
      self.session["program"] = None
      del self.session["program"]

  @property
  def program(self):
    return self.program_key

  @program.setter
  def program(self, pgm):
    self.set_session_program(pgm)

  def session_logout(self):
    """Logs the dj out, deleting program and dj keys in the session"""
    for key in ('dj', 'program'):
      if key in self.session:
        self.session[key] = None
        del self.session[key]

  def session_has_login(self):
    return self.session.has_key('dj')

  def session_has_program(self):
    return self.session.has_key('program')

  @property
  def dj_key(self):
    if "dj" not in self.session:
      return None

    key = self.session.get('dj').get('key')
    if key is not None:
      return ndb.Key(urlsafe=key)
    return None

  @property
  def program_key(self):
    if "program" not in self.session:
      return None

    key = self.session.get('program').get('key')
    if key is not None:
      return ndb.Key(urlsafe=key)
    return None
