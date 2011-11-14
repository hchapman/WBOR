#!/usr/bin/env python
#
# Written by Seth Glickman
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
import models
import cache
import urllib
import hmac
import base64
import hashlib
import datetime
import time
import pylast
import amazon
import logging
import random
import string
from xml.dom import minidom
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
import webapp2
from google.appengine.ext.webapp import util
from google.appengine.api import mail
from django.utils import simplejson
from google.appengine.api import memcache
from passwd_crypto import hash_password, check_password
from handlers import BaseHandler, UserHandler

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
        perm = models.getPermission(label)
        if key in perm.dj_list:
          func(self, *args, **kw)
        else:
          self.session.add_flash("You're not authorized to view this page. If you think this is an error, please send an email to a member of WBOR management.")
          self.redirect("/dj/")
      else:
        self.session.add_flash("You must log in to view this page.")
        self.redirect("/dj/login/")
    return wrapper
  return outer_wrapper

# Convenience method for templates
def getPath(filename):
  return os.path.join(os.path.dirname(__file__), filename)

# http://www.wbor.org/dj/
class MainPage(UserHandler):
  @login_required
  def get(self):
    djkey = self.dj_key
    template_values = {
      'session': self.session,
      'flashes': self.session.get_flashes(),
      'manage_djs': models.hasPermission(djkey, "Manage DJs"),
      'manage_programs': models.hasPermission(djkey, "Manage Programs"),
      'manage_permissions': models.hasPermission(djkey, "Manage Permissions"),
      'manage_albums': models.hasPermission(djkey, "Manage Albums"),
      'manage_genres': models.hasPermission(djkey, "Manage Genres"),
      'manage_blog': models.hasPermission(djkey, "Manage Blog"),
      'manage_events': models.hasPermission(djkey, "Manage Events"),
      'posts': models.getLastPosts(3),
    }
    self.response.out.write(template.render(getPath("dj_main.html"), template_values))
  

# Logs the user out
class Logout(UserHandler):
  def get(self):
    self.session_logout()
    self.session.add_flash("You have been logged out.")
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
    self.response.out.write(template.render(getPath("dj_login.html"), template_values))
  
  def post(self):
    username = self.request.get("username")
    password = self.request.get("password")
    dj = models.djLogin(username, password)
    if not dj:
      self.session.add_flash("Invalid username/password combination. Please try again.")
      self.redirect('/dj/login/')
      return
    self.set_session_user(dj)
    programList = models.getProgramsByDj(dj)
    if not programList:
      self.session.add_flash("You have successfully logged in, but you have no associated programs.  You will not be able to do much until you have a program.  If you see this message, please email <a href='mailto:cmsmith@bowdoin.edu'>Connor</a> immediately.")
      self.redirect('/dj/')
      return
    elif len(programList) == 1:
      self.set_session_program(programList[0])
      self.session.add_flash("Successfully logged in with program %s."% 
                             programList[0].title)
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
      reset_dj = models.getDjByUsername(username)
      if not reset_dj:
        self.session.add_flash("There is no user by that name")
        self.redirect("/dj/reset/")
        return
      if (not reset_dj.pw_reset_expire or
          not reset_dj.pw_reset_hash or
          datetime.datetime.now() > reset_dj.pw_reset_expire):
        self.session.add_flash("This request is no longer valid, request a new reset.")
        self.redirect("/dj/reset")
        return
      if check_password(reset_dj.pw_reset_hash, reset_key):
        self.set_session_user(reset_dj)
        reset_dj.pw_reset_expire = datetime.datetime.now()
        reset_dj.pw_reset_hash = None
        reset_dj.put()
        programList = models.getProgramsByDj(reset_dj)
        if not programList:
          self.session.add_flash("You have been temporarily logged in. Please change your password so that you may log in in the future!<br><br>\n\nYou will not be able to do much until you have a program.  If you see this message, please email <a href='mailto:cmsmith@bowdoin.edu'>Connor</a> immediately.")
          # self.sess['program'] = None
          self.redirect('/dj/myself')
          return
        elif len(programList) == 1:
          self.set_session_program(programList[0])
          self.session.add_flash("You have been temporarily logged in. Please change your password so that you may log in in the future!<br><br>\n\nLogged in with program " + programList[0].title + ".")
          self.redirect("/dj/myself")
          return
        else:
          self.session.add_flash("You have been temporarily logged in. Please change your password so that you may log in in the future!")
          self.redirect("/dj/myself")
          return
      else:
        self.session.add_flash("Error, this is not a valid password reset URL.")
        self.redirect("/dj/reset/")
    else:
      if self.session_has_login():
        self.redirect("/dj/")
      template_values = {
        'session': self.session,
        'flash': self.flash,
        }
      self.response.out.write(template.render(getPath("dj_reset_password.html"), 
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
    if username:
      reset_dj = models.getDjByUsername(username)
    if not reset_dj:
      self.session.add_flash("Requested user does not exist")
      self.redirect("/dj/reset/")
      return
    if "@" not in email:
      email = email + "@bowdoin.edu"
    if email[-1] == "@":
      email = email + "bowdoin.edu"
    if reset_dj.email.strip() != email.strip():
      self.session.add_flash("Username and email do not match")
      self.redirect("/dj/reset/")
      return

    # Generate a key to be sent to the user and add the
    # new password request to the database
    reset_key = ''.join(random.choice(string.ascii_letters +
                                      string.digits) for x in range(20))
    reset_url="%s/dj/reset/?username=%s&reset_key=%s"%(
      self.request.host_url,username,reset_key)
    reset_dj.pw_reset_expire=datetime.datetime.now() + datetime.timedelta(2)
    reset_dj.pw_reset_hash=hash_password(reset_key)
    reset_dj.put()
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
    self.session.add_flash("Request successfully sent! Check your mail, and be sure to doublecheck the spam folder in case.")
    self.redirect("/")

# Lets the user select which program they've logged in as
class SelectProgram(UserHandler):
  @login_required
  def get(self):
    programlist = models.getProgramsByDj(self.dj_key)
    if len(programlist) <= 1:
      self.session.add_flash("You don't have more than one radio program to choose between.")
      self.redirect("/dj/")
      return
    template_values = {
      'programlist': programlist,
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(1)
    }
    self.response.out.write(template.render(getPath("dj_selectprogram.html"),
      template_values))
  
  @login_required
  def post(self):
    program_key = self.request.get("programkey")
    program = models.Program.get(program_key)
    if not program:
      self.session.add_flash("An error occurred retrieving your program.  Please try again.")
      self.redirect("/dj/")
      return
    self.set_session_program(program)
    self.session.add_flash("The current program has been set to " + program.title + ".")
    self.redirect("/dj/")


# The main portion of what a DJ sees on the website
# get(): the form for charting a song; displays current playlist under form.
# post(): charts the song/psa/stationID
class ChartSong(UserHandler):
  @login_required
  def get(self):
    if not self.session_has_program():
      self.session.add_flash("You can't chart songs until you have an associated program in the system.  Please contact a member of management immediately.")
      self.redirect("/dj/")
      return
    station_id = False
    try:
      if self.flash.msg == "Station ID recorded.":
        station_id = True
    except AttributeError:
      pass 
    posts = models.getLastPosts(2)
    memcache_key = "playlist_html_%s"%self.session.get('program').get('key')
    playlist_html = memcache.get(memcache_key)
    if not playlist_html:
      playlist_html = template.render("dj_chartsong_playlist_div.html",
        {'playlist': cache.getLastPlays(num=50,
                                        program=self.program_key,
                                        after=(datetime.datetime.now() - 
                                               datetime.timedelta(days=1))),
         }
      )
      memcache.set(memcache_key, playlist_html, 60 * 60 * 24)
    last_psa = cache.getLastPsa()
    new_albums = None
    new_song_div_html = memcache.get("new_song_div_html")
    album_songs = []
    new_song_div_html = None
    if not new_song_div_html:
      new_albums = []
      #new_albums = models.getNewAlbums(byArtist=True)
      if new_albums:
        new_albums = models.Album.get(new_albums)
        logging.debug(new_albums)
        album_songs = [models.Song.get(k) for k in 
                       new_albums[0].songList]
      memcache.set("new_song_div_html",
        template.render(
          getPath("dj_chartsong_newsongdiv.html"), 
            {'new_albums': new_albums,
             'album_songs': album_songs,}
        )
      )
    template_values = {
      'last_psa': last_psa,
      'playlist_html': playlist_html,
      'session': self.session,
      'flash': self.flash,
      'new_albums': new_albums,
      'album_songs': album_songs,
      'new_song_div_html': new_song_div_html,
      'posts': posts,
      'station_id': station_id,
    }
    self.response.out.write(template.render(getPath("dj_chartsong.html"), template_values))
  
  @login_required
  def post(self):
    if self.request.get("submit") == "Chart Song":
      # Charting a song, not a PSA or ID
      track_artist = self.request.get("artist").encode("latin1", 'replace')
      trackname = self.request.get("trackname").encode("latin1", 'replace')
      isNew = self.request.get("isNew")
      if isNew:
        # if it's "new", the album should be in the datastore already with
        # a valid key.
        album = models.Album.get(self.request.get("album_key"))      
        if not album:
          self.session.add_flash("Missing album information for new song, please try again.")
          self.redirect("/dj/chartsong/")
          return
        # likewise, the song should be in the datastore already with a valid key.
        song = models.Song.get(self.request.get("song_key"))
        if not song:
          self.session.add_flash("An error occurred trying to fetch the song, please try again.")
          self.redirect("/dj/chartsong/")
          return
        trackname = song.title
        track_artist = song.artist
        models.addNewPlay(song=song, program=self.program_key, 
                          play_date=datetime.datetime.now(), isNew=True, 
                          artist=album.artist)
      else:
        # a song needs to have an artist and a track name
        if not track_artist or not trackname:
          self.session.add_flash("Missing track information, please fill out both fields.")
          self.redirect("/dj/chartsong/")
          return
        song = models.Song(title=trackname, artist=track_artist)
        song.put()
        models.addNewPlay(song=song, program=self.program_key, 
                          play_date=datetime.datetime.now(), isNew=False, 
                          artist=track_artist)
      memcache_key = "playlist_html_%s"%self.session.get('program').get('key')
      playlist_html = template.render("dj_chartsong_playlist_div.html",
      {'playlist': models.getLastPlays(program=self.program_key, 
                                       after=(datetime.datetime.now() - 
                                              datetime.timedelta(days=1)))}
      )
      memcache.set(memcache_key, playlist_html, 60 * 60 * 24)
      if not models.getArtist(track_artist):
        # this is for autocomplete purposes. if the artist hasn't been charted
        # before, save the artist name in the datastore.
        an = models.ArtistName(artist_name=track_artist, 
          lowercase_name=track_artist.lower(),
          search_names=models.artistSearchName(track_artist).split())
        an.put()
      # updates the top 10 artists for the program
      self.updateArtists(models.Program.get(self.program_key), track_artist)
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
        self.session.add_flash("%s has been charted and scrobbled to Last.FM, and should show up below."%trackname)
      except:
        # just catch all errors with the last.fm; it's not that important that
        # everything get scrobbled exactly; plus this is like the #1 source
        # of errors in charting songs.
        self.session.add_flash("%s has been charted, but was not scrobbled to Last.FM"%
                               trackname)
      self.redirect("/dj/chartsong/")
      return
      # End of song charting.
    elif self.request.get("submit") == "Station ID":
      # If the DJ has recorded a station ID
      station_id = models.StationID(program=self.program_key, 
                                    play_date=datetime.datetime.now())
      station_id.put()
      self.session.add_flash("Station ID recorded.")
      self.redirect("/dj/chartsong/")
      return
    elif self.request.get("submit") == "PSA":
      # If the DJ has recorded a PSA play
      psa_desc = self.request.get("psa_desc")
      cache.addNewPsa(desc=psa_desc, program=self.program_key)
      self.session.add_flash("PSA recorded.")
      self.redirect("/dj/chartsong/")
      return
  
  # This is a helper method to update which artists are recorded as
  # the most-played artists for a given program.
  # If the artist just played is already within the top 10, then
  # increment the count by one and re-order.
  # Otherwise, make an 11-element list of the current top 10 artists played
  # along with the just-played artist's name and playcount;
  # sort this list, grab the first 10 elements and save them.
  def updateArtists(self, program, artist):
    # a dictionary which looks like (artist_name => playcount)
    playcounts = {}
    for a, p in zip(program.top_artists, program.top_playcounts):
      playcounts[a] = p
    if artist in playcounts:
      playcounts[artist] = playcounts[artist] + 1
    else:
      playcounts[artist] = self.getPlayCountByArtist(program, artist) + 1
    playcounts = [(playcounts[a], a) for a in playcounts]
    playcounts.sort()
    playcounts.reverse()
    playcounts = playcounts[:10]
    program.top_artists = [str(p[1]) for p in playcounts]
    program.top_playcounts = [int(p[0]) for p in playcounts]
    program.put()
  def getPlayCountByArtist(self, program, artist):
    return len(models.Play.all().filter("program =", program).filter("artist =", artist).fetch(1000))
  


# Displays the top-played songs for a given period.
# get(): Print log for the last week, display form for choosing endpoint.
# post(): Print log of week-long period.
class ViewCharts(UserHandler):  
  @login_required
  def get(self):
    default_songs = 20
    default_albums = 50
    start = datetime.datetime.now() - datetime.timedelta(weeks=1)
    end = datetime.datetime.now()
    songs, albums = models.getTopSongsAndAlbums(start, end, default_songs, default_albums)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'songs': songs,
      'albums': albums,
      'start': start,
      'end': end,
    }
    self.response.out.write(template.render(getPath("dj_charts.html"), template_values))
  
  @login_required
  def post(self):
    default_songs = 20
    default_albums = 50
    try:
      start = datetime.datetime.strptime(self.request.get("start_date"), "%m/%d/%Y")
    except ValueError:
      self.session.add_flash("Unable to select date. Enter a date in the form mm/dd/yyyy.")
      self.redirect("/dj/charts/")
      return
    end = start + datetime.timedelta(weeks=1)
    if self.request.get("song_num"):
      default_songs = int(self.request.get("song_num"))
    if self.request.get("album_num"):
      default_albums = int(self.request.get("album_num"))
    songs, albums = models.getTopSongsAndAlbums(start, end, default_songs, default_albums)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'songs': songs,
      'albums': albums,
      'start': start,
      'end': end,
    }
    self.response.out.write(template.render(getPath("dj_charts.html"), template_values))

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
      'flash': self.flash,
      'psas': psas,
      'ids': ids,
      'start': start,
      'end': end,
    }
    self.response.out.write(template.render(getPath("dj_logs.html"), template_values))
  
  @login_required
  def post(self):
    try:
      start = datetime.datetime.strptime(self.request.get("start_date"), "%m/%d/%Y")
    except ValueError:
      self.session.add_flash("Unable to select date. Enter a date in the form mm/dd/yyyy.")
      self.redirect("/dj/logs/")
      return      
    end = start + datetime.timedelta(weeks=2)
    psas = models.getPSAsInRange(start=start, end=end)
    ids = models.getIDsInRange(start=start, end=end)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'psas': psas,
      'ids': ids,
      'start': start,
      'end': end,
    }
    self.response.out.write(template.render(getPath("dj_logs.html"), template_values))
  


# For administration, manages the DJs in the system.
# get(): Displays list of current DJs for editing/deletion
# post(): Adds a new DJ
class ManageDJs(UserHandler):
  @authorization_required("Manage DJs")
  def get(self):
    dj_list = models.Dj.all().order("fullname")
    template_values = {
      'dj_list': dj_list,
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(3),
    }
    self.response.out.write(template.render(getPath("dj_manage_djs.html"),
      template_values))
  
  @authorization_required("Manage DJs")
  def post(self):
    if self.request.get("submit") != "Add DJ":
      self.session.add_flash("There was an error, please try again.")
      self.redirect("/dj/djs/")
    else:
      email = self.request.get("email")
      username = self.request.get("username")
      if not email:
        self.session.add_flash("Please enter a valid email address.")
        self.redirect("/dj/djs")
        return
      if not username:
        self.session.add_flash("Please enter a valid username.")
        self.redirect("/dj/djs")
        return
      if not self.request.get("fullname"):
        self.session.add_flash("Please enter a valid full name.")
        self.redirect("/dj/djs")
        return
      if not self.request.get("password"):
        self.session.add_flash("Please enter a valid password.")
        self.redirect("/dj/djs")
        return
      if not self.request.get("password") == self.request.get("confirm"):
        self.session.add_flash("Passwords do not match.")
        self.redirect("/dj/djs")
        return
      if "@" not in email:
        email = email + "@bowdoin.edu"
      if email[-1] == "@":
        email = email + "bowdoin.edu"
      dj = models.getDjByEmail(email)
      if dj:
        self.session.add_flash("A DJ with email address " + dj.email + " already exists: " + dj.fullname + ", username " + dj.username)
        self.redirect("/dj/djs")
        return
      dj = models.getDjByUsername(username)
      if dj:
        self.session.add_flash("A DJ with username " + username + " already exists: " + dj.fullname + ", email address " + dj.email)
        self.redirect("/dj/djs")
        return
      # If both username and email address are new, then we can add them
      dj = models.Dj(fullname=self.request.get("fullname"),
        lowername=self.request.get("fullname").lower(),
        email=email,
        username=username,
        password_hash=hash_password(self.request.get("password")))
      dj.put()
      self.session.add_flash(dj.fullname + " successfully added as a DJ.")
      self.redirect("/dj/djs/")
  

# Displays and edits a DJ's details in the datastore
# get(): Display DJ's details
# post(): Save changes to DJ's details
class EditDJ(UserHandler):
  @authorization_required("Manage DJs")
  def get(self, dj_key):
    dj = models.Dj.get(dj_key)
    dj_list = models.Dj.all().order("fullname")
    if not dj:
      self.session.add_flash("The DJ specified (" + dj_key + ") does not exist.  Please try again.")
      self.redirect("/dj/djs/")
    else:
      template_values = {
        'dj_list': dj_list,
        'dj': dj,
        'session': self.session,
        'flash': self.flash,
        'posts': models.getLastPosts(3),
      }
      self.response.out.write(template.render(getPath("dj_manage_djs.html"), template_values))
  
  @authorization_required("Manage DJs")
  def post(self, dj_key):
    dj = models.Dj.get(dj_key)
    if (not dj) or (self.request.get("submit") != "Edit DJ" and self.request.get("submit") != "Delete DJ"):
      self.session.add_flash("There was an error processing your request.  Please try again.")
    elif self.request.get("submit") == "Edit DJ":
      dj.fullname = self.request.get("fullname")
      dj.lowername = dj.fullname.lower()
      dj.email = self.request.get("email")
      if dj.email[-1] == "@":
        dj.email = dj.email + "bowdoin.edu"
      if "@" not in dj.email:
        dj.email = dj.email + "@bowdoin.edu"
      dj.username = self.request.get("username")
      if self.request.get("password"):
        if not self.request.get("password") == self.request.get("confirm"):
          self.session.add_flash("New passwords do not match.")
          self.redirect("/dj/djs")
          return
        else:
          dj.password_hash = hash_password(self.request.get("password"))
      dj.put()
      self.session.add_flash(dj.fullname + " has been successfully edited.")
    elif self.request.get("submit") == "Delete DJ":
      dj.delete()
      self.session.add_flash(dj.fullname + " has been successfully deleted.")
    self.redirect("/dj/djs/")


# Displays current programs and adds new programs
# get(): display current programs
# post(): add new program
class ManagePrograms(UserHandler):
  @authorization_required("Manage Programs")
  def get(self):
    program_list = models.Program.all().order("title")

    template_values = {
      'current_programs': tuple({"prog" : program,
                                 "dj_list" : (tuple(models.Dj.get(dj) 
                                                    for dj in program.dj_list) if program.dj_list
                                              else None)}
                                for program in program_list if program.current),
      'legacy_programs': tuple({"prog" : program,
                                "dj_list" : (tuple(models.Dj.get(dj) 
                                                   for dj in program.dj_list) if program.dj_list
                                              else None)}
                               for program in program_list if not program.current),
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(3),
    }
    self.response.out.write(template.render(getPath("dj_manage_programs.html"), template_values))
  
  @authorization_required("Manage Programs")
  def post(self):
    if (self.request.get("submit") != "Add Program"):
      self.session.add_flash("There was an error processing your request. Please try again.")
    else:
      slug = self.request.get("slug")
      program = models.getProgramBySlug(slug)
      if program:
        self.session.add_flash(("Program \"%s\" already exists with slug %s."%
                          (program.title, slug)))
        self.redirect("/dj/programs/")
        return

      # Set up the program entry, and then put it in the DB
      program = models.Program(title=self.request.get("title"), 
                               slug=self.request.get("slug"),
                               desc=self.request.get("desc"), 
                               dj_list=[], 
                               page_html=self.request.get("page_html"),
                               current=bool(self.request.get("current")))
      program.put()

      self.session.add_flash("%s was successfully created associated a program. "
                        "Click <a href='/dj/programs/%s'>here</a> "
                        "to edit it (you probably want to do "
                        "this as there are no DJs on it currently)."% 
                        (program.title, str(program.key())))

    self.redirect('/dj/programs/')
  

# Displays and edits details of a program.
class EditProgram(UserHandler):
  @authorization_required("Manage Programs")
  def get(self, program_key):
    program = models.Program.get(program_key)
    if not program:
      self.session.add_flash("Unable to find program (" + program_key + ").  Please try again.")
      self.redirect("/dj/programs/")
    else:
      template_values = {
        'all_dj_list': [{'dj': dj, 'in_program': dj.key() in program.dj_list} for dj in models.Dj.all()],
        'program': program,
        'session': self.session,
        'flash': self.flash,
        'posts': models.getLastPosts(3),
      }
      self.response.out.write(template.render(getPath("dj_manage_programs.html"), template_values))
  
  @authorization_required("Manage Programs")
  def post(self, program_key):
    program = models.Program.get(program_key)
    if (not program) or (self.request.get("submit") != "Edit Program" and self.request.get("submit") != "Delete Program"):
      self.session.add_flash("There was an error processing your request. Please try again.")
    elif self.request.get("submit") == "Edit Program":
      program.title = self.request.get("title")
      program.slug = self.request.get("slug")
      program.desc = self.request.get("desc")
      program.page_html = self.request.get("page_html")
      program.dj_list = [models.db.Key(k) for k in self.request.get("dj_list", allow_multiple=True)]
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
    dj = models.Dj.get(self.dj_key)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'dj': dj,
      'posts': models.getLastPosts(1),
    }
    self.response.out.write(template.render(getPath("dj_self.html"), template_values))
  
  @login_required
  def post(self):
    dj = models.Dj.get(self.request.get("dj_key"))
    errors = ""
    if not dj:
      self.session.add_flash("An error occurred processing your request.  Please try again.")
      self.redirect("/dj/myself")
      return
    dj.fullname = self.request.get("fullname")
    dj.lowername = dj.fullname.lower()
    email = self.request.get("email")
    duplicate_dj = models.getDjByEmail(email)
    if duplicate_dj and str(duplicate_dj.key()) != str(dj.key()):
      errors += "The email specified is already in use by another DJ.  Please enter a unique one."
    dj.email = email
    if dj.email[-1] == "@":
      dj.email = dj.email + "bowdoin.edu"
    if "@" not in dj.email:
      dj.email = dj.email + "@bowdoin.edu"
    username = self.request.get("username")
    duplicate_dj = models.getDjByUsername(username)
    if duplicate_dj and str(duplicate_dj.key()) != str(dj.key()):
      errors += "The username specified is already in use by another DJ.  Please choose another."
    dj.username = username
    if errors:
      self.session.add_flash(errors)
      self.redirect("/dj/myself")
      return
    if self.request.get("password"):
      if not self.request.get("password") == self.request.get("confirm"):
        self.session.add_flash("New passwords do not match.")
        self.redirect("/dj/myself")
        return
      else:
        dj.password_hash = hash_password(self.request.get("password"))
    dj.put()
    self.session.add_flash("You have successfully updated your profile.")
    self.redirect("/dj/")

# Lets a DJ edit the description etc. of their show.
class MyShow(UserHandler):
  @login_required
  def get(self):
    program = models.Program.get(self.program_key)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'program': program,
      'posts': models.getLastPosts(2),
    }
    self.response.out.write(template.render(getPath("dj_myshow.html"), template_values))
  
  @login_required
  def post(self):
    program = models.Program.get(self.request.get("program_key"))
    if not program:
      self.session.add_flash("Unable to find program.")
      self.redirect("/dj/myshow")
      return
    slug = self.request.get("slug")
    p = models.getProgramBySlug(slug)
    if p and program.key() != p.key():
      self.session.add_flash("There is already a program with slug \"" + slug + "\".")
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
    posts = models.getLastPosts(2)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'posts': posts,
    }
    self.response.out.write(template.render(getPath("dj_createpost.html"), template_values))
  
  @authorization_required("Manage Blog")
  def post(self):
    errors = ""
    title = self.request.get("title")
    text = self.request.get("text")
    post_date = datetime.datetime.now();
    slug = self.request.get("slug")
    post = models.BlogPost(title=title, text=text, post_date=post_date, slug=slug)
    posts = models.getLastPosts(2)
    if models.getPostBySlug(post_date, slug):
      errors = "Error: this post has a duplicate slug to another post from the same day.  This probably shouldn't happen often."
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'errors': errors,
      'post': post,
      'posts': posts,
    }
    if errors:
      self.response.out.write(template.render(getPath("dj_createpost.html"), template_values))
    else:
      post.put()
      self.session.add_flash("Post \"%s\" successfully added." % title)
      self.redirect("/")



class EditBlogPost(UserHandler):
  @authorization_required("Manage Blog")
  def get(self, date_string, slug):
    post_date = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    post = models.getPostBySlug(post_date, slug)
    if not post:
      self.session.add_flash("The post you're looking for does not exist.  But you can look at actual posts below :)")
      self.redirect("/")
      return
    posts = models.getLastPosts(2)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'post': post,
      'editing': True,
      'posts': posts,
    }
    self.response.out.write(template.render(getPath("dj_createpost.html"), template_values))
  
  @authorization_required("Manage Blog")
  def post(self, date_string, slug):
    errors = ""
    title = self.request.get("title")
    text = self.request.get("text")
    slug = self.request.get("slug")
    post_key = self.request.get("post_key")
    post = models.BlogPost.get(post_key)
    if not post:
      self.session.add_flash("The post you're looking for does not exist.  Something strange has occurred.")
      # this shouldn't happen unless people are fiddling around with POST values by hand I think
      self.redirect("/")
      return
    if self.request.get("submit") == "Delete Post":
      post.delete()
      self.session.add_flash("Post deleted.")
      self.redirect("/")
      return
    duplicate = models.getPostBySlug(post.post_date, slug)
    old_slug = post.slug
    post.slug = slug
    if duplicate:
      if str(duplicate.key()) != post_key:
        errors = "This post has a duplicate slug to another post from the same day.  Please rename the slug."
        post.slug = old_slug
    post.title = title
    post.text = text
    posts = models.getLastPosts(2)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'errors': errors,
      'post': post,
      'editing': True,
      'posts': posts,
    }
    if errors:
      self.response.out.write(template.render(getPath("dj_createpost.html"), template_values))
    else:
      post.put()
      self.session.add_flash("Successfully altered post %s" % post.title)
      self.redirect("/")


class RemovePlay(UserHandler):
  @login_required
  def post(self):
    self.response.headers['Content-Type'] = 'text/json'
    cache.deletePlay(self.request.get("play_key"), self.program_key)
    memcache.delete("playlist_html_%s"%self.program_key)
    self.response.out.write(simplejson.dumps({
          'status': "Successfully deleted play."
          }))

class NewEvent(UserHandler):
  @authorization_required("Manage Events")
  def get(self):
    posts = models.getLastPosts(2)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'editing': False,
      'hours': [str(i).rjust(2, "0") for i in range(24)],
      'minutes': [str(i).rjust(2, "0") for i in range(0, 60, 15)],
      'posts': posts,
    }
    self.response.out.write(template.render(getPath("dj_create_event.html"), template_values))

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
      self.session.add_flash("Unable to work with date \"%s\". Enter a valid date in the form mm/dd/yyyy, and an hour/minute as well." % date_string)
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
      self.session.add_flash("Unable to find the requested event.  Please try again.")
      self.redirect("/dj/")
      return
    day = event.event_date.strftime("%m/%d/%Y")
    hour = event.event_date.strftime("%H")
    minute = event.event_date.strftime("%M")
    posts = models.getLastPosts(2)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'editing': True,
      'event': event,
      'day': day,
      'hour': hour,
      'minute': minute,
      'hours': [str(i).rjust(2, "0") for i in range(24)],
      'minutes': [str(i).rjust(2, "0") for i in range(0, 60, 15)],
      'posts': posts,
    }
    self.response.out.write(template.render(getPath("dj_create_event.html"), template_values))

  @authorization_required("Manage Events")
  def post(self, event_key):
    event = models.Event.get(self.request.get("event_key"))
    if not event:
      self.session.add_flash("Unable to find the requested event.  Please try again.")
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
      self.session.add_flash("Unable to work with date. Enter a date in the form mm/dd/yyyy, and an hour/minute as well.")
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
    permissions = models.getPermissions()
    template_values = {
      'permissions': [{
        'key': p.key(),
        'title': p.title,
        'dj_list': [models.Dj.get(d) for d in p.dj_list],
        } for p in permissions],
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(2),
    }
    self.response.out.write(template.render(getPath("dj_permissions.html"), template_values))
  
  @authorization_required("Manage Permissions")
  def post(self):
    self.response.headers['Content-Type'] = 'text/json'
    dj_key = self.request.get("dj_key")
    dj = models.Dj.get(dj_key)
    errors = "";
    if not dj:
      errors = "Unable to find DJ. "
    permission_key = self.request.get("permission_key")
    permission = models.Permission.get(permission_key)
    if not permission:
      errors = "Unable to find permission."
    if errors:
      self.response.out.write(simplejson.dumps({
        'err': errors,
      }))
      return
    action = self.request.get("action")
    if action == "add":
      if dj.key() in permission.dj_list:
        errors = dj.fullname + " is already in the " + permission.title + " permission list."
      else:
        permission.dj_list.append(dj.key())
        status = "Successfully added " + dj.fullname + " to " + permission.title + " permission list."
    if action == "remove":
      if dj.key() not in permission.dj_list:
        errors = dj.fullname + " was not in the " + permission.title + " permission list."
      else:
        permission.dj_list.remove(dj.key())
        status = "Successfully removed " + dj.fullname + " from " + permission.title + " permission list."
    if errors:
      self.response.out.write(simplejson.dumps({
        'err': errors,
      }))
    else:
      permission.put()
      self.response.out.write(simplejson.dumps({
        'err': '',
        'msg': status
      }))
  

# Add and edit which albums are marked as "new"
# get(): Display list of new albums
# post(): One of four actions:
#     - add: AJAXically adds a new album to the datastore.
#     - makeOld: AJAXically removes "new" status from an album
#     - makeNew: AJAXically adds "new" status back to an album if made old by mistake
#     - manual: NOT AJAX - adds an album which has been typed in by hand.

class ManageAlbums(UserHandler):
  @authorization_required("Manage Albums")
  def get(self):
    new_album_list = None
    new_album_html = memcache.get("manage_new_albums_html")
    if not new_album_html:
      new_album_list = []
      #new_album_list = models.getNewAlbums()
      new_album_html = template.render(
        getPath("dj_manage_new_albums_list.html"), {'new_album_list': new_album_list}
      )
      memcache.set("manage_new_albums_html", new_album_html)
    template_values = {
      'new_album_list': new_album_list,
      'new_album_html': new_album_html,
      'session': self.session,
      'flash': self.flash,
    }
    self.response.out.write(template.render(getPath("dj_manage_albums.html"), template_values))
  
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
      album = models.getAlbumByASIN(asin)
      if album:
        album.isNew = True
        album.put()
        memcache.flush_all()
        self.response.out.write(simplejson.dumps({
          'msg': "Success, already existed. The album was re-set to new."
        }))
        return
      # Grab the product details from Amazon to save to our datastore.
      i = amazon.productSearch(asin)
      try:
        i = i[0]
      except IndexError:
        self.response.out.write(simplejson.dumps({
          'err': "An error occurred.  Please try again, or if this keeps happening, select a different album."
        }))
        return
      # this overly complicated code sets up the json data associated with
      # the album we're adding.  It pulls the appropriate values from the
      # XML received.
      json_data = {
        'small_pic': i.getElementsByTagName("SmallImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
        'large_pic': i.getElementsByTagName("LargeImage")[0].getElementsByTagName("URL")[0].firstChild.nodeValue,
        'artist': i.getElementsByTagName("Artist")[0].firstChild.nodeValue,
        'title': i.getElementsByTagName("Title")[0].firstChild.nodeValue,
        'asin': i.getElementsByTagName("ASIN")[0].firstChild.nodeValue,
        'tracks': [t.firstChild.nodeValue for t in i.getElementsByTagName("Track")],
      }
      largeCover = urlfetch.fetch(json_data['large_pic']).content
      large_filetype = json_data['large_pic'][-4:].strip('.')
      smallCover = urlfetch.fetch(json_data['small_pic']).content
      small_filetype = json_data['small_pic'][-4:].strip('.')
      # create the actual objects and store them
      cover = models.CoverArt(
        large_filetype=large_filetype,
        small_filetype=small_filetype,
        large_cover=largeCover,
        small_cover=smallCover,
        )
      cover.put()
      album = models.Album(
        title=json_data['title'],
        lower_title=json_data['title'].lower(),
        artist=json_data['artist'],
        add_date=datetime.datetime.now(),
        isNew=True,
        cover_art=cover,
        asin=asin,
      )
      album.put()
      artist_name = json_data['artist']
      if not models.getArtist(artist_name):
        an = models.ArtistName(artist_name=artist_name, 
          lowercase_name=artist_name.lower(),
          search_names=models.artistSearchName(artist_name).split())
        an.put()
      songlist = [models.Song(title=t, artist=json_data['artist'], album=album) for t in json_data['tracks']]
      for s in songlist:
        s.put()
      album.songList = [s.key() for s in songlist]
      album.put()
      memcache.flush_all()
      self.response.out.write(simplejson.dumps({'msg': "Album successfully added."}))
    elif action == "makeNew":
      # We're marking an existing album as "new" again
      self.response.headers['Content-Type'] = 'text/json'
      key = self.request.get("key")
      album = models.Album.get(key)
      if not album:
        self.response.out.write(simplejson.dumps({'err': "Album not found. Please try again."}))
        return
      album.isNew = True
      album.put()
      memcache.flush_all()
      self.response.out.write(simplejson.dumps({'msg': "Made new."}))
    elif action == "makeOld":
      # We're removing the "new" marking from an album
      self.response.headers['Content-Type'] = 'text/json'
      key = self.request.get("key")
      album = models.Album.get(key)
      if not album:
        self.response.out.write(simplejson.dumps({'err': "Album not found. Please try again."}))
        return
      album.isNew = False
      album.put()
      memcache.flush_all()
      self.response.out.write(simplejson.dumps({'msg': "Made old."}))
    elif action == "manual":
      # The user has typed in the title, the artist, all track names,
      # and provided a cover image URL.
      tracks = self.request.get("track-list")
      tracks = [line.strip() for line in tracks.splitlines() if
                len(line.strip())>0]
      cover_url = self.request.get("cover_url")
      if not cover_url:
        cover_url = "/static/images/noalbumart.png"
      try:
        cover = urlfetch.fetch(cover_url).content
      except urlfetch.ResponseTooLargeError:
        self.session.add_flash("The image you provided was too large.  There is a 1MB limit on cover artwork.  Try a different version with a reasonable size.")
        self.redirect("/dj/albums/")
        return
      except urlfetch.InvalidURLError:
        self.session.add_flash("The URL you provided could not be downloaded.  Hit back and try again.")
        self.redirect("/dj/albums/")
        return
      except urlfetch.DownloadError:
        self.session.add_flash("The URL you provided could not be downloaded.  Hit back and try again.")
        self.redirect("/dj/albums/")
        return
      cover_filetype = cover_url[-4:].strip('.')
      artist = self.request.get('artist')
      cover = models.CoverArt(
        large_cover=cover,
        small_cover=cover,
        large_filetype=cover_filetype,
        small_filetype=cover_filetype
        )
      cover.put()
      album = models.Album(
        title=self.request.get("title"),
        lower_title=self.request.get("title").lower(),
        artist=artist,
        add_date=datetime.datetime.now(),
        isNew=True,
        cover=cover
        )
      album.put()
      memcache.flush_all()
      songlist = [models.Song(title=trackname, artist=artist, album=album) for trackname in tracks]
      for s in songlist:
        s.put()
      album.songList = [s.key() for s in songlist]
      album.put()
      if not models.getArtist(artist):
        an = models.ArtistName(artist_name=artist, 
          lowercase_name=artist.lower(),
          search_names=models.artistSearchName(artist).split())
        an.put()
      self.session.add_flash(self.request.get("title") + " added.")
      self.redirect("/dj/albums/")


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
    ('/dj/charts/?', ViewCharts),
    ('/blog/([^/]*)/([^/]*)/edit/?', EditBlogPost),
    ('/dj/newpost/?', NewBlogPost),
    ('/dj/event/?', NewEvent),
    ('/dj/myself/?', MySelf),
    ('/dj/removeplay/?', RemovePlay),
    ('/dj/event/([^/]*)/?', EditEvent),
    ('/dj/reset/?.*', RequestPassword),
    ], debug=True, config=webapp2conf)
