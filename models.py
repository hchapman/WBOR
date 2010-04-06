#Secret Access Key: 6oYjAsiXTz8xZzpKZC8zkqXnkYV72CNuCRh9hUsQ
#Access Key ID: AKIAJIXECWA77X5XX4DQ

from google.appengine.ext import db

class Dj(db.Model):
  fullname = db.StringProperty()
  lowername = db.StringProperty()
  email = db.StringProperty()
  username = db.StringProperty()
  password_hash = db.StringProperty()

class Program(db.Model):
  title = db.StringProperty()
  slug = db.StringProperty()
  desc = db.StringProperty(multiline=True)
  dj_list = db.ListProperty(db.Key)
  page_html = db.TextProperty()
  top_artists = db.StringListProperty()
  top_playcounts = db.ListProperty(int)

class ArtistName(db.Model):
  artist_name = db.StringProperty()
  lowercase_name = db.StringProperty()

class BlogPost(db.Model):
  title = db.StringProperty()
  text = db.TextProperty()
  post_date = db.DateTimeProperty()
  slug = db.StringProperty()

class Album(db.Model):
  title = db.StringProperty()
  asin = db.StringProperty()
  lower_title = db.StringProperty()
  artist = db.StringProperty()
  add_date = db.DateTimeProperty()
  isNew = db.BooleanProperty()
  large_cover = db.BlobProperty()
  small_cover = db.BlobProperty()
  large_filetype = db.StringProperty()
  small_filetype = db.StringProperty()
  songList = db.ListProperty(db.Key)

class Song(db.Model):
  title = db.StringProperty()
  artist = db.StringProperty()
  album = db.ReferenceProperty(Album)

class Play(db.Model):
  song = db.ReferenceProperty(Song)
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()
  isNew = db.BooleanProperty()

class Psa(db.Model):
  desc = db.StringProperty()
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()

class StationID(db.Model):
  program = db.ReferenceProperty(Program)
  play_date = db.DateTimeProperty()

class Permission(db.Model):
  title = db.StringProperty()
  dj_list = db.ListProperty(db.Key)

def getLastPlay():
  return Play.all().order("-play_date").fetch(1)[0]

def getPermission(label):
  p = Permission.all().filter("title =", label).fetch(1)
  if len(p) > 0:
    return p[0]
  else:
    return None

def getDjByEmail(email):
  d = Dj.all().filter("email =", email).fetch(1)
  if len(d) > 0:
    return d[0]
  else:
    return None

def getDjByUsername(username):
  d = Dj.all().filter("username =", username).fetch(1)
  if len(d) > 0:
    return d[0]
  else:
    return None

def djLogin(username, password):
  d = Dj.all().filter("username =", username).filter("password_hash =", password).fetch(1)
  if len(d) > 0:
    return d[0]
  else:
    return None

def hasPermission(dj, label):
  p = getPermission(label)
  return dj.key() in p.dj_list

def getLastPosts(num):
  return BlogPost.all().order("-post_date").fetch(num)

def artistAutocomplete(prefix):
  prefix = prefix.lower()
  artists = ArtistName.all().filter("lowercase_name >=", prefix).filter("lowercase_name <", prefix + u"\ufffd").fetch(30)
  return artists

def djAutocomplete(prefix):
  prefix = prefix.lower()
  djs = Dj.all().filter("lowername >=", prefix).filter("lowername <", prefix + u"\ufffd").fetch(30)
  return djs

def albumAutocomplete(prefix):
  prefix = prefix.lower()
  albums = Album.all().filter("lower_title >=", prefix).filter("lower_title <", prefix + u"\ufffd").fetch(30)

def getLastNPlays(num):
  plays = Play.all().order("-play_date").fetch(num)
  return plays

def getLastPlays(program, after=None):  
  plays = Play.all().filter("program =", program)
  if after:
    plays = plays.filter("play_date >=", after)
  plays = plays.order("-play_date").fetch(1000)
  return plays

def getLastPsa():
  psa = Psa.all().order("-play_date").fetch(1)
  if len(psa) > 0:
    return psa[0]
  else:
    return None

def getProgramsByDj(dj):
  return Program.all().filter("dj_list =", dj).fetch(100)

def getNewAlbums():
  return Album.all().filter("isNew =", True).order("-add_date").fetch(1000)

def getLastAlbums(num):
  return Album.all().order("-add_date").fetch(num)

def getAlbumByASIN(asin):
  albums = Album.all().filter("asin =", asin).fetch(1)
  if albums:
    return albums[0]
  else:
    return None

def getArtist(artist):
  artists = ArtistName.all().filter("lowercase_name =", artist.lower()).fetch(1)
  if artists:
    return artists[0]
  else:
    return None

def getProgramBySlug(slug):
  programs = Program.all().filter("slug =", slug).fetch(1)
  if programs:
    return programs[0]
  else:
    return None
    
def getPSAsInRange(start, end):
  psas = Psa.all().filter("play_date >=", start).filter("play_date <=", end).fetch(1000)
  return psas

def getIDsInRange(start, end):
  ids = StationID.all().filter("play_date >=", start).filter("play_date <=", end).fetch(1000)
  return ids

def addDjToPermission(dj, permission):
  if dj.key() not in permission.dj_list:
    permission.dj_list.append(dj.key())
  permission.put()

def removeDjFromPermission(dj, permission):
  if dj.key() in permission.dj_list:
    permission.dj_list.remove(dj.key())
  permission.put()

def getPermissions():
  return Permission.all().order("-title").fetch(100)

