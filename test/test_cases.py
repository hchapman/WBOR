## Test cases for wbor.org functionality
# Author: Harrison Chapman


from google.appengine.dist import use_library
use_library('django', '1.3')

from google.appengine.ext import webapp
from google.appengine.ext import ndb
from google.appengine.ext import testbed
from webapp2 import Response, Request
from webapp2_extras import sessions

from models.dj import Dj
from models.play import Program
import json

import pprint
import Cookie

import unittest

from models.dj import *

from dj import app as dj_app
from main import app as main_app

#from handlers import BaseHandler
from configuration import webapp2conf

def get_session(response, app=main_app):
  pass
def get_response(request, app=main_app):
  response = request.get_response(app)
  cookies = response.headers.get('Set-Cookie')
  request = Request.blank('/', headers=[('Cookie', cookies)])
  request.app = app
  store = sessions.SessionStore(request)
  session = store.get_session()
  flashes = session.get_flashes()
  store.save_sessions(response)

  return response, session, flashes

class TestHandlers(unittest.TestCase):
  def set_cookie(self, response):
    self.cookies.load(response.headers['Set-Cookie'])

  def setUp(self):
    # Initialize the GAE testbed (dummy services)
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.setup_env
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()

    # Setup datastore and login as seth (superadmin)
    self.cookies = Cookie.BaseCookie()

    req = Request.blank('/setup')
    req.get_response(main_app)

    req = Request.blank('/dj/login', POST={'username': 'seth',
                                           'password': 'testme'})
    req.method = 'POST'
    res, self.session, flashes = get_response(req, app=dj_app)
    self.set_cookie(res)

  def test_get_new(self):
    new_cacheables = [Dj, Program]
    for cls in new_cacheables:
      objs = cls.get_new(num=5)
      self.assertEqual(1, len(objs))

    for cls in new_cacheables:
      objs = cls.get_new(num=5)
      self.assertEqual(1, len(objs))

  def test_logged_in(self):
    self.assertEqual(self.session['dj']['username'], 'seth')

  def test_dj_management(self):
    # Add some Djs
    names = file("./names")
    name_pairs = [(name.strip(),
                  (name[0] + name.split()[1]).lower().strip()) for name in names]

    seen_unames = set()
    for name, uname in name_pairs:
      req = Request.blank('/dj/djs/', POST={
        'username': uname,
        'fullname': name,
        'email': uname,
        'password': "wbor",
        'confirm': "wbor",
        'submit': "Add DJ"})
      req.headers['Cookie'] = self.cookies.output()
      req.method = 'POST'
      res, ses, flash = get_response(req, app=dj_app)

      if uname in seen_unames:
        self.assertNotEqual(u"success", flash[0][1])
      else:
        self.assertEqual(u"success", flash[0][1])

      seen_unames.add(uname)
      self.set_cookie(res)

    # Run some searches on Djs
    name, uname = name_pairs[1]
    fname = name.split()[0]

    djkey = Dj.get_key_by_username(uname)

    for i in range(len(fname)):
      req = Request.blank('/ajax/djcomplete?query=%s'%fname[:i+1])
      res, ses, flash = get_response(req, app=main_app)
      found = json.loads(res.body)
      res_keys = [data['key'] for data in found['data']]
      self.assertIn(djkey.urlsafe(), res_keys)

    # Run some searches on Djs. Guy should NOT show up
    name = "Guy Fieri"
    fname = name.split()[0]

    for i in range(len(fname)):
      req = Request.blank('/ajax/djcomplete?query=%s'%fname[:i+1])
      res, ses, flash = get_response(req, app=main_app)
      found = json.loads(res.body)
      res_keys = [data['key'] for data in found['data']]
      self.assertNotIn(djkey.urlsafe(), res_keys)

    # Modify this guy so that his name is different
    
    req = Request.blank('/dj/djs/%s'%djkey.urlsafe(), POST={
      'username': "gfieri",
      'fullname': "Guy Fieri",
      'email': "guyguy",
      'submit': "Edit DJ"})
    req.headers['Cookie'] = self.cookies.output()
    req.method = 'POST'
    res, ses, flash = get_response(req, app=dj_app)
    print flash
    self.assertEqual(u"success", flash[0][1])
    self.set_cookie(res)

    # Run some searches on Djs. Our changed guy shouldn't be here.
    name, uname = name_pairs[1]
    fname = name.split()[0]

    for i in range(len(fname)):
      req = Request.blank('/ajax/djcomplete?query=%s'%fname[:i+1])
      res, ses, flash = get_response(req, app=main_app)
      found = json.loads(res.body)
      res_keys = [data['key'] for data in found['data']]
      self.assertNotIn(djkey.urlsafe(), res_keys)

    # Run some searches on Djs. Guy should show up
    name, uname = "Guy Fieri", "gfieri"
    fname = name.split()[0]

    for i in range(len(fname)):
      req = Request.blank('/ajax/djcomplete?query=%s'%fname[:i+1])
      res, ses, flash = get_response(req, app=main_app)
      found = json.loads(res.body)
      res_keys = [data['key'] for data in found['data']]
      self.assertIn(djkey.urlsafe(), res_keys)

  def tearDown(self):
    self.testbed.deactivate()

if __name__ == "__main__":
  unittest.main()
