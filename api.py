## Author: Harrison Chapman
# api.py is (will be) the main component of the wbor JSON api.

import json
import webapp2
import logging

import cache

from configuration import webapp2conf
from main import ViewCoverHandler

class ApiRequestHandler(webapp2.RequestHandler):
  def json_respond(self, data):
    self.response.headers["Content-Type"] = "text/json"
    self.response.out.write(json.dumps(data))


class NowPlaying(ApiRequestHandler):
  def get(self):
    last_play = cache.getLastPlay()
    if last_play is not None:
      self.json_respond(last_play.to_json())
    else:
      self.json_respond({})

class LastPlays(ApiRequestHandler):
  def get(self):
    last_plays = cache.getLastPlays(num=20)
    self.json_respond({
        'play_list': [play.to_json() for play in last_plays]
        })

class NewShelf(ApiRequestHandler):
  def get(self):
    album_list = cache.getNewAlbums(num=36)
    self.json_respond({
        'album_list': [album.to_json() for album in album_list]
        })

class PlayHandler(ApiRequestHandler):
  def get(self, key):
    play = cache.getPlay(key)
    if play:
      self.json_respond(play.to_json())

class SongHandler(ApiRequestHandler):
  def get(self, key):
    song = cache.getSong(key)
    if song:
      self.json_respond(song.to_json())

class ProgramHandler(ApiRequestHandler):
  def get(self, key):
    program = cache.getProgram(key)
    if program:
      self.json_respond(program.to_json())

class AlbumHandler(ApiRequestHandler):
  def get(self, key):
    album = cache.getAlbum(key)
    logging.info(album.to_json())
    if album is not None:
      self.json_respond(album.to_json())

app = webapp2.WSGIApplication([
    ('/api/nowPlaying/?', NowPlaying),
    ('/api/lastPlays/?', LastPlays),
    ('/api/newShelf/?', NewShelf),

    # RESTful API object handlers
    ('/api/play/([^/]*)/?', PlayHandler),
    ('/api/song/([^/]*)/?', SongHandler),
    ('/api/program/([^/]*)/?', ProgramHandler),
    ('/api/album/([^/]*)/?', AlbumHandler),
    ('/api/cover/([^/]*)/?', ViewCoverHandler),
    ], debug=True, config=webapp2conf)

