#!/usr/bin/env python

import os
import cache
import urllib
import hashlib
import datetime
import time
import json
import logging

from models.dj import Permission, Dj
from models.tracks import Album, Song, ArtistName
from models.play import Play, Program
from models.base_models import NoSuchEntry
from models.blog import BlogPost

import amazon

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.ext import blobstore
from google.appengine.runtime import DeadlineExceededError

import webapp2
from webapp2_extras import sessions

from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import blobstore_handlers

from passwd_crypto import hash_password
from handlers import BaseHandler, UserHandler
from dj import check_login, login_required

from configuration import webapp2conf
import configuration as conf

def get_path(filename):
  return os.path.join(os.path.dirname(__file__), filename)

class MainPage(BaseHandler):
  def get(self):
    ## Album list disabled until it is further optimized.
    #album_list = []
    album_list = Album.get_new(num=36)
    start = datetime.date.today() - datetime.timedelta(days=6)
    end = datetime.date.today() + datetime.timedelta(days=1)
    song_num = 10
    album_num = 10
    top_songs, top_albums = Play.get_top(start, end, song_num, album_num)
    posts = BlogPost.get_last(num=3)
    events = [] #models.getEventsAfter(datetime.datetime.now() -
              #                     datetime.timedelta(days=1), 3)
    template_values = {
      'news_selected': True,
      'flash': self.flashes,
      'session': self.session,
      'album_list': album_list,
      'top_songs': top_songs,
      'top_albums': top_albums,
      'posts': posts,
      'events': events,
      }
    self.response.out.write(template.render(get_path("index.html"),
                                            template_values))

class DjComplete(BaseHandler):
  def get(self):
    q = self.request.get("query")
    djs = Dj.autocomplete(q)
    self.response.out.write(json.dumps({
          'query': q,
          'suggestions': ["%s - %s"%(dj.fullname, dj.email) for dj in djs],
          'data': [{'key': str(dj.key),
                    'name': dj.fullname,
                    'email': dj.email} for dj in djs],}))

class ArtistComplete(BaseHandler):
  def get(self):
    q = self.request.get("query")
    artists = ArtistName.autocomplete(q)
    self.response.out.write(json.dumps({
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
      self.response.out.write(json.dumps({
            'err': "Unable to parse requested page."
            }))
      return
    album_table_html = memcache.get("album_table_html")
    if album_table_html is None:
      albums = models.getNewAlbums(20, page)
      template_values = {
        'session': self.session,
        'album_list': albums,
        }
      album_table_html = template.render(
        get_path("newalbums.html"), template_values)
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
          'small_pic': (i.getElementsByTagName("SmallImage")[0].
                        getElementsByTagName("URL")[0].
                        firstChild.nodeValue),
          'large_pic': (i.getElementsByTagName("LargeImage")[0].
                        getElementsByTagName("URL")[0].
                        firstChild.nodeValue),
          'medium_pic': (i.getElementsByTagName("MediumImage")[0].
                         getElementsByTagName("URL")[0].
                         firstChild.nodeValue),
          'artist': i.getElementsByTagName("Artist")[0].firstChild.nodeValue,
          'title': i.getElementsByTagName("Title")[0].firstChild.nodeValue,
          'asin': i.getElementsByTagName("ASIN")[0].firstChild.nodeValue,
          'tracks': [t.firstChild.nodeValue
                     for t in i.getElementsByTagName("Track")],
          } for i in items]}
    updatehtml = template.render(get_path("addalbumupdate.html"), json_data)
    json_data['updatehtml'] = updatehtml
    self.response.headers['Content-Type'] = 'text/json'
    self.response.out.write(json.dumps(json_data))


class Setup(BaseHandler):
  def get(self):
    labels = Permission.PERMISSIONS
    try:
      seth = Dj.get_by_email("seth.glickman@gmail.com")
    except NoSuchEntry:
      seth = Dj.new(fullname='Seth Glickman',
                    email='seth.glickman@gmail.com', username='seth',
                    password='testme')
      seth.put()

      program = Program.new(
        title='Seth\'s Show', slug='seth',
        desc='This is the show where Seth plays his favorite music.',
        dj_list=[seth.key],
        page_html='a <b>BOLD</b> show!')
      program.put()
    for l in labels:
      try:
        permission = Permission.get_by_title(l)
      except NoSuchEntry:
        permission = Permission.new(l, [])
        permission.put()
      finally:
        if seth.key not in permission.dj_list:
          permission.add_dj(seth.key)
          permission.put()
    if not BlogPost.get_last(num=3):
      post1 = BlogPost.new(
        title="Blog's first post!",
        text="This is really just filler text on the first post.",
        slug="first-post", post_date=datetime.datetime.now())
      post1.put()
      time.sleep(2)
      post2 = BlogPost.new(
        title="Blog's second post!",
        text="More filler text, alas.",
        slug="second-post", post_date=datetime.datetime.now())
      post2.put()
      contactspage = BlogPost.new(
        title="Contacts Page",
        text="This is a dummy stub for the contacts page. Lorem ipsum whatnot",
        slug="contacts-page", post_date=datetime.datetime.now())
      contactspage.put()
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
      if not (ArtistName._RAW.query()
              .filter(ArtistName._RAW.artist_name == a)
              .fetch(1, keys_only=True)):
        ar = ArtistName.new(artist_name=a)
        ar.put()
    self.session.add_flash("Permissions set up, ArtistNames set up, "
                           "Blog posts set up, DJ Seth entered.")
    self.redirect('/')



class BlogDisplay(BaseHandler):
  def get(self, date_string, post_slug):
    post_date = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    post = models.getPostBySlug(post_date, post_slug)
    if not post:
      self.session.add_flash(
        "The post you requested could not be found.  Please try again.")
      self.redirect('/')
      return
    template_values = {
      'session': self.session,
      'post': post,
      }
    self.response.out.write(template.render("blog_post.html", template_values))

class ViewCoverHandler(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, cover_key):
    if not cover_key:
      self.error(404)
    cover_key = str(urllib.unquote(cover_key))
    self.response.headers["Cache-Control"] = "public"
    expires_date = datetime.datetime.utcnow() + datetime.timedelta(365)
    expires_str = expires_date.strftime("%d %b %Y %H:%M:%S GMT")
    self.response.headers.add_header("Expires", expires_str)
    self.send_blob(cover_key)

"""class AlbumDisplay(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, key_id, size):
    self.response.headers["Cache-Control"] = "max-age=604800"
    album = cache.getAlbum(key_id)
    if not album:
      return
    if size == "l":
      self.send_blob(album.cover_large)
    else:
      self.send_blob(album.cover_small)"""


class UpdateInfo(webapp2.RequestHandler):
  def get(self):
    recent_songs = Play.get_last(num=3)
    if recent_songs is not None and len(recent_songs) > 0:
      last_play = recent_songs[0]
      song, program = (last_play.song,
                       last_play.program)
      logging.error(song.raw)
      song_string = song.title
      artist_string = song.artist
      if program is not None:
        program_title, program_desc, program_slug = (program.title,
                                                     program.desc,
                                                     program.slug)
      else:
        program_title, program_desc, program_slug = ("no show",
                                                     "No description",
                                                     "")
    else:
      song, program = None, None
      song_string = "nothing"
      artist_string = "nobody"
      program_title, program_desc, program_slug = ("no show",
                                                   "No description",
                                                   "")

    self.response.headers["Content-Type"] = "text/json"
    self.response.out.write(json.dumps({
          'song_string': song_string,
          'artist_string': artist_string,
          'program_title': program_title,
          'program_desc': program_desc,
          'program_slug': program_slug,
          'top_played': ("Top artists: " + ", ".join(
            [a[0] for a in program.top_artists[:3]]) if
                         program is not None else None),
          'recent_songs_html': template.render(
            get_path("recent_songs.html"), {'plays': recent_songs}),
          }))

class CallVoice(webapp2.RequestHandler):
  def get(self):
    url = "https://clients4.google.com/voice/embed/webButtonConnect"
    form_fields = {
      'buttonId': self.request.get("button_id"),
      'callerNumber': self.request.get("cid_number"),
      'name': self.request.get("cid_name"),
      'showCallerNumber': "1",
    }
    form_data = urllib.urlencode(form_fields)
    result = urlfetch.fetch(
      url=url,
      payload=form_data,
      method=urlfetch.POST,
      headers={'Content-Type': 'application/x-www-form-urlencoded'})
    self.response.out.write(result)

class SongList(BaseHandler):
  def get(self):
    self.response.headers["Content-Type"] = "text/json"
    album_key = self.request.get("album_key")
    songlist_html = memcache.get("songlist_html_" + album_key)
    if songlist_html:
      self.response.out.write(json.dumps({
            'songListHtml': songlist_html,
            'generated': 'memcache',
            }))
      return
    album = Album.get(album_key, one_key=True)
    self.response.headers["Content-Type"] = "text/json"
    if not album:
      self.response.out.write(json.dumps({
            'err': ("An error occurred and the specified album could "
                    "not be found.  Please try again.")
            }))
      return
    songlist_html = template.render(get_path("ajax_songlist.html"), {
        'songList': Song.get(album.tracklist),
        })
    memcache.set("songlist_html_" + album_key, songlist_html)
    self.response.out.write(json.dumps({
          'songListHtml': template.render(get_path("ajax_songlist.html"), {
              'songList': Song.get(album.tracklist),
              }),
          'generated': 'generated',
          }))

class EventPage(BaseHandler):
  def get(self):
    start_date = datetime.datetime.now() - datetime.timedelta(days=2)
    events = models.getEventsAfter(start_date)
    template_values = {
      'events_selected': True,
      'session': self.session,
      'events': events,
      }
    self.response.out.write(template.render(get_path("events.html"),
                                            template_values))

class SchedulePage(BaseHandler):
  def get(self):
    template_values = {
      'schedule_selected': True,
      'session': self.session,
    }
    self.response.out.write(template.render(get_path("schedule.html"),
                                            template_values))

class PlaylistPage(BaseHandler):
  def get(self):
    shows = Program.get(num=1000) # TODO: NOPE
    slug = self.request.get("show")
    datestring = self.request.get("programdate")
    selected_date = None

    if datestring:
      try:
        selected_date = datetime.datetime.strptime(datestring, "%m/%d/%Y")
        selected_date = selected_date + datetime.timedelta(hours=12)
      except:
        self.session.add_flash("The date provided could not be parsed.")
        self.redirect("/")
        return

    if slug:
      selected_program = Program.get(slug=slug)
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
        lastplay = Play.get_last(program=selected_program, num=1)
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
        lastplay = Play.get_last()
        if lastplay:
          selected_date = lastplay.play_date

      if selected_date:
        plays = models.getPlaysForDate(selected_date)
      else:
        plays = Play.get_last(num=60)

    template_values = {
      'playlists_selected': True,
      'session': self.session,
      'plays': plays,
      'shows': shows,
      }
    self.response.out.write(template.render(get_path("playlist.html"),
                                            template_values))

class PlaylistExport(BaseHandler):
  @login_required
  def get(self):
    import csv
    shows = models.getPrograms()
    slug = self.request.get("show")
    datestring = self.request.get("programdate")
    selected_date = None

    if datestring:
      try:
        selected_date = datetime.datetime.strptime(datestring, "%m/%d/%Y")
        selected_date = selected_date + datetime.timedelta(hours=12)
        print selected_date.isoformat(" ")
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
        lastplay = Play.get_last(program=selected_program, num=1)
        if lastplay:
          lastplay = lastplay[0]
          last_date = lastplay.play_date
          plays = models.getPlaysBetween(program=selected_program,
                                         after=(last_date -
                                                datetime.timedelta(days=1)))
        else:
          plays = []
    else:
      if selected_date is None:
        lastplay = Play.get_last()
        if lastplay:
          selected_date = lastplay.play_date

      if selected_date:
        print "doop"
        print selected_date.isoformat(" ")
        plays = models.getRetardedNumberOfPlaysForDate(selected_date)
      else:
        plays = Play.get_last(num=60)

    csv_sep = "\t"
    out_data = [("Date", "Time", "Title", "Artist")]
    for p in plays:
      s = cache.getSong(p.song_key)
      out_data.append((p.play_date.isoformat(csv_sep), s.title, s.artist))

    self.response.out.write("\n".join([csv_sep.join(row) for row in out_data]))

class FunPage(BaseHandler):
  def get(self):
    template_values = {
      'session': self.session,
    }
    self.response.out.write(template.render(get_path("fun.html"),
                                            template_values))

class ChartsPage(UserHandler):
  @check_login
  def get(self):
    start = datetime.date.today() - datetime.timedelta(days=6)
    end = datetime.date.today() + datetime.timedelta(days=1)
    song_num = 30
    album_num = 30
    songs, albums = Play.get_top(start, end, song_num, album_num)
    template_values = {
      'charts_selected': True,
      'session': self.session,
      'flash': self.flashes,
      'songs': songs,
      'albums': albums,
      'start': start,
      'end': end,
      'login': self.dj_login,
      }
    self.response.out.write(
      template.render(get_path("charts.html"), template_values))

  @check_login
  def post(self):
    song_num = 30
    album_num = 30

    # Parse dates
    start_date_req = self.request.get("start_date")
    if start_date_req:
      try:
        start = datetime.datetime.strptime(start_date_req, "%m/%d/%Y").date()
      except ValueError:
        self.session.add_flash(
          "Unable to parse start date. Defaulting to a week ago, today.")
        start = datetime.date.today() - datetime.timedelta(days=6)
    else:
      start = datetime.date.today() - datetime.timedelta(days=6)

    end_date_req = self.request.get("end_date")
    if end_date_req:
      try:
        end = datetime.datetime.strptime(end_date_req, "%m/%d/%Y").date()
      except ValueError:
        self.session.add_flash(
          "Couldn't parse end date. Defaulting to a week of charts.")
        end = start + datetime.timedelta(weeks=1)
    else:
      end = start + datetime.timedelta(weeks=1)

    if self.request.get("song_num"):
      song_num = int(self.request.get("song_num"))
    if self.request.get("album_num"):
      album_num = int(self.request.get("album_num"))
    songs, albums = Play.get_top(start, end, song_num, album_num)
    template_values = {
      'charts_selected': True,
      'session': self.session,
      'flash': self.flashes,
      'songs': songs,
      'albums': albums,
      'start': start,
      'end': end,
      'login': self.dj_login,
    }
    self.response.out.write(
      template.render(get_path("charts.html"), template_values))

class HistoryPage(BaseHandler):
  def get(self):
    template_values = {
      'history_selected': True,
      'session': self.session,
    }
    self.response.out.write(
      template.render(get_path("history.html"), template_values))

class ContactPage(BaseHandler):
  def get(self):
    # TODO: Please please fix this. Although realistically it will be fixed on
    # models rework in future.
    # So general MGMT can edit contacts page
    contacts = memcache.get("contacts_page_html")
    if contacts is None:
      contacts = models.BlogPost.all().filter("slug =", "contacts-page").get()
    cache.mcset_t(contacts, 3600, "contacts_page_html")
    template_values = {
      'contact_selected': True,
      'session': self.session,
      'contacts': contacts
    }
    self.response.out.write(
      template.render(get_path("contact.html"), template_values))

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
      'flash': self.flashes,
      'program': program,
      'djs' :  (tuple(Dj.get(dj)
                      for dj in program.dj_list) if program.dj_list
                else None),
      'posts': posts,
      }
    self.response.out.write(
      template.render(get_path("show.html"), template_values))

class TestModels(BaseHandler):
  def get(self):
    from models._raw_models import Play
    self.response.out.write("hey there")
    key = Play.query().get(keys_only=True)
    self.response.out.write(key)
    play = key.get()
    self.response.out.write(play)


## There should never be a need to use the following handler in the future.
# However, it remains for educational purposes.
# Be aware that it's somewhat hackishly written
class SecretPortCoversPage(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self):
    cursor = self.request.get('cursor', None)
    query = models.Album.all()
    if cursor:
      logging.debug("cursor get!")
      query.with_cursor(start_cursor=cursor)
    album = query.get()
    if album:
      new_cursor = query.cursor()
      new_url = '/secret12345qwerty?cursor=%s' % new_cursor
      album = album
      try:
        models.moveCoverToBlobstore(album)
      except:
        pass
      self.response.out.write("""
<html>
<head>
  <meta http-equiv="refresh" content="0;url=%s"/>
</head>
<body>
  <h3>Update Datastore</h3>
  <ul>
    <li>Cursor: %s</li>
    <li>LastCursor: %s</li>
    <li>Updated: %s</li>
  </ul>
</body>
</html>
    """%(new_url, new_cursor, cursor, album.title))
      return
    self.response.out.write("Done")

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
    ('/playexport/?', PlaylistExport),
    ('/fun/?', FunPage),
    ('/charts/?', ChartsPage),
    ('/history/?', HistoryPage),
    ('/contact/?', ContactPage),
    ('/events/?', EventPage),
    ('/albums/([^/]*)/?', ViewCoverHandler),
    ('/callvoice/?', CallVoice),
    ('/testmodels/?', TestModels),
    ], debug=True, config=webapp2conf)
