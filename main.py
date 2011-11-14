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
import cache
import urllib
import hashlib
import datetime
import time
import amazon
import logging
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
import webapp2
from webapp2_extras import sessions
from google.appengine.ext.webapp import util
from django.utils import simplejson
from google.appengine.api import memcache
from google.appengine.runtime import DeadlineExceededError
from passwd_crypto import hash_password
from dj import check_login
from handlers import BaseHandler, UserHandler

from configuration import webapp2conf
import configuration as conf

def getPath(filename):
  return os.path.join(os.path.dirname(__file__), filename)

class MainPage(BaseHandler):
  def get(self):
    ## Album list disabled until it is further optimized.
    album_list = []
    # album_list = models.getNewAlbums(50)
    start = datetime.datetime.now() - datetime.timedelta(weeks=1)
    end = datetime.datetime.now()
    song_num = 10
    album_num = 10
    top_songs, top_albums = models.getTopSongsAndAlbums(start, end, song_num, album_num)
    posts = models.getLastPosts(3)
    events = models.getEventsAfter(datetime.datetime.now() - 
                                   datetime.timedelta(days=1), 3)
    template_values = {
      'flash': self.flash,
      'session': self.session,
      'album_list': album_list,
      'top_songs': top_songs,
      'top_albums': top_albums,
      'posts': posts,
      'events': events,
      }
    self.response.out.write(template.render(getPath("index.html"), 
                                            template_values))

class DjComplete(BaseHandler):
  def get(self):
    q = self.request.get("query")
    djs = models.djAutocomplete(q)
    self.response.out.write(simplejson.dumps({
          'query': q,
          'suggestions': [dj.fullname for dj in djs],
          'data': [str(dj.key()) for dj in djs],
          }))

class ArtistComplete(BaseHandler):
  def get(self):
    q = self.request.get("query")
    artists = cache.artistAutocomplete(q)
    self.response.out.write(simplejson.dumps({
          'query': q,
          'suggestions': [ar.artist_name for ar in artists],      
          }))

class AlbumTable(BaseHandler):
  def post(self):
    pass

  def dummy(self):
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
      albums = models.getNewAlbums(20, page)
      template_values = {
        'album_list': albums,
        }
      album_table_html = template.render(getPath("newalbums.html"), template_values)
      memcache.set("album_table_html", album_table_html)
    self.response.out.write(album_table_html)

class AlbumInfo(BaseHandler):
  def get(self):
    artist = self.request.get('artist')
    album = self.request.get('album')
    keywords = self.request.get('keywords')

    keywords = (urllib.quote(keywords) + "%20" + 
                urllib.quote(artist) + "%20" + urllib.quote(album))
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
  

class Setup(BaseHandler):
  def get(self):
    labels = ["Manage DJs", "Manage Programs", "Manage Permissions", 
              "Manage Albums", "Manage Genres", "Manage Blog", "Manage Events"]
    for l in labels:
      if not models.getPermission(l):
        permission = models.Permission(title=l, dj_list=[])
        permission.put()
    seth = models.getDjByEmail("seth.glickman@gmail.com")
    if not seth:
      seth = models.Dj(fullname='Seth Glickman', lowername='seth glickman', 
                       email='seth.glickman@gmail.com', username='seth', 
                       password_hash=hash_password('testme'))
      seth.put()
      program = models.Program(title='Seth\'s Show', slug='seth', 
                               desc='This is the show where Seth plays his favorite music.',
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
    self.session.add_flash("Permissions set up, ArtistNames set up, Blog posts set up, DJ Seth entered.")
    self.redirect('/')
  


class BlogDisplay(BaseHandler):
  def get(self, date_string, post_slug):
    post_date = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    post = models.getPostBySlug(post_date, post_slug)
    if not post:
      self.session.add_flash("The post you requested could not be found.  Please try again.")
      self.redirect('/')
      return
    template_values = {
      'post': post,
      }
    self.response.out.write(template.render("blog_post.html", template_values))

class AlbumDisplay(BaseHandler):
  def get(self, key_id, size):
    album = models.Album.get(key_id)
    cover = models.CoverArt.get(album)
    if not album:
      return
    image_blob = cover.small_cover
    image_type = cover.small_filetype
    if size == "l":
      image_blob = cover.large_cover
      image_type = cover.large_filetype
    if image_blob and image_type:
      self.response.headers["Content-Type"] = "image/" + image_type
      self.response.out.write(image_blob)


class UpdateInfo(webapp2.RequestHandler):
  def get(self):
    recent_songs = cache.getLastPlays(num=3)
    logging.error(recent_songs)
    if recent_songs is not None and len(recent_songs) > 0:
      last_play = recent_songs[0]
      song, program = (cache.getSong(last_play.song_key), 
                       cache.getProgram(last_play.program_key))
      song_string = song.title + " &mdash; " + song.artist
      program_title, program_desc, program_slug = (program.title,
                                                   program.desc,
                                                   program.slug)
    else:
      song, program = None, None
      song_string = "Nothing is playing"
      program_title, program_desc, program_slug = ("No show",
                                                   "No description",
                                                   "")

    self.response.headers["Content-Type"] = "text/json"
    self.response.out.write(simplejson.dumps({
          'song_string': song_string,
          'program_title': program_title,
          'program_desc': program_desc,
          'program_slug': program_slug,
          'top_played': ("Top artists: " + ", ".join([a for a in program.top_artists[:3]]) if
                         program is not None else None),
          'recent_songs_html': template.render(getPath("recent_songs.html"), {'plays': recent_songs}),
          }))


class SongList(BaseHandler):
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
    


class EventPage(BaseHandler):
  def get(self):
    start_date = datetime.datetime.now() - datetime.timedelta(days=2)
    events = models.getEventsAfter(start_date)
    template_values = {
      'events': events,
      }
    self.response.out.write(template.render(getPath("events.html"), 
                                            template_values))

class SchedulePage(BaseHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("schedule.html"), 
                                            template_values))

class PlaylistPage(BaseHandler):
  def get(self):
    shows = models.getPrograms()
    slug = self.request.get("show")
    datestring = self.request.get("programdate")
    selected_date = None

    if datestring is not None:
      try:
        selected_date = datetime.datetime.strptime(datestring, "%m/%d/%Y")
        selected_date = selected_date + datetime.timedelta(hours=12)
      except:
        self.session.add_flash("The date provided could not be parsed.")
        self.redirect("/")
        return

    if slug:
      selected_program = models.getProgramBySlug(slug)
      if not selected_program:
        self.session.add_flash("There is no program for slug %s." % slug)
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
        lastplay = cache.getLastPlays()[0]
        if lastplay:
          selected_date = lastplay.play_date

      if selected_date:
        plays = models.getPlaysForDate(selected_date)
      else:
        plays = cache.getLastPlays(60)
    
    template_values = {
      'plays': plays,
      'shows': shows,
      }
    self.response.out.write(template.render(getPath("playlist.html"), 
                                            template_values))

class FunPage(BaseHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("fun.html"), 
                                            template_values))

class ChartsPage(UserHandler):
  @check_login
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
      'login': self.dj_login,
      }
    self.response.out.write(template.render(getPath("charts.html"), template_values))

class HistoryPage(BaseHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("history.html"), template_values))

class ContactPage(BaseHandler):
  def get(self):
    template_values = {}
    self.response.out.write(template.render(getPath("contact.html"), template_values))

class ConvertArtistNames(BaseHandler):
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
    

class ConvertPlays(BaseHandler):
  def get(self):
    pc = models.Play.all().fetch(2000)
    total = 0
    for p in pc:
      if not p.artist:
        total += 1
        p.artist = p.song.artist
        p.put()
    self.response.out.write("converted %d plays." % total)

class ProgramPage(BaseHandler):
  def get(self, slug):
    program = models.getProgramBySlug(slug)
    posts = models.getLastPosts(1)
    if not program:
      self.session.add_flash("Invalid program slug specified.")
      self.redirect("/")
      return
    template_values = {
      'session': self.session,
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



app = webapp2.WSGIApplication([
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
    ], debug=True, config=webapp2conf)
