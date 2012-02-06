## Test cases for wbor.org functionality
# Author: Harrison Chapman

from google.appengine.ext import webapp
from google.appengine.ext import db

import cache
from models.dj import Dj

from handlers import BaseHandler
from configuration import webapp2conf

def run():
    runCacheTests()

def runCacheTests():
    runDjCacheTests()

def runDjCacheTests():
  try:
    # Put some Djs
    dj1 = Dj.new(email="tcase",
                 fullname="Test Casington",
                 username="tcase",
                 password="esact")

    dj2 = cache.putDj(email="tcase2@",
                      fullname="Tesla Casey",
                      username="tcase2",
                      password="esac_secret")

    dj3 = cache.putDj(email="ctest@gmail.com",
                      fullname="Chase Testa",
                      username="ctest",
                      password="chest")

    print dj1.to_xml()
    print dj2.to_xml()
    print dj3.to_xml()

    # Alter some Dj information
    dj2 = cache.putDj(email="teslac", edit_dj=dj2)
    dj2 = cache.putDj(email="teslac@", edit_dj=dj2)
    dj2 = cache.putDj(email="teslac@hotmail.com", edit_dj=dj2)

    dj1.put(fullname="Tess Case")
    dj1.put(email="tesscase", fullname="Tessa Case")
    dj1.put(email="tesscase@", fullname="Tessa Case")

    dj3 = cache.putDj(email="chase", fullname="Chase Case", 
                      password="secret", edit_dj=dj3)
    dj3 = cache.putDj(password="supersecret2", edit_dj=dj3)

    print dj1.to_xml()
    print dj2.to_xml()
    print dj3.to_xml()

    print dj1.__hash__()
    print dj1.key() == db.Key(str(dj1.key()))
    print str(dj1.key()).__hash__()
    print dj1.key().__hash__()

    print "--------------------"
    
    # Try logging in
    print cache.djLogin("ctest", "chest")
    print cache.djLogin("ctest", "secret")
    print cache.djLogin("ctest", "supersecret2")

  finally:
    # Delete the Djs
    dj1.delete()
    cache.deleteDj(dj2)
    cache.deleteDj(dj3)

    print cache.djLogin("ctest", "supersecret2")
    print cache.djLogin("ctest", "chest")

class RunTests(BaseHandler):
    def get(self):
        run()

app = webapp.WSGIApplication([
        ('.*', RunTests),
        ], debug=True, config=webapp2conf)
