#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import models
import urllib
import hashlib
import datetime
import sessions
import time
import flash
import amazon
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from django.utils import simplejson

def getPath(filename):
  return os.path.join(os.path.dirname(__file__), filename)

class MainPage(webapp.RequestHandler):

  def get(self):
    self.sess = sessions.Session()
    self.flash = flash.Flash()
    recently_played = [
      {
        'title': "Song 1",
        'artist': "Artist 1",
        'timestamp': "5 minutes ago",
      },
      {
        'title': "Song 1",
        'artist': "Artist 1",
        'timestamp': "5 minutes ago",
      },
    ]
    album_list = models.getNewAlbums()
    song_charts = [
    
    ]
    album_charts = [
    
    ]
    posts = models.getLastPosts(3)
    template_values = {
      'flash': self.flash,
      'session': self.sess,
      'recently_played': recently_played,
      'album_list': album_list,
      'song_charts': song_charts,
      'album_charts': album_charts,
      'posts': posts,
    }
    self.response.out.write(template.render(getPath("index.html"), template_values))

class DjComplete(webapp.RequestHandler):
  def get(self):
    q = self.request.get("query")
    djs = models.djAutocomplete(q)
    self.response.out.write(simplejson.dumps({
      'query': q,
      'suggestions': [dj.fullname for dj in djs],
      'data': [str(dj.key()) for dj in djs],
    }))

class ArtistComplete(webapp.RequestHandler):
  def get(self):
    q = self.request.get("query")
    artists = models.artistAutocomplete(q)
    self.response.out.write(simplejson.dumps({
      'query': q,
      'suggestions': [ar.artist_name for ar in artists],      
    }))

class AlbumInfo(webapp.RequestHandler):
  def get(self):    
    artist = self.request.get('artist')
    album = self.request.get('album')
    keywords = self.request.get('keywords')
    keywords = urllib.quote(keywords) + "%20" + urllib.quote(artist) + "%20" + urllib.quote(album)
    # AKIAJIXECWA77X5XX4DQ
    # 6oYjAsiXTz8xZzpKZC8zkqXnkYV72CNuCRh9hUsQ
    # datetime.datetime.now().strftime("%Y-%m-%dT%H:%M%:%SZ")
    items = amazon.productSearch(keywords)
    json_data = {'items': [{
      'small_pic': i.getElementsByTagName("SmallImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
      'large_pic': i.getElementsByTagName("LargeImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
      'medium_pic': i.getElementsByTagName("MediumImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
      'artist': i.getElementsByTagName("Artist")[0].firstChild.nodeValue,
      'title': i.getElementsByTagName("Title")[0].firstChild.nodeValue,
      'asin': i.getElementsByTagName("ASIN")[0].firstChild.nodeValue,
      'tracks': [t.firstChild.nodeValue for t in i.getElementsByTagName("Track")],
    } for i in items]}
    updatehtml = template.render(getPath("addalbumupdate.html"), json_data)
    json_data['updatehtml'] = updatehtml
    self.response.headers['Content-Type'] = 'text/json'
    self.response.out.write(simplejson.dumps(json_data))
  

class Setup(webapp.RequestHandler):
  def get(self):
    self.flash = flash.Flash()
    labels = ["Manage DJs", "Manage Programs", "Manage Permissions", "Manage Albums", "Manage Genres", "Manage Blog", "Manage Events"]
    for l in labels:
      if not models.getPermission(l):
        permission = models.Permission(title=l, dj_list=[])
        permission.put()
    seth = models.getDjByEmail("seth.glickman@gmail.com")
    if not seth:
      seth = models.Dj(fullname='Seth Glickman', lowername='seth glickman', email='seth.glickman@gmail.com', username='seth', password_hash='testme')
      seth.put()
      program = models.Program(title='Seth\'s Show', slug='seth', desc='This is the show where Seth plays his favorite music.',
        dj_list=[seth.key()], page_html='a <b>BOLD</b> show!')
      program.put()
    for l in labels:
      permission = models.getPermission(l)
      if seth.key() not in permission.dj_list:
        permission.dj_list.append(seth.key())
        permission.put()
    if not models.getLastPosts(3):
      post1 = models.BlogPost(title="Blog's first post!", text="This is really just filler text on the first post.", slug="first-post", post_date=datetime.datetime.now())
      post1.put()
      time.sleep(2)
      post2 = models.BlogPost(title="Blog's second post!", text="More filler text, alas.", slug="second-post", post_date=datetime.datetime.now())
      post2.put()
    artists = [
      "Bear In Heaven",
      "Beck",
      "Arcade Fire",
      "Andrew Bird",
      "The Antlers",
      "Arcade Fire",
      "The Beach Boys",
      "Brian Wilson",
      "The Beatles",
      "Beethoven",
      "Beirut",
      "Belle & Sebastian",
      "Benji Hughes",
      "Club 8",
      "Crayon Fields",
    ]
    for a in artists:
      if not models.ArtistName.all().filter("artist_name =", a).fetch(1):
        ar = models.ArtistName(artist_name=a, lowercase_name=a.lower())
        ar.put()
    self.flash.msg = "Permissions set up, ArtistNames set up, Blog posts set up, DJ Seth entered."
    self.redirect('/')
  


class AlbumDisplay(webapp.RequestHandler):
  def get(self, key_id, size):
    album = models.Album.get(key_id)
    if not album:
      return
    image_blob = album.small_cover
    image_type = album.small_filetype
    if size == "l":
      image_blob = album.large_cover
      image_type = album.large_filetype
    if image_blob and image_type:
      self.response.headers["Content-Type"] = "image/" + image_type
      self.response.out.write(image_blob)


class UpdateInfo(webapp.RequestHandler):
  def get(self):
    lastPlay = models.getLastPlay()
    song, program = lastPlay.song, lastPlay.program
    song_string = song.title + " &mdash; " + song.artist
    recent_songs = models.getLastNPlays(3)
    # self.response.headers["Content-Type"] = "text/json"
    self.response.out.write(simplejson.dumps({
      'song_string': song_string,
      'program_title': program.title,
      'program_desc': program.desc,
      'program_slug': program.slug,
      'top_played': "Top artists: " + ", ".join([a for a in program.top_artists[:3]]),
      'recent_songs_html': template.render(getPath("recent_songs.html"), {'plays': recent_songs}),
    }))


class SongList(webapp.RequestHandler):
  def get(self):
    album_key = self.request.get("album_key")
    album = models.Album.get(album_key)
    self.response.headers["Content-Type"] = "text/json"
    if not album:
      self.response.out.write(simplejson.dumps({
        'err': "An error occurred and the specified album could not be found.  Please try again."
      }))
      return
    self.response.out.write(simplejson.dumps({
      'songListHtml': template.render(getPath("ajax_songlist.html"), {
        'songList': [models.Song.get(k) for k in album.songList],
      })
    }))
    

class ProgramPage(webapp.RequestHandler):
  def get(self, slug):
    self.flash = flash.Flash()
    self.sess = sessions.Session()
    program = models.getProgramBySlug(slug)
    if not program:
      self.flash.msg = "Invalid program slug specified."
      self.redirect("/")
      return
    template_values = {
      'session': self.sess,
      'flash': self.flash,
      'program': program,
    }
    self.response.out.write(template.render(getPath("show.html"), template_values))

def main():
  application = webapp.WSGIApplication([
      ('/', MainPage),
      ('/updateinfo/?', UpdateInfo),
      ('/ajax/albuminfo/?', AlbumInfo),
      ('/ajax/artistcomplete/?', ArtistComplete),
      ('/ajax/getSongList/?', SongList),
      ('/ajax/djcomplete/?', DjComplete),
      ('/setup/?', Setup),
      ('/programs?/([^/]*)/?', ProgramPage),
      ('/albums/([^/]*)/([^/]*)/?', AlbumDisplay),
                                       ],
                                       debug=True)
  util.run_wsgi_app(application)


if __name__ == '__main__':
  main()

