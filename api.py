## Author: Harrison Chapman
# api.py is (will be) the main component of the wbor JSON api.

import json
import webapp2

class ApiJsonRequestHandler(webapp2.RequestHandler):
    pass

class ApiGetNowPlaying(ApiJsonRequestHandler):
  def get(self):
    recent_songs = cache.getLastPlays(num=3)
    logging.debug(recent_songs)
    if recent_songs is not None and len(recent_songs) > 0:
      last_play = recent_songs[0]
      song, program = (cache.getSong(last_play.song_key), 
                       cache.getProgram(last_play.program_key))
      song_string = song.title + " &mdash; " + song.artist
      program_title, program_desc, program_slug = (program.title,
                                                   program.desc,
                                                   program.slug)

      self.response.headers["Content-Type"] = "text/json"
      self.response.out.write(json.dumps({
                  'song_title': song.title,
                  'song_artist': song.artist,
                  'song_key': song.key(),
                  'program_title': program.title
                  'program_desc': program.desc,
                  'program_slug': program.slug,
                  'program_key': program.key(),
                  }))

    else:
        song, program = None, None
        song_string = "Nothing is playing"
        program_title, program_desc, program_slug = ("No show",
                                                     "No description",
                                                     "")


app = webapp2.WSGIApplication([
    ('/api/nowplaying/?', ApiGetNowPlaying),
    ], debug=True, config=webapp2conf)

