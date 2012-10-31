#!/usr/bin/env python
#
# Written by Seth Glickman
# & modified by Harrison Chapman
#
##############################
# Some quick notes:
#
# Anything which prints out simplejson.dumps MUST have
# self.response.headers['Content-Type'] = 'text/json'
# preferably towards the beginning.  This allows JQuery on
# the client to read in the data appropriately and act on it.
#
#

import os
import urllib
import datetime
import time
import logging
import json

from google.appengine.api import urlfetch
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import images
from google.appengine.api import files

from google.appengine.ext import ndb

import webapp2
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util

import amazon
import pylast
from handlers import UserHandler
from passwd_crypto import hash_password
from slughifi import slughifi

from models.base_models import (NoSuchEntry,)
from models.dj import (Dj, Permission, InvalidLogin,
                       NoSuchUsername, NoSuchEmail)
from models.tracks import Album, Song, ArtistName
from models.play import Play, Psa, StationID, Program
from models.blog import BlogPost

from configuration import webapp2conf

# This is a decoration for making sure that the user
# is logged in before they view the page.
def login_required(func):
  def wrapper(self, *args, **kw):
    if self.session.has_key("dj"):
      func(self, *args, **kw)
    else:
      self.session.add_flash("You must log in to view this page.")
      self.redirect("/dj/login")
  return wrapper

# This is a decoration which checks if the user is logged in,
# and informs the function of this status.
def check_login(func):
  def wrapper(self, *args, **kw):
    self.dj_login = self.session_has_login()
    func(self, *args, **kw)
  return wrapper

# This is a decoration for making sure that the user has
# the appropriate permissions for viewing the page.
def authorization_required(label):
  def outer_wrapper(func):
    def wrapper(self, *args, **kw):
      if self.session_has_login():
        key = self.dj_key
        if Permission.get_by_title(label).has_dj(key):
          func(self, *args, **kw)
        else:
          self.session.add_flash(
            "You're not authorized to view this page. If you think this is an "
            "error, please send an email to a member of WBOR management.")
          self.redirect("/dj/")
      else:
        self.session.add_flash("You must log in to view this page.")
        self.redirect("/dj/login/")
    return wrapper
  return outer_wrapper

# Convenience method for templates
def get_path(filename):
  return os.path.join(os.path.dirname(__file__), filename)

# http://www.wbor.org/dj/
class MainPage(UserHandler):
  @login_required
  def get(self):
    djkey = self.dj_key

    template_values = {
      'session': self.session,
      'flashes': self.session.get_flashes(),
      'posts': BlogPost.get_last(3),
    }
    permissions = {
      'djs': Permission.DJ_EDIT,
      'programs': Permission.PROGRAM_EDIT,
      'albums': Permission.ALBUM_EDIT,
      'permissions': Permission.PERMISSION_EDIT,
      'genres': Permission.GENRE_EDIT,
      'blogs': Permission.BLOG_EDIT,
      'events': Permission.EVENT_EDIT,}
    permissions_dict = dict(('manage_%s'%key,
                             Permission.get_by_title(perm).has_dj(djkey)) for
                            (key, perm) in permissions.iteritems())
    template_values.update(permissions_dict)
    self.response.out.write(
      template.render(get_path("dj_main.html"), template_values))


# Logs the user out
class Logout(UserHandler):
  def get(self):
    self.session_logout()
    self.flash = ("You have been logged out.")
    self.redirect('/')


# Logs the user in
# get(): the login form
# post(): setting cookies etc.
class Login(UserHandler):
  def get(self):
    if self.session.has_key("dj"):
      self.redirect("/dj/")
    template_values = {
      'session': self.session,
      'flashes': self.session.get_flashes(),
    }
    self.response.out.write(
      template.render(get_path("dj_login.html"), template_values))

  def post(self):
    username = self.request.get("username")
    password = self.request.get("password")

    # Try to log in.
    try:
      dj = Dj.login(username, password)
    except NoSuchUsername:
      self.flash = "Invalid username. Please try again."
      self.redirect('/dj/login/')
      return
    except InvalidLogin:
      self.flash = "Invalid username/password combination. Please try again."
      self.redirect('/dj/login/')
      return

    self.user = dj
    program_list = Program.get_by_dj(dj=dj, num=10)
    if not program_list:
      self.flash = ("You have successfully logged in,"
                    "but you have no associated programs."
                    "You will not be able to do much until"
                    "you have a program.  If you see this message,"
                    "please email <a href='mailto:cmsmith@bowdoin.edu'>"
                    "Connor</a> immediately.")
      self.redirect('/dj/')
      return
    elif len(program_list) == 1:
      self.program = program_list[0]
      self.flash = ("Successfully logged in with program %s."%
                    program_list[0].title)
      self.redirect("/dj/")
      return
    else:
      self.redirect("/dj/selectprogram/")
      return

# Lets a DJ reset his password (to a randomly generated code)
# get(): display a username entry form
# post(): submit the username entry form and send an email to the dj.
class RequestPassword(UserHandler):
  def get(self):
    # If we have a reset_key, then try to reset the password.
    reset_key = self.request.get("reset_key")
    if reset_key:
      username = self.request.get("username")

      try:
        reset_dj = Dj.recovery_login(username, reset_key)
      except NoSuchUsername:
        self.session.add_flash("There is no user by that name")
        self.redirect("/dj/reset/")
        return
      except InvalidLogin:
        self.flash = ("This request is no longer valid, or the key provided"
                      "is somehow corrupt. If clicking the link in your email"
                      "does not work again, perhaps request a new reset.")
        self.redirect("/dj/reset")
        return

      self.set_session_user(reset_dj)
      program_list = Program.get_by_dj(dj=reset_dj)

      if not program_list:
        self.session.add_flash(
          "You have been temporarily logged in. Please change your"
          "password so that you may log in in the future!")
        self.session.add_flash(
          "You will not be able to do much until you have a"
          "program.  If you see this message, please email"
          "<a href='mailto:cmsmith@bowdoin.edu'>Connor</a>"
          "immediately.")
        self.redirect('/dj/myself')
        return
      elif len(program_list) == 1:
        self.set_session_program(program_list[0])
        self.session.add_flash(
          "You have been temporarily logged in. Please change your password so "
          "that you may log in in the future!")
        self.session.add_flash(
          "Logged in with program %s"%program_list[0].title)
        self.redirect("/dj/myself")
        return
      else:
        self.session.add_flash(
          "You have been temporarily logged in. Please change your password so "
          "that you may log in in the future!")
        self.redirect("/dj/myself")
        return
    else:
      if self.session_has_login():
        self.redirect("/dj/")
        return
      template_values = {
        'session': self.session,
        'flash': self.flashes,
        }
      self.response.out.write(
        template.render(get_path("dj_reset_password.html"),
                        template_values))

  def post(self):
    if self.request.get("submit") != "Request Reset":
      self.session.add_flash("There was an error, please try again")
      self.redirect("/dj/reset/")
      return

    # Check that the user exists and information is valid
    username = self.request.get("username")
    email = self.request.get("email")
    reset_dj = None

    try:
      reset_dj = Dj.get_by_username(username)
    except NoSuchUsername as e:
      self.session.add_flash(str(e))
      self.redirect("/dj/reset")
      return
    if not reset_dj.email_matches(email):
      self.session.add_flash(
        "The email you have entered does not match our records. "
        "Check, and try, again.")

    # Generate a key to be sent to the user and add the
    # new password request to the database
    reset_key = ''.join(random.choice(string.ascii_letters +
                                      string.digits) for x in range(20))
    reset_url="%s/dj/reset/?username=%s&reset_key=%s"%(
      self.request.host_url, username, reset_dj.reset_password())
    mail.send_mail(
      sender="WBOR <password-reset@wbor-hr.appspotmail.com>",
      to=email.strip(),
      subject="You've requested to reset your password!",
      body="""
Hello!

Someone has requested to reset your password for wbor.org. In order to do so,
please click on the following link or paste it into your address bar:
%s

If you were not who requested this password reset, then please just ignore
this email.

Thank you!
The WBOR.org Team
"""%reset_url)
    self.session.add_flash(
      "Request successfully sent! Check your mail, and be sure to doublecheck "
      "the spam folder in case.")
    self.redirect("/")

# Lets the user select which program they've logged in as
class SelectProgram(UserHandler):
  @login_required
  def get(self):
    program_list = Program.get_by_dj(dj=self.dj_key)
    if len(program_list) <= 1:
      self.session.add_flash(
        "You don't have more than one radio program to choose between.")
      self.redirect("/dj/")
      return
    template_values = {
      'program_list': program_list,
      'session': self.session,
      'flash': self.flashes,
      'posts': BlogPost.get_last(num=1)
    }
    self.response.out.write(template.render(get_path("dj_selectprogram.html"),
      template_values))

  @login_required
  def post(self):
    program_key = self.request.get("programkey")
    program = Program.get(key=program_key)
    if not program:
      self.session.add_flash(
        "An error occurred retrieving your program.  Please try again.")
      self.redirect("/dj/")
      return
    self.set_session_program(program)
    self.session.add_flash(
      "The current program has been set to %s."%program.title)
    self.redirect("/dj/")


# The main portion of what a DJ sees on the website
# get(): the form for charting a song; displays current playlist under form.
# post(): charts the song/psa/stationID
class ChartSong(UserHandler):
  @login_required
  def get(self):
    if not self.session_has_program():
      self.session.add_flash(
        "You can't chart songs until you have an associated program in the "
        "system.  Please contact a member of management immediately.")
      self.redirect("/dj/")
      return

    memcache_key = "playlist_html_%s"%self.session.get('program').get('key')
    playlist_html = memcache.get(memcache_key)
    if not playlist_html:
      playlist_html = template.render("dj_chartsong_playlist_div.html",
        {'playlist': Play.get_last(num=50,
                                   program=Program.get(self.program_key),
                                   after=(datetime.date.today())),
         }
      )
      memcache.set(memcache_key, playlist_html, 60 * 60 * 24)

    last_psa = None #Psa.get_last() # cache.getLastPsa()
    new_albums = None
    #new_song_div_html = memcache.get("new_song_div_html")
    album_songs = []
    new_song_div_html = None
    if not new_song_div_html:
      new_albums = Album.get_new() #by_artist=True)
      if new_albums:
        logging.debug(new_albums)
        album_songs = Song.get(new_albums[0].tracklist)
      new_song_div_html = template.render(
        get_path("dj_chartsong_newsongdiv.html"),
        {'new_albums': new_albums,
         'album_songs': album_songs,})
      memcache.set("new_song_div_html", new_song_div_html)

    template_values = {
      'last_psa': last_psa,
      'playlist_html': playlist_html,
      'session': self.session,
      'flash': self.flashes,
      'new_albums': new_albums,
      'album_songs': album_songs,
      'new_song_div_html': new_song_div_html,
    }
    self.response.out.write(
      template.render(get_path("dj_chartsong.html"), template_values))

  @login_required
  def post(self):
    if self.request.get("submit") == "Chart Song":
      # Charting a song, not a PSA or ID
      track_artist = self.request.get("artist").encode("latin1", 'replace')
      trackname = self.request.get("trackname").encode("latin1", 'replace')
      isNew = int(self.request.get("isNew"))
      if isNew > 0:
        # if it's "new", the album should be in the datastore already with
        # a valid key.
        album = Album.get(self.request.get("album_key"))
        if not album:
          self.session.add_flash(
            "Missing album information for new song, please try again.")
          self.redirect("/dj/chartsong/")
          return
        # likewise, the song should be in the datastore already with a
        # valid key.
        song = Song.get(self.request.get("song_key"))
        if not song:
          self.session.add_flash(
            "An error occurred trying to fetch the song, please try again.")
          self.redirect("/dj/chartsong/")
          return
        logging.debug(song)
        trackname = song.title
        track_artist = song.artist
        Play.new(song=song, program=self.program_key,
                 play_date=datetime.datetime.now(), is_new=True,
                 artist=album.artist).put()
      else:
        # a song needs to have an artist and a track name
        if not track_artist or not trackname:
          self.session.add_flash(
            "Missing track information, please fill out both fields.")
          self.redirect("/dj/chartsong/")
          return
        song = Song.new(title=trackname, artist=track_artist)
        song.put()

        Play.new(song=song, program=self.program_key,
                 play_date=datetime.datetime.now(), isNew=False,
                 artist=track_artist).put()
      memcache_key = "playlist_html_%s"%self.session.get('program').get('key')
      playlist_html = template.render(
        "dj_chartsong_playlist_div.html",
        {'playlist': Play.get_last(
          program=self.program_key,
          after=(datetime.datetime.now() - datetime.timedelta(days=1)))})
      memcache.set(memcache_key, playlist_html, 60 * 60 * 24)
      ArtistName.try_put(track_artist)

      try:
        # last.fm integration
        lastfm_username = "wbor"
        lastfm_password = "WBOR911!"
        lastfm_api_key = "59925bd7155e59bd39f14adcb70b7b77"
        lastfm_secret_key = "6acf5cc79a41da5a16f36d5baac2a484"
        network = pylast.get_lastfm_network(api_key=lastfm_api_key,
          api_secret=lastfm_secret_key,
          username=lastfm_username,
          password_hash=pylast.md5(lastfm_password))
        scrobbler = network.get_scrobbler("tst", "1.0")
        scrobbler.scrobble(track_artist, trackname, int(time.time()),
          pylast.SCROBBLE_SOURCE_USER, pylast.SCROBBLE_MODE_PLAYED, 60)
        self.session.add_flash(
          "%s has been charted and scrobbled to Last.FM,"
          " and should show up below."%trackname)
      except:
        # just catch all errors with the last.fm; it's not that important that
        # everything get scrobbled exactly; plus this is like the #1 source
        # of errors in charting songs.
        self.session.add_flash(
          "%s has been charted, but was not scrobbled to Last.FM"%
          trackname)
      self.redirect("/dj/chartsong/")
      return
      # End of song charting.
    elif self.request.get("submit") == "Station ID":
      # If the DJ has recorded a station ID
      station_id = models._raw_models.StationID(program=self.program_key,
                                    play_date=datetime.datetime.now())
      station_id.put()
      self.session.add_flash("Station ID recorded.")
      self.redirect("/dj/chartsong/")
      return
    elif self.request.get("submit") == "PSA":
      # If the DJ has recorded a PSA play
      psa_desc = self.request.get("psa_desc")
      Psa.new(desc=psa_desc, program=self.program_key).put()
      self.session.add_flash("PSA recorded.")
      self.redirect("/dj/chartsong/")
      return

# Displays log of PSA and Station ID records for a given two-week period.
# /dj/logs/?
# get(): Print log for the last two weeks, display form for choosing endpoint.
# post(): Print log of two-week period.
class ViewLogs(UserHandler):
  @login_required
  def get(self):
    start = datetime.datetime.now() - datetime.timedelta(weeks=2)
    end = datetime.datetime.now()
    psas = models.getPSAsInRange(start=start, end=end)
    ids = models.getIDsInRange(start=start, end=end)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'psas': psas,
      'ids': ids,
      'start': start,
      'end': end,
    }
    self.response.out.write(
      template.render(get_path("dj_logs.html"), template_values))

  @login_required
  def post(self):
    try:
      start = datetime.datetime.strptime(
        self.request.get("start_date"), "%m/%d/%Y")
    except ValueError:
      self.session.add_flash(
        "Unable to select date. Enter a date in the form mm/dd/yyyy.")
      self.redirect("/dj/logs/")
      return
    end = start + datetime.timedelta(weeks=2)
    psas = models.getPSAsInRange(start=start, end=end)
    ids = models.getIDsInRange(start=start, end=end)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'psas': psas,
      'ids': ids,
      'start': start,
      'end': end,
    }
    self.response.out.write(
      template.render(get_path("dj_logs.html"), template_values))

# For administration, manages the DJs in the system.
# get(): Displays list of current DJs for editing/deletion
# post(): Adds a new DJ
class ManageDJs(UserHandler):
  @authorization_required("Manage DJs")
  def get(self):
    dj_list = [] #Dj.getAll() # This is TERRIBLE PRACTICE

    template_values = {
      'dj_list': dj_list,
      'session': self.session,
      'flash': self.flashes,
      'posts': BlogPost.get_last(num=3),
    }
    self.response.out.write(template.render(get_path("dj_manage_djs.html"),
      template_values))

  @authorization_required("Manage DJs")
  def post(self):
    if self.request.get("submit") != "Add DJ":
      self.session.add_flash("There was an error, please try again.")
      self.redirect("/dj/djs/")
    else:
      fullname = self.request.get("fullname")
      email = self.request.get("email")
      username = self.request.get("username")
      password = self.request.get("password")

      if not email:
        self.session.add_flash("Please enter a valid email address.")
        self.redirect("/dj/djs")
        return
      if not username:
        self.session.add_flash("Please enter a valid username.")
        self.redirect("/dj/djs")
        return
      if not fullname:
        self.session.add_flash("Please enter a valid full name.")
        self.redirect("/dj/djs")
        return
      if not password:
        self.session.add_flash("Please enter a valid password.")
        self.redirect("/dj/djs")
        return
      if not password == self.request.get("confirm"):
        self.session.add_flash("Passwords do not match.")
        self.redirect("/dj/djs")
        return

      try:
        dj = Dj.get_by_email(email)
      except NoSuchEmail:
        dj = None

      if dj is not None:
        self.session.add_flash(
          "A DJ with email address %s already exists: %s, username %s" %
          (dj.email, dj.fullname, dj.username))
        self.redirect("/dj/djs")
        return

      try:
        dj = Dj.get_by_username(username)
      except NoSuchUsername:
        dj = None

      if dj is not None:
        self.session.add_flash(
          "A DJ with username %s already exists: %s, email address %s" %
          (dj.username, dj.fullname, dj.email))
        self.redirect("/dj/djs")
        return

      # If both username and email address are new, then we can add them
      dj = Dj.new(fullname=fullname,
                  email=email,
                  username=username,
                  password=password)
      dj.put()

      self.session.add_flash(dj.fullname + " successfully added as a DJ.")
      self.redirect("/dj/djs/")


# Displays and edits a DJ's details in the datastore
# get(): Display DJ's details
# post(): Save changes to DJ's details
class EditDJ(UserHandler):
  @authorization_required("Manage DJs")
  def get(self, dj_key):
    dj = Dj.get(dj_key)
    # TODO: CRITICAL: CRITICAL: Don't show every goddamn DJ
    dj_list = [] # Seriously screw this crap
    #dj_list = cache.getAllDjs()
    if not dj:
      self.session.add_flash(
          "The DJ specified (" + dj_key +
          ") does not exist.  Please try again.")
      self.redirect("/dj/djs/")
    else:
      template_values = {
        'dj_list': dj_list,
        'dj': dj,
        'session': self.session,
        'flash': self.flashes,
        'posts': BlogPost.get_last(num=3),
      }
      self.response.out.write(
          template.render(get_path("dj_manage_djs.html"), template_values))

  @authorization_required("Manage DJs")
  def post(self, dj_key):
    dj = Dj.get(dj_key)
    if (dj is None) or (self.request.get("submit") != "Edit DJ" and
                        self.request.get("submit") != "Delete DJ"):
      self.session.add_flash(
          "There was an error processing your request.  Please try again.")

    elif self.request.get("submit") == "Edit DJ":
      fullname = self.request.get("fullname")
      email = self.request.get("email")
      username = self.request.get("username")
      password = self.request.get("password")

      if password is not None:
        if not password == self.request.get("confirm"):
          self.session.add_flash("New passwords do not match.")
          self.redirect("/dj/djs")
          return

      # Edit the dj
      dj = Dj.put(fullname=fullname,
                  email=email,
                  username=username,
                  password=password,)

      self.session.add_flash(fullname + " has been successfully edited.")
    elif self.request.get("submit") == "Delete DJ":
      dj.delete()
      self.session.add_flash(fullname + " has been successfully deleted.")
    self.redirect("/dj/djs/")


# Displays current programs and adds new programs
# get(): display current programs
# post(): add new program
class ManagePrograms(UserHandler):
  @authorization_required("Manage Programs")
  def get(self):
    new_programs = Program.get(num=5)

    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'new_programs': new_programs,
    }
    self.response.out.write(
        template.render(get_path("dj_manage_programs.html"), template_values))

  @authorization_required("Manage Programs")
  def post(self):
    if (self.request.get("submit") != "Add Program"):
      self.session.add_flash(
          "There was an error processing your request. Please try again.")
    else:
      slug = self.request.get("slug")
      program = Program.get(slug=slug)
      if program:
        self.session.add_flash(("Program \"%s\" already exists with slug %s."%
                          (program.title, slug)))
        self.redirect("/dj/programs/")
        return

      # Set up the program entry, and then put it in the DB
      program = Program.new(title=self.request.get("title"),
                            slug=self.request.get("slug"),
                            desc=self.request.get("desc"),
                            dj_list=self.request.get_all("djkey"),
                            page_html=self.request.get("page_html"),
                            current=bool(self.request.get("current")))
      program.put()

      self.session.add_flash(
          "%s was successfully created associated a program. "
          "Click <a href='/dj/programs/%s'>here</a> "
          "to edit it (you probably want to do "
          "this as there are no DJs on it currently)."%
          (program.title, str(program.key)))

    self.redirect('/dj/programs/')


# Displays and edits details of a program.
class EditProgram(UserHandler):
  @authorization_required("Manage Programs")
  def get(self, program_key):
    program = Program.get(program_key)
    if not program:
      self.session.add_flash(
        "Unable to find program (" + program_key + ").  Please try again.")
      self.redirect("/dj/programs/")
    else:
      new_programs = Program.get(num=5)
      template_values = {
        'program_djs': [Dj.get(dj) for dj in program.dj_list],
        'program': program,
        'session': self.session,
        'flash': self.flashes,
        'new_programs': new_programs
      }
      self.response.out.write(
        template.render(get_path("dj_manage_programs.html"), template_values))

  @authorization_required("Manage Programs")
  def post(self, program_key):
    program = Program.get(program_key)
    if (not program or
        (self.request.get("submit") != "Edit Program" and
         self.request.get("submit") != "Delete Program")):
      self.session.add_flash(
        "There was an error processing your request. Please try again.")
    elif self.request.get("submit") == "Edit Program":
      program.title = self.request.get("title")
      program.slug = self.request.get("slug")
      program.desc = self.request.get("desc")
      program.page_html = self.request.get("page_html")
      program.dj_list = self.request.get_all("djkey")
      program.current = bool(self.request.get("current"))
      program.put()
      self.session.add_flash(program.title + " successfully edited.")
    elif self.request.get("submit") == "Delete Program":
      program.delete()
      self.session.add_flash(program.title + " successfully deleted.")
    self.redirect("/dj/programs/")


class MySelf(UserHandler):
  @login_required
  def get(self):
    dj = Dj.get(self.dj_key)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'dj': dj,
      'posts': BlogPost.get_last(1),
    }
    self.response.out.write(
      template.render(get_path("dj_self.html"), template_values))

  @login_required
  def post(self):
    dj_key = ndb.Key(urlsafe=self.request.get("dj_key"))
    dj = Dj.get(dj_key)

    if not dj:
      self.session.add_flash(
        "An error occurred processing your request.  Please try again.")
      self.redirect("/dj/myself")
      return
    dj.fullname = self.request.get("fullname")

    email = self.request.get("email")
    if email[-1] == "@":
      email += "bowdoin.edu"
    if "@" not in email:
      email += "@bowdoin.edu"
    duplicate_dj_key = Dj.get_key_by_email(email)
    if duplicate_dj_key and duplicate_dj_key != dj.key:
      error = True
      self.session.add_flash(
        "The email specified is already in use by another DJ.  "
        "Please enter a unique one.")
    dj.email = email

    username = self.request.get("username")
    duplicate_dj_key = Dj.get_key_by_username()
    if duplicate_dj_key and duplicate_dj_key != dj.key:
      error = True
      self.session.add_flash(
        "The username specified is already in use by another DJ.  "
        "Please choose another.")
    dj.username = username

    if error:
      self.redirect("/dj/myself")
      return
    if self.request.get("password"):
      if not self.request.get("password") == self.request.get("confirm"):
        self.session.add_flash("New passwords do not match.")
        self.redirect("/dj/myself")
        return
      else:
        dj.password = self.request.get("password")

    dj.put()
    self.session.add_flash("You have successfully updated your profile.")
    self.redirect("/dj/")

# Lets a DJ edit the description etc. of their show.
class MyShow(UserHandler):
  @login_required
  def get(self):
    program = cache.getProgram(self.program_key)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'program': program,
      'posts': BlogPost.get_last(2),
    }
    self.response.out.write(
      template.render(get_path("dj_myshow.html"), template_values))

  @login_required
  def post(self):
    program = cache.getProgram(self.request.get("program_key"))
    if not program:
      self.session.add_flash("Unable to find program.")
      self.redirect("/dj/myshow")
      return
    slug = self.request.get("slug")
    p = Program.get_by_slug(slug)
    if p and program.key != p.key:
      self.session.add_flash("There is already a program with slug \""
                             + slug + "\".")
      self.redirect("/dj/myshow")
      return
    program.title = self.request.get("title")
    program.slug = self.request.get("slug")
    program.desc = self.request.get("desc")
    program.page_html = self.request.get("page_html")
    program.put()
    self.set_session_program(program)
    self.session.add_flash("Program successfully changed.")
    self.redirect("/dj/myshow")


# How DJs with the appropriate permissions can create a blog post
# get(): Display "new blog post" form
# post(): Save as post, redirect to home page to display their hard work
class NewBlogPost(UserHandler):
  @authorization_required("Manage Blog")
  def get(self):
    posts = BlogPost.get_last(2)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'posts': posts,
    }
    self.response.out.write(
        template.render(get_path("dj_createpost.html"), template_values))

  @authorization_required("Manage Blog")
  def post(self):
    errors = ""
    title = self.request.get("title")
    text = self.request.get("text")
    post_date = datetime.datetime.now();
    slug = self.request.get("slug")
    post = BlogPost.new(
      title=title,
      text=text,
      post_date=post_date,
      slug=slug)
    posts = BlogPost.get_last(num=2)
    if BlogPost.get_by_slug(slug, post_date=post_date):
      errors = ("Error: this post has a duplicate slug to another post from "
                "the same day.  This probably shouldn't happen often.")
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'errors': errors,
      'post': post,
      'posts': posts,
    }
    if errors:
      self.response.out.write(
          template.render(get_path("dj_createpost.html"), template_values))
    else:
      post.put()
      self.session.add_flash("Post \"%s\" successfully added." % title)
      self.redirect("/")



class EditBlogPost(UserHandler):
  @authorization_required("Manage Blog")
  def get(self, date_string, slug):
    post_date = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    post = BlogPost.get_by_slug(slug, post_date=post_date)
    if not post:
      self.session.add_flash(
          "The post you're looking for does not exist.  "
          "But you can look at actual posts below :)")
      self.redirect("/")
      return
    posts = BlogPost.get_last(num=2)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'post': post,
      'editing': True,
      'posts': posts,
    }
    self.response.out.write(
      template.render(get_path("dj_createpost.html"), template_values))

  @authorization_required("Manage Blog")
  def post(self, date_string, slug):
    errors = ""
    title = self.request.get("title")
    text = self.request.get("text")
    slug = self.request.get("slug")
    post_key = ndb.Key(urlsafe=self.request.get("post_key"))
    post = BlogPost.get(post_key)
    if not post:
      self.session.add_flash(
        "The post you're looking for does not exist.  "
        "Something strange has occurred.")
      # this shouldn't happen unless people are fiddling around with
      # POST values by hand I think
      self.redirect("/")
      return
    if self.request.get("submit") == "Delete Post":
      post.delete()
      self.session.add_flash("Post deleted.")
      self.redirect("/")
      return
    duplicate = BlogPost.get_by_slug(slug, post_date=post.post_date)
    old_slug = post.slug
    post.slug = slug
    if duplicate:
      if duplicate.key != post_key:
        errors = ("This post has a duplicate slug to another post "
                  "from the same day.  Please rename the slug.")
        post.slug = old_slug
    post.title = title
    post.text = text
    posts = BlogPost.get_last(num=2)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'errors': errors,
      'post': post,
      'editing': True,
      'posts': posts,
    }
    if errors:
      self.response.out.write(
        template.render(get_path("dj_createpost.html"), template_values))
    else:
      post.put()
      self.session.add_flash("Successfully altered post %s" % post.title)
      self.redirect("/")


class RemovePlay(UserHandler):
  @login_required
  def post(self):
    self.response.headers['Content-Type'] = 'text/json'
    Play.delete_key(self.request.get("play_key"), program=self.program_key)
    memcache.delete("playlist_html_%s"%self.program_key)
    self.response.out.write(json.dumps({
          'status': "Successfully deleted play."
          }))

class NewEvent(UserHandler):
  @authorization_required("Manage Events")
  def get(self):
    posts = BlogPost.get_last(num=2)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'editing': False,
      'hours': [str(i).rjust(2, "0") for i in range(24)],
      'minutes': [str(i).rjust(2, "0") for i in range(0, 60, 15)],
      'posts': posts,
    }
    self.response.out.write(
        template.render(get_path("dj_create_event.html"), template_values))

  @authorization_required("Manage Events")
  def post(self):
    title = self.request.get('title')
    desc = self.request.get('desc')
    url = self.request.get('url')
    event_date = self.request.get("date")
    hours = self.request.get("hour")
    minutes = self.request.get("minute")
    date_string = event_date + " " + hours + ":" + minutes
    try:
      event_date = datetime.datetime.strptime(date_string, "%m/%d/%Y %H:%M")
    except ValueError:
      self.session.add_flash(
          "Unable to work with date \"%s\". Enter a valid date in the form "
          "mm/dd/yyyy, and an hour/minute as well." % date_string)
      self.redirect("/dj/event/")
      return
    event = models.Event(event_date=event_date, title=title, url=url, desc=desc)
    event.put()
    self.session.add_flash("Event %s successfully created." % title)
    self.redirect("/dj/")


class EditEvent(UserHandler):
  @authorization_required("Manage Events")
  def get(self, event_key):
    event = models.Event.get(event_key)
    if not event:
      self.session.add_flash(
          "Unable to find the requested event.  Please try again.")
      self.redirect("/dj/")
      return
    day = event.event_date.strftime("%m/%d/%Y")
    hour = event.event_date.strftime("%H")
    minute = event.event_date.strftime("%M")
    posts = BlogPost.get_last(num=2)
    template_values = {
      'session': self.session,
      'flash': self.flashes,
      'editing': True,
      'event': event,
      'day': day,
      'hour': hour,
      'minute': minute,
      'hours': [str(i).rjust(2, "0") for i in range(24)],
      'minutes': [str(i).rjust(2, "0") for i in range(0, 60, 15)],
      'posts': posts,
    }
    self.response.out.write(
        template.render(get_path("dj_create_event.html"), template_values))

  @authorization_required("Manage Events")
  def post(self, event_key):
    event = models.Event.get(self.request.get("event_key"))
    if not event:
      self.session.add_flash(
          "Unable to find the requested event.  Please try again.")
      self.redirect("/dj/")
      return
    if self.request.get("submit") == "Delete Event":
      event.delete()
      self.session.add_flash("Event %s deleted." % event.title)
      self.redirect("/dj/")
      return
    event.title = self.request.get("title")
    event.desc = self.request.get("desc")
    event.url = self.request.get("url")
    event_date = self.request.get("date")
    hours = self.request.get("hour")
    minutes = self.request.get("minute")
    date_string = event_date + " " + hours + ":" + minutes
    try:
      event_date = datetime.datetime.strptime(date_string, "%m/%d/%Y %H:%M")
    except ValueError:
      self.session.add_flash(
          "Unable to work with date. Enter a date in the form mm/dd/yyyy, and "
          "an hour/minute as well.")
      self.redirect("/dj/event/")
      return
    event.event_date = event_date
    event.put()
    self.session.add_flash("Event %s updated." % event.title)
    self.redirect("/events/")


# Rules for who can access what.
# get(): Display permissions along with DJs
# post(): AJAXically adding/removing DJs to permissions.
class ManagePermissions(UserHandler):
  @authorization_required("Manage Permissions")
  def get(self):
    permissions = Permission.get_all()
    template_values = {
      'permissions': [{
        'key': p.key,
        'title': p.title,
        'dj_list': [Dj.get(d) for d in p.dj_list],
        } for p in permissions],
      'session': self.session,
      'flash': self.flashes,
      'posts': BlogPost.get_last(num=2),
    }
    self.response.out.write(
        template.render(get_path("dj_permissions.html"), template_values))

  @authorization_required("Manage Permissions")
  def post(self):
    self.response.headers['Content-Type'] = 'text/json'
    dj_key = self.request.get("dj_key")
    dj = Dj.get(dj_key)
    errors = "";
    if not dj:
      errors = "Unable to find DJ. "
    permission_key = self.request.get("permission_key")
    permission = Permission.get(keys=permission_key)
    if not permission:
      errors = "Unable to find permission."
    if errors:
      self.response.out.write(json.dumps({
        'err': errors,
      }))
      return
    action = self.request.get("action")
    if action == "add":
      if permission.has_dj(dj):
        errors = ("%s is already in the %s permission list."%
                  (dj.fullname, permission.title))
      else:
        permission.add_dj(dj)
        status = ("Successfully added %s to %s permission list."%
                  (dj.fullname, permission.title))
    if action == "remove":
      if dj.key not in permission.dj_list:
        errors = (dj.fullname + " was not in the " +
                  permission.title + " permission list.")
      else:
        permission.remove_dj(dj.key)
        status = ("Successfully removed " + dj.fullname + " from " +
                  permission.title + " permission list.")
    if errors:
      self.response.out.write(json.dumps({
        'err': errors,
      }))
    else:
      permission.put()
      self.response.out.write(json.dumps({
        'err': '',
        'msg': status
      }))


# Add and edit which albums are marked as "new"
# get(): Display list of new albums
# post(): One of four actions:
#     - add: AJAXically adds a new album to the datastore.
#     - makeOld: AJAXically removes "new" status from an album
#     - makeNew: AJAXically adds "new" status back to an album if made
# old by mistake
#     - manual: AJAX - adds an album which has been typed in by hand.

class ManageAlbums(UserHandler):
  @authorization_required("Manage Albums")
  def get(self):
    new_album_list = None
 #   new_album_html = memcache.get("manage_new_albums_html")
 #   if not new_album_html:
    new_album_list = Album.get_new()
    new_album_html = template.render(
        get_path("dj_manage_new_albums_list.html"),
        {'new_album_list': new_album_list})
    memcache.set("manage_new_albums_html", new_album_html)
    template_values = {
      'new_album_list': new_album_list,
      'new_album_html': new_album_html,
      'session': self.session,
      'flash': self.flashes,
    }
    self.response.out.write(
        template.render(get_path("dj_manage_albums.html"), template_values))

  @authorization_required("Manage Albums")
  def post(self):
    self.response.headers['Content-Type'] = 'text/json'
    action = self.request.get("action")

    if action == "add":
      self.response.headers['Content-Type'] = 'text/json'
      # asin is Amazon's special ID number.
      # unique to the product (but different versions of the same
      # thing will have different ASIN's, like a vinyl vs. a cd vs. a
      # special edition etc.)
      asin = self.request.get("asin")
      album = Album.get(asin=asin)
      if album:
        album.set_new()
        album.put()
        self.response.out.write(json.dumps({
          'msg': "Success, already existed. The album was re-set to new."
        }))
        return

      # Grab the product details from Amazon to save to our datastore.
      i = amazon.productSearch(asin)
      try:
        i = i[0]
      except IndexError:
        self.response.out.write(json.dumps({
          'err': ("An error occurred.  Please try again, or if this keeps "
                  "happening, select a different album.")
        }))
        return
      # this overly complicated code sets up the json data associated with
      # the album we're adding.  It pulls the appropriate values from the
      # XML received.
      json_data = {
        'small_pic': i.getElementsByTagName(
          "SmallImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
        'large_pic': i.getElementsByTagName(
          "LargeImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
        'artist': i.getElementsByTagName("Artist")[0].firstChild.nodeValue,
        'title': i.getElementsByTagName("Title")[0].firstChild.nodeValue,
        'asin': i.getElementsByTagName("ASIN")[0].firstChild.nodeValue,
        'tracks': [t.firstChild.nodeValue
                   for t in i.getElementsByTagName("Track")],
      }
      largeCover = urlfetch.fetch(json_data['large_pic']).content
      large_filetype = json_data['large_pic'][-4:].strip('.')
      smallCover = urlfetch.fetch(json_data['small_pic']).content
      small_filetype = json_data['small_pic'][-4:].strip('.')

      title = json_data['title']
      artist = json_data['artist']
      tracks = json_data['tracks']

    elif action == "makeNew":
      # We're marking an existing album as "new" again
      self.response.headers['Content-Type'] = 'text/json'
      key = self.request.get("key")
      try:
        album = Album.get(key)
        album.set_new()
        album.put()
      except:
        self.response.out.write(
            json.dumps({'err': "Album not found. Please try again."}))
        return

      self.response.out.write(json.dumps({'msg': "Made new."}))
      return

    elif action == "makeOld":
      # We're removing the "new" marking from an album
      self.response.headers['Content-Type'] = 'text/json'
      key = self.request.get("key")
      try:
        album = Album.get(key)
        album.unset_new()
        album.put()
      except NoSuchEntry:
        pass
      self.response.out.write(json.dumps({'msg': "Made old."}))
      return

    elif action == "manual":
      # The user has typed in the title, the artist, all track names,
      # and provided a cover image URL.
      tracks = self.request.get("track-list")
      tracks = [line.strip() for line in tracks.splitlines() if
                len(line.strip()) > 0]
      cover_url = self.request.get("cover_url")
      if not cover_url:
        cover_url = "/static/images/noalbumart.png"

      # Try to fetch the cover art, if possible
      try:
        largeCover = urlfetch.fetch(cover_url).content
      except urlfetch.ResponseTooLargeError:
        if self.request.get("ajax"):
          self.response.out.write(
            json.dumps({
                'msg': ("The image you provided was too large. "
                        "There is a 1MB limit on cover artwork. "
                        "Try a different version with a reasonable size."),
                'result': 1,}))
        else:
          self.session.add_flash(
              "The image you provided was too large. "
              "There is a 1MB limit on cover artwork. "
              "Try a different version with a reasonable size.")
          self.redirect("/dj/albums/")
        return
      except urlfetch.InvalidURLError:
        if self.request.get("ajax"):
          self.response.out.write(
            json.dumps({
                'msg': ("The URL you provided could not be downloaded. "
                        "Hit back and try again."),
                'result': 1,}))
        else:
          self.session.add_flash("The URL you provided could "
                                 "not be downloaded. "
                                 "Try again.")
          self.redirect("/dj/albums/")
        return
      except urlfetch.DownloadError:
        if self.request.get("ajax"):
          self.response.out.write(
            json.dumps({
              'msg': ("The URL you provided could not be downloaded. "
                      "Hit back and try again."),
              'result': 1,}))
        else:
          self.session.add_flash("The URL you provided could "
                                 "not be downloaded. Try again.")
          self.redirect("/dj/albums")
        return

      large_filetype = cover_url[-4:].strip('.')
      smallCover = images.resize(largeCover, 100, 100)
      small_filetype = large_filetype

      title = self.request.get('title')
      artist = self.request.get('artist')
      asin = None


    ## Create the actual objects and store them
    fn = "%s_%s"%(slughifi(artist), slughifi(title))
    # Create the file nodes in the blobstore
    # _blobinfo_uploaed_filename WILL change in the future.
    small_file = files.blobstore.create(
      mime_type=small_filetype,
      _blobinfo_uploaded_filename="%s_small.png"%fn)
    large_file = files.blobstore.create(
      mime_type=large_filetype,
      _blobinfo_uploaded_filename="%s_big.png"%fn)

    # Write the images
    with files.open(small_file, 'a') as small:
      small.write(smallCover)
    with files.open(large_file, 'a') as large:
      large.write(largeCover)

    files.finalize(small_file)
    files.finalize(large_file)

    cover_small=files.blobstore.get_blob_key(small_file)
    cover_large=files.blobstore.get_blob_key(large_file)

    # Finally, create the album
    album = Album.new(title=title,
                      artist=artist,
                      tracks=tracks,
                      asin=asin,
                      cover_small=cover_small,
                      cover_large=cover_large)
    album.put()

    if self.request.get("ajax"):
      self.response.out.write(
        json.dumps({
            'msg': ("The album \"%s\" by %s was successfully added."%
                    (title, artist)),
            'result': 0,}))


app = webapp2.WSGIApplication([
    ('/dj/?', MainPage),
    ('/dj/login/?', Login),
    ('/dj/logout/?', Logout),
    ('/dj/djs/?', ManageDJs),
    ('/dj/djs/([^/]*)/?', EditDJ),
    ('/dj/programs/?', ManagePrograms),
    ('/dj/programs/([^/]*)/?', EditProgram),
    ('/dj/chartsong/?', ChartSong),
    ('/dj/albums/?', ManageAlbums),
    ('/dj/selectprogram/?', SelectProgram),
    ('/dj/logs/?', ViewLogs),
    ('/dj/permissions/?', ManagePermissions),
    ('/dj/myshow/?', MyShow),
    ('/blog/([^/]*)/([^/]*)/edit/?', EditBlogPost),
    ('/dj/newpost/?', NewBlogPost),
    ('/dj/event/?', NewEvent),
    ('/dj/myself/?', MySelf),
    ('/dj/removeplay/?', RemovePlay),
    ('/dj/event/([^/]*)/?', EditEvent),
    ('/dj/reset/?.*', RequestPassword),
    ], debug=True, config=webapp2conf)
