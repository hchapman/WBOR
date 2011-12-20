## Author: Harrison Chapman
# api.py is (will be) the main component of the wbor JSON api.

import json
import webapp2
import logging

import cache

from configuration import webapp2conf

class ApiRequestHandler(webapp2.RequestHandler):
  def jsonResponse(self, data):
    self.response.headers["Content-Type"] = "text/json"
    self.response.out.write(json.dumps(data))


class NowPlaying(ApiRequestHandler):
  def get(self):
    last_play = cache.getLastPlay()
    if last_play is not None:
      self.jsonResponse(last_play.to_json())
    else:
      self.jsonResponse({})

class LastPlayed(ApiRequestHandler):
  def playToDict(self, play):
    song = cache.getSong(play.song_key)
    prog = cache.getProgram(play.program_key)
    return {'song_title': song.title,
            'song_artist': song.artist,
            'song_key': str(song.key()),
            'program_title': prog.title,
            'program_desc': prog.desc,
            'program_slug': prog.slug,
            'program_key': str(prog.key()),
            }

  def get(self):
    last_plays = cache.getLastPlays(num=20)
    self.jsonResponse({
        'play_list': [play.to_json() for play in last_plays]
        })
    

app = webapp2.WSGIApplication([
    ('/api/nowPlaying/?', NowPlaying),
    ('/api/lastPlays/?', LastPlayed),
    ], debug=True, config=webapp2conf)

