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
import logging
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from django.utils import simplejson
from google.appengine.api import memcache
from google.appengine.runtime import DeadlineExceededError

def getPath(filename):
  return os.path.join(os.path.dirname(__file__), filename)

class MainPage(webapp.RequestHandler):
  def get(self):
    self.sess = sessions.Session()
    self.flash = flash.Flash()
    album_list = []
    # album_list = models.getNewAlbums(50)
    start = datetime.datetime.now() - datetime.timedelta(weeks=1)
    end = datetime.datetime.now()
    song_num = 60
    album_num = 60
    top_songs, top_albums = models.getTopSongsAndAlbums(start, end, 
                                                        song_num, album_num)
    posts = models.getLastPosts(3)
    events = models.getEventsAfter(datetime.datetime.now() - 
                                   datetime.timedelta(days=1), 3)
    template_values = {
      'flash': self.flash,
      'session': self.sess,
      'album_list': album_list,
      'top_songs': top_songs,
      'top_albums': top_albums,
      'posts': posts,
      'events': events,
      }
    self.response.out.write(template.render(getPath("index.html"), 
                                            template_values))

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

class AlbumTable(webapp.RequestHandler):
  def post(self):
    page = self.request.get('page')
    try:
      page = int(page)
    except ValueError:
      self.response.out.write(simplejson.dumps({
            'err': "Unable to parse requested page."
            }))
      return
    album_table_html = memcache.get("album_table_html")
    if album_table_html is None:
      albums = models.getNewAlbums(100, page)
      template_values = {
        'album_list': albums,
        }
      album_table_html = template.render(getPath("newalbums.html"), template_values)
      memcache.set("album_table_html", album_table_html)
    self.response.out.write(album_table_html)

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
    labels = ["Manage DJs", "Manage Programs", "Manage Permissions", 
              "Manage Albums", "Manage Genres", "Manage Blog", "Manage Events"]
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
        ar = models.ArtistName(artist_name=a, lowercase_name=a.lower(), search_names=models.artistSearchName(a).split())
        ar.put()
    self.flash.msg = "Permissions set up, ArtistNames set up, Blog posts set up, DJ Seth entered."
    self.redirect('/')
  


class BlogDisplay(webapp.RequestHandler):
  def get(self, date_string, post_slug):
    post_date = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    post = models.getPostBySlug(post_date, post_slug)
    self.flash = flash.Flash()
    if not post:
      self.flash.msg = "The post you requested could not be found.  Please try again."
      self.redirect('/')
      return
    template_values = {
      'post': post,
      }
    self.response.out.write(template.render("blog_post.html", template_values))

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
    self.response.headers["Content-Type"] = "text/json"
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
    self.response.headers["Content-Type"] = "text/json"
    album_key = self.request.get("album_key")
    songlist_html = memcache.get("songlist_html_" + album_key)
    if songlist_html:
      self.response.out.write(simplejson.dumps({
            'songListHtml': songlist_html,
            'generated': 'memcache',
            }))
      return
    album = models.Album.get(album_key)
    self.response.headers["Content-Type"] = "text/json"
    if not album:
      self.response.out.write(simplejson.dumps({
            'err': "An error occurred and the specified album could not be found.  Please try again."
            }))
      return
    songlist_html = template.render(getPath("ajax_songlist.html"), {
        'songList': [models.Song.get(k) for k in album.songList],
        })
    memcache.set("songlist_html_" + album_key, songlist_html)
    self.response.out.write(simplejson.dumps({
          'songListHtml': template.render(getPath("ajax_songlist.html"), {
              'songList': [models.Song.get(k) for k in album.songList],
              }),
          'generated': 'generated',
          }))
    


class EventPage(webapp.RequestHandler):
  def get(self):
    start_date = datetime.datetime.now() - datetime.timedelta(days=2)
    events = models.getEventsAfter(start_date)
    self.sess = sessions.Session()
    self.flash = flash.Flash()
    template_values = {
      'events': events,
      'logged_in': self.sess.has_key('dj'),
      }
    self.response.out.write(template.render(getPath("events.html"), 
                                            template_values))

class SchedulePage(webapp.RequestHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("schedule.html"), 
                                            template_values))

class PlaylistPage(webapp.RequestHandler):
  def get(self):
    shows = models.getPrograms()
    self.sess = sessions.Session()
    self.flash = flash.Flash()
    slug = self.request.get("show")
    datestring = self.request.get("programdate")
    selected_date = None

    if datestring:
      try:
        selected_date = datetime.datetime.strptime(datestring, "%m/%d/%Y")
        selected_date = selected_date + datetime.timedelta(hours=12)
      except:
        self.flash.msg = "The date provided could not be parsed."
        self.redirect("/")
        return

    if slug:
      selected_program = models.getProgramBySlug(slug)
      if not selected_program:
        self.flash.msg = "There is no program for slug %s." % slug
        self.redirect("/")
        return
      if selected_date:
        plays = models.getPlaysBetween(program=selected_program, 
                                       after=(selected_date - 
                                              datetime.timedelta(hours=24)), 
                                       before=(selected_date + 
                                               datetime.timedelta(hours=24)))
      else:
        lastplay = models.getLastPlays(program=selected_program, num=1)
        if lastplay:
          lastplay = lastplay[0]
          last_date = lastplay.play_date
          plays = models.getPlaysBetween(program=selected_program,
                                         after=(last_date - 
                                                datetime.timedelta(days=1)))
        else:
          plays = []
    else:
      if not selected_date:
        lastplay = models.getLastPlay()
        if lastplay:
          selected_date = lastplay.play_date

      if selected_date:
        plays = models.getPlaysForDate(selected_date)
      else:
        plays = []
      #plays = models.getLastNPlays(60)
    
    template_values = {
      'plays': plays,
      'shows': shows,
      }
    self.response.out.write(template.render(getPath("playlist.html"), 
                                            template_values))

class FunPage(webapp.RequestHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("fun.html"), 
                                            template_values))

class ChartsPage(webapp.RequestHandler):
  def get(self):
    start = datetime.datetime.now() - datetime.timedelta(weeks=1)
    end = datetime.datetime.now()
    song_num = 60
    album_num = 60
    songs, albums = models.getTopSongsAndAlbums(start, end, song_num, album_num)
    template_values = {
      'songs': songs,
      'albums': albums,
      'start': start,
      'end': end,
      }
    self.response.out.write(template.render(getPath("charts.html"), template_values))

class HistoryPage(webapp.RequestHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("history.html"), template_values))

class ContactPage(webapp.RequestHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("contact.html"), template_values))

class ConvertArtistNames(webapp.RequestHandler):
  def get(self):
    an = models.ArtistName.all().fetch(2000)
    total = 0
    try:
      for a in an:
        if not a.search_names:
          total += 1
          a.search_names = models.artistSearchName(a.lowercase_name).split()
          a.put()
      self.response.out.write("converted %d artist names." % total)
    except DeadlineExceededError:
      self.response.out.write("converted %d artist names, incomplete." % total)
    

class ConvertPlays(webapp.RequestHandler):
  def get(self):
    pc = models.Play.all().fetch(2000)
    total = 0
    for p in pc:
      if not p.artist:
        total += 1
        p.artist = p.song.artist
        p.put()
    self.response.out.write("converted %d plays." % total)

class ProgramPage(webapp.RequestHandler):
  def get(self, slug):
    self.flash = flash.Flash()
    self.sess = sessions.Session()
    program = models.getProgramBySlug(slug)
    posts = models.getLastPosts(1)
    if not program:
      self.flash.msg = "Invalid program slug specified."
      self.redirect("/")
      return
    template_values = {
      'session': self.sess,
      'flash': self.flash,
      'program': program,
      'djs' :  (tuple(models.Dj.get(dj) 
                      for dj in program.dj_list) if program.dj_list
                else None),
      'posts': posts,
      }
    self.response.out.write(template.render(getPath("show.html"), template_values))


def profile_main():
  # This is the main function for profiling
  # We've renamed our original main() above to real_main()
  import cProfile, pstats, StringIO
  prof = cProfile.Profile()
  prof = prof.runctx("real_main()", globals(), locals())
  stream = StringIO.StringIO()
  stats = pstats.Stats(prof, stream=stream)
  stats.sort_stats("time")  # Or cumulative
  stats.print_stats(80)  # 80 = how many to print
  # The rest is optional.
  # stats.print_callees()
  # stats.print_callers()
  logging.info("Profile data:\n%s", stream.getvalue())

def real_main():
  application = webapp.WSGIApplication([
      ('/', MainPage),
      ('/updateinfo/?', UpdateInfo),
      ('/ajax/albumtable/?', AlbumTable),
      ('/ajax/albuminfo/?', AlbumInfo),
      ('/ajax/artistcomplete/?', ArtistComplete),
      ('/ajax/getSongList/?', SongList),
      ('/ajax/djcomplete/?', DjComplete),
      ('/setup/?', Setup),
      ('/blog/([^/]*)/([^/]*)/?', BlogDisplay),
      ('/programs?/([^/]*)/?', ProgramPage),
      ('/schedule/?', SchedulePage),
      ('/playlists/?', PlaylistPage),
      ('/fun/?', FunPage),
      ('/charts/?', ChartsPage),
      ('/history/?', HistoryPage),
      ('/contact/?', ContactPage),
      ('/events/?', EventPage),
      ('/searchnames/?', ConvertArtistNames),
      ('/convertplays/?', ConvertPlays),
      ('/albums/([^/]*)/([^/]*)/?', AlbumDisplay),
      ],
                                       debug=True)
  util.run_wsgi_app(application)

main = real_main
if __name__ == '__main__':
  main()
