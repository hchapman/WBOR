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
import cache
import datetime
import time
import logging
import json

from google.appengine.api import urlfetch
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import images
from google.appengine.api import files

import webapp2
from google.appengine.ext.webapp import template

import amazon
import pylast
from handlers import UserHandler
from passwd_crypto import hash_password
from slughifi import slughifi
import models_old as models

from models.dj import (Dj, InvalidLoginError,)
from models.permission import (Permission,)

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
        if Permission.getByTitle(label).hasDj(key):
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
      'manage_djs': Permission.getByTitle(Permission.DJ_EDIT).hasDj(djkey),
      'manage_programs': Permission.getByTitle(Permission.PROGRAM_EDIT).hasDj(djkey),
      'manage_albums': Permission.getByTitle(Permission.ALBUM_EDIT).hasDj(djkey),
      'manage_permissions': Permission.getByTitle(Permission.PERMISSION_EDIT).hasDj(djkey),
      'manage_genres': Permission.getByTitle(Permission.GENRE_EDIT).hasDj(djkey),
      'manage_blogs': Permission.getByTitle(Permission.BLOG_EDIT).hasDj(djkey),
      'manage_events': Permission.getByTitle(Permission.EVENT_EDIT).hasDj(djkey),
      'posts': models.getLastPosts(3),
    }
    self.response.out.write(template.render(get_path("dj_main.html"), template_values))
  

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
    except NoSuchUserError:
      self.flash = "Invalid username. Please try again."
      self.redirect('/dj/login/')
      return
    except InvalidLoginError:
      self.flash = "Invalid username/password combination. Please try again."
      self.redirect('/dj/login/')
      return

    self.user = dj
    programList = cache.getPrograms(dj=dj)
    if not programList:
      self.flash = ("You have successfully logged in,"
                    "but you have no associated programs."
                    "You will not be able to do much until"
                    "you have a program.  If you see this message,"
                    "please email <a href='mailto:cmsmith@bowdoin.edu'>"
                    "Connor</a> immediately.")
      self.redirect('/dj/')
      return
    elif len(programList) == 1:
      self.program = programList[0]
      self.flash = ("Successfully logged in with program %s."% 
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

      try:
        reset_dj = Dj.recoveryLogin(username, reset_key)
      except NoSuchUserError:
        self.session.add_flash("There is no user by that name")
        self.redirect("/dj/reset/")
        return
      except InvalidLoginError:
        self.flash = ("This request is no longer valid, or the key provided"
                      "is somehow corrupt. If clicking the link in your email"
                      "does not work again, perhaps request a new reset.")
        self.redirect("/dj/reset")
        return
      
      self.set_session_user(reset_dj)
      programList = cache.getPrograms(dj=reset_dj)

      if not programList:
        self.flash = ("You have been temporarily logged in. Please change your"
                      "password so that you may log in in the future!<br><br>"
                      "\n\nYou will not be able to do much until you have a"
                      "program.  If you see this message, please email"
                      "<a href='mailto:cmsmith@bowdoin.edu'>Connor</a>"
                      "immediately.")
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
      if self.session_has_login():
        self.redirect("/dj/")
        return
      template_values = {
        'session': self.session,
        'flash': self.flash,
        }
      self.response.out.write(template.render(get_path("dj_reset_password.html"), 
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
      reset_dj = Dj.getByUsernameCheckEmail(username, email)
    except NoSuchUserError as e:
      self.session.add_flash(str(e))
      self.redirect("/dj/reset")
      return

    # Generate a key to be sent to the user and add the
    # new password request to the database
    reset_url="%s/dj/reset/?username=%s&reset_key=%s"%(
      self.request.host_url,username,reset_dj.resetPassword())
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

sThank you!
The WBOR.org Team
"""%reset_url)
    self.session.add_flash("Request successfully sent! Check your mail, and be sure to doublecheck the spam folder in case.")
    self.redirect("/")

# Lets the user select which program they've logged in as
class SelectProgram(UserHandler):
  @login_required
  def get(self):
    programlist = cache.getPrograms(dj=self.dj_key)
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
    self.response.out.write(template.render(get_path("dj_selectprogram.html"),
      template_values))
  
  @login_required
  def post(self):
    program_key = self.request.get("programkey")
    program = cache.getProgram(key=program_key)
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
    #new_song_div_html = memcache.get("new_song_div_html")
    album_songs = []
    new_song_div_html = None
    if not new_song_div_html:
      new_albums = cache.getNewAlbums(by_artist=True)
      if new_albums:
        logging.debug(new_albums)
        album_songs = [cache.getSong(k) for k in 
                       new_albums[0].songList]
      new_song_div_html = template.render(
        get_path("dj_chartsong_newsongdiv.html"), 
        {'new_albums': new_albums,
         'album_songs': album_songs,}
        )
      memcache.set("new_song_div_html",
                   new_song_div_html
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
    self.response.out.write(template.render(get_path("dj_chartsong.html"), template_values))
  
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
        album = cache.getAlbum(key=self.request.get("album_key"))      
        if not album:
          self.session.add_flash("Missing album information for new song, please try again.")
          self.redirect("/dj/chartsong/")
          return
        # likewise, the song should be in the datastore already with a valid key.
        song = cache.getSong(key=self.request.get("song_key"))
        if not song:
          self.session.add_flash("An error occurred trying to fetch the song, please try again.")
          self.redirect("/dj/chartsong/")
          return
        trackname = song.title
        track_artist = song.artist
        cache.addNewPlay(song=song, program=self.program_key, 
                          play_date=datetime.datetime.now(), isNew=True, 
                          artist=album.artist)
      else:
        # a song needs to have an artist and a track name
        if not track_artist or not trackname:
          self.session.add_flash("Missing track information, please fill out both fields.")
          self.redirect("/dj/chartsong/")
          return
        song = cache.putSong(title=trackname, artist=track_artist)
        song.put()
        
        cache.addNewPlay(song=song, program=self.program_key, 
                          play_date=datetime.datetime.now(), isNew=False, 
                          artist=track_artist)
      memcache_key = "playlist_html_%s"%self.session.get('program').get('key')
      playlist_html = template.render("dj_chartsong_playlist_div.html",
      {'playlist': cache.getLastPlays(program=self.program_key, 
                                      after=(datetime.datetime.now() - 
                                             datetime.timedelta(days=1)))}
      )
      memcache.set(memcache_key, playlist_html, 60 * 60 * 24)
      if not cache.getArtist(track_artist):
        # this is for autocomplete purposes. if the artist hasn't been charted
        # before, save the artist name in the datastore.
        cache.tryPutArtist(track_artist)

      # updates the top 10 artists for the program
      self.updateArtists(cache.getProgram(key=self.program_key), track_artist)
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
    return len(models.Play.all(keys_only=True).
               filter("program =", program).
               filter("artist =", artist).
               fetch(1000))
  


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
    self.response.out.write(template.render(get_path("dj_charts.html"), template_values))
  
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
    self.response.out.write(template.render(get_path("dj_charts.html"), template_values))

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
    self.response.out.write(template.render(get_path("dj_logs.html"), template_values))
  
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
    self.response.out.write(template.render(get_path("dj_logs.html"), template_values))
  


# For administration, manages the DJs in the system.
# get(): Displays list of current DJs for editing/deletion
# post(): Adds a new DJ
class ManageDJs(UserHandler):
  @authorization_required("Manage DJs")
  def get(self):
    dj_list = Dj.getAll() # This is TERRIBLE PRACTICE

    template_values = {
      'dj_list': dj_list,
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(3),
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

      dj = cache.getDjByEmail(email)
      if dj is not None:
        self.session.add_flash(
          "A DJ with email address %s already exists: %s, username %s" %
          (dj.email, dj.fullname, dj.username))
        self.redirect("/dj/djs")
        return
      dj = cache.getDjByUsername(username)
      if dj is not None:
        self.session.add_flash(
          "A DJ with username %s already exists: %s, email address %s" %
          (dj.username, dj.fullname, dj.email))
        self.redirect("/dj/djs")
        return

      # If both username and email address are new, then we can add them
      dj = cache.putDj(fullname=fullname,
                       email=email,
                       username=username,
                       password=password)

      self.session.add_flash(dj.fullname + " successfully added as a DJ.")
      self.redirect("/dj/djs/")
  

# Displays and edits a DJ's details in the datastore
# get(): Display DJ's details
# post(): Save changes to DJ's details
class EditDJ(UserHandler):
  @authorization_required("Manage DJs")
  def get(self, dj_key):
    dj = cache.getDj(dj_key)
    dj_list = cache.getAllDjs()
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
      self.response.out.write(template.render(get_path("dj_manage_djs.html"), template_values))
  
  @authorization_required("Manage DJs")
  def post(self, dj_key):
    dj = cache.getDj(dj_key)
    if (dj is None) or (self.request.get("submit") != "Edit DJ" and 
                        self.request.get("submit") != "Delete DJ"):
      self.session.add_flash("There was an error processing your request.  Please try again.")

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
      dj = cache.putDj(fullname=fullname,
                       email=email,
                       username=username,
                       password=password,
                       edit_dj=dj)
      
      self.session.add_flash(fullname + " has been successfully edited.")
    elif self.request.get("submit") == "Delete DJ":
      cache.deleteDj(dj)
      self.session.add_flash(fullname + " has been successfully deleted.")
    self.redirect("/dj/djs/")


# Displays current programs and adds new programs
# get(): display current programs
# post(): add new program
class ManagePrograms(UserHandler):
  @authorization_required("Manage Programs")
  def get(self):
    program_list = cache.getPrograms(order="title")

    template_values = {
      'current_programs': tuple({"prog" : program,
                                 "dj_list" : cache.getDj(program.dj_list)}
                                 for program in program_list if program.current),
      'legacy_programs': tuple({"prog" : program,
                                "dj_list" : cache.getDj(program.dj_list)}
                               for program in program_list if not program.current),
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(3),
    }
    self.response.out.write(template.render(get_path("dj_manage_programs.html"), template_values))
  
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
      self.response.out.write(template.render(get_path("dj_manage_programs.html"), template_values))
  
  @authorization_required("Manage Programs")
  def post(self, program_key):
    program = cache.getProgram(program_key)
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
    self.response.out.write(template.render(get_path("dj_self.html"), template_values))
  
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
    program = cache.getProgram(self.program_key)
    template_values = {
      'session': self.session,
      'flash': self.flash,
      'program': program,
      'posts': models.getLastPosts(2),
    }
    self.response.out.write(template.render(get_path("dj_myshow.html"), template_values))
  
  @login_required
  def post(self):
    program = cache.getProgram(self.request.get("program_key"))
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
    self.response.out.write(template.render(get_path("dj_createpost.html"), template_values))
  
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
      self.response.out.write(template.render(get_path("dj_createpost.html"), template_values))
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
    self.response.out.write(template.render(get_path("dj_createpost.html"), template_values))
  
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
      self.response.out.write(template.render(get_path("dj_createpost.html"), template_values))
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
    self.response.out.write(json.dumps({
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
    self.response.out.write(template.render(get_path("dj_create_event.html"), template_values))

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
    self.response.out.write(template.render(get_path("dj_create_event.html"), template_values))

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
    permissions = Permission.getAll()
    template_values = {
      'permissions': [{
        'key': p.key(),
        'title': p.title,
        'dj_list': [cache.getDj(d) for d in p.dj_list],
        } for p in permissions],
      'session': self.session,
      'flash': self.flash,
      'posts': models.getLastPosts(2),
    }
    self.response.out.write(template.render(get_path("dj_permissions.html"), template_values))
  
  @authorization_required("Manage Permissions")
  def post(self):
    self.response.headers['Content-Type'] = 'text/json'
    dj_key = self.request.get("dj_key")
    dj = cache.getDj(dj_key)
    errors = "";
    if not dj:
      errors = "Unable to find DJ. "
    permission_key = self.request.get("permission_key")
    permission = Permission.get(key=permission_key)
    if not permission:
      errors = "Unable to find permission."
    if errors:
      self.response.out.write(json.dumps({
        'err': errors,
      }))
      return
    action = self.request.get("action")
    if action == "add":
      if permission.hasDj(dj):
        errors = ("%s is already in the %s permission list."%
                  (dj.p_fullname, permission.p_title))
      else:
        permission.addDj(dj)
        status = ("Successfully added %s to %s permission list."%
                  (dj.fullname, permission.title))
    if action == "remove":
      if dj.key() not in permission.dj_list:
        errors = dj.fullname + " was not in the " + permission.title + " permission list."
      else:
        permission.dj_list.remove(dj.key())
        status = "Successfully removed " + dj.fullname + " from " + permission.title + " permission list."
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
#     - makeNew: AJAXically adds "new" status back to an album if made old by mistake
#     - manual: NOT AJAX - adds an album which has been typed in by hand.

class ManageAlbums(UserHandler):
  @authorization_required("Manage Albums")
  def get(self):
    new_album_list = None
 #   new_album_html = memcache.get("manage_new_albums_html")
 #   if not new_album_html:
    new_album_list = cache.getNewAlbums()
    new_album_html = template.render(
      get_path("dj_manage_new_albums_list.html"), {'new_album_list': new_album_list}
      )
    memcache.set("manage_new_albums_html", new_album_html)
    template_values = {
      'new_album_list': new_album_list,
      'new_album_html': new_album_html,
      'session': self.session,
      'flash': self.flash,
    }
    self.response.out.write(template.render(get_path("dj_manage_albums.html"), template_values))
  
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
          'err': "An error occurred.  Please try again, or if this keeps happening, select a different album."
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
        'tracks': [t.firstChild.nodeValue for t in i.getElementsByTagName("Track")],
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
      if not cache.setAlbumIsNew(key, is_new=True):
        self.response.out.write(json.dumps({'err': "Album not found. Please try again."}))
        return
      self.response.out.write(json.dumps({'msg': "Made new."}))
      return

    elif action == "makeOld":
      # We're removing the "new" marking from an album
      self.response.headers['Content-Type'] = 'text/json'
      key = self.request.get("key")
      album = cache.getAlbum(key=key)
      if not cache.setAlbumIsNew(key, is_new=False):
        self.response.out.write(json.dumps({'err': "Album not found. Please try again."}))
        return
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
          self.session.add_flash("The image you provided was too large. "
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
          self.session.add_flash("The URL you provided could not be downloaded. "
                                 "Hit back and try again.")
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
          self.session.add_flash("The URL you provided could not be downloaded. "
                                 "Hit back and try again.")
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
    cache.putAlbum(title=title,
                   artist=artist,
                   tracks=tracks,
                   asin=asin,
                   cover_small=cover_small,
                   cover_large=cover_large)

    if self.request.get("ajax"):
      self.response.out.write(
        json.dumps({
            'msg': "Album successfully added.",
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
    ('/dj/charts/?', ViewCharts),
    ('/blog/([^/]*)/([^/]*)/edit/?', EditBlogPost),
    ('/dj/newpost/?', NewBlogPost),
    ('/dj/event/?', NewEvent),
    ('/dj/myself/?', MySelf),
    ('/dj/removeplay/?', RemovePlay),
    ('/dj/event/([^/]*)/?', EditEvent),
    ('/dj/reset/?.*', RequestPassword),
    ], debug=True, config=webapp2conf)
