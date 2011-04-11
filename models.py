#Secret Access Key: 6oYjAsiXTz8xZzpKZC8zkqXnkYV72CNuCRh9hUsQ
#Access Key ID: AKIAJIXECWA77X5XX4DQ

from google.appengine.ext import db
import datetime
from google.appengine.api import memcache

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
  current = db.BooleanProperty(default=False)

class ArtistName(db.Model):
  artist_name = db.StringProperty()
  lowercase_name = db.StringProperty()
  search_name = db.StringProperty()
  search_names = db.StringListProperty()

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
  artist = db.StringProperty()

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

class Event(db.Model):
  title = db.StringProperty()
  event_date = db.DateTimeProperty()
  desc = db.TextProperty()
  url = db.StringProperty()

def getEventsAfter(start, num=1000):
  return Event.all().filter("event_date >=", start).order("event_date").fetch(num)

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
  artists_full = ArtistName.all().filter("lowercase_name >=", prefix).filter("lowercase_name <", prefix + u"\ufffd").fetch(20)
  artists_sn = ArtistName.all().filter("search_name >=", prefix).filter("search_name <", prefix + u"\ufffd").fetch(20)
  artist_dict = {}
  all_artists = artists_full + artists_sn
  for a in all_artists:
    artist_dict[a.artist_name] = a
  artists = []
  for a in artist_dict:
    artists.append(artist_dict[a])
  artists = sorted(artists, key=lambda x: x.search_name)
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

def getPlaysForDate(date, program=None):
  plays = Play.all().order("-play_date")
  if program:
    plays.filter("program =", program)

  after = date - datetime.timedelta(hours=24) 
  before = date + datetime.timedelta(hours=24)
  plays = plays.filter("play_date >=", after)\
      .filter("play_date <=", before)
  plays = plays.order("-play_date").fetch(1000)

  return plays
    

def getPlaysBetween(program, before=None, after=None):
  plays = Play.all().filter("program =", program)
  if after:
    plays = plays.filter("play_date >=", after)
  if before:
    plays = plays.filter("play_date <=", before)
  plays = plays.order("play_date").fetch(1000)
  return plays

def getLastPlays(program, after=None, num=1000):  
  plays = Play.all().filter("program =", program)
  if after:
    plays = plays.filter("play_date >=", after)
  plays = plays.order("-play_date").fetch(num)
  return plays

def getLastPsa():
  psa = Psa.all().order("-play_date").fetch(1)
  if psa:
    return psa[0]
  else:
    return None

def getProgramsByDj(dj):
  return Program.all().filter("dj_list =", dj).fetch(100)

def getNewAlbums(num=1000, page=0, byArtist=False):
  albums = Album.all().filter("isNew =", True)
  if byArtist:
    albums = albums.order("artist")
  else:
    albums = albums.order("-add_date")
  albums = albums.fetch(num, offset=page*50)
  return albums

def getNewAlbumsAlphabetically(num=1000):
  return Album.all().filter("isNew =", True).order("artist").fetch(num)

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

def getNewPlaysInRange(start, end):
  plays = Play.all().filter("isNew =", True).filter("play_date >=", start).filter("play_date <=", end).fetch(1000)
  return plays

def getPostBySlug(post_date, slug):
  day_start = datetime.datetime(post_date.year, post_date.month, post_date.day)
  day_end = day_start + datetime.timedelta(days=1)
  posts = BlogPost.all().filter("post_date >=", day_start).filter("post_date <=", day_end).filter("slug =", slug).fetch(1)
  if posts:
    return posts[0]
  else:
    return None

def getTopSongsAndAlbums(start, end, song_num, album_num):
  #cached = memcache.get("topsongsandalbums")
  cached = None
  if cached:
    if cached[0]:
      return cached
  plays = getNewPlaysInRange(start=start, end=end)
  songs = {}
  albums = {}
  for p in plays:
    if p.song.key() in songs:
      songs[p.song.key()][0] += 1
    else:
      songs[p.song.key()] = [1, p.song.title, p.song.artist, p.song.album.title]
    if p.song.album.key() in albums:
      albums[p.song.album.key()][0] += 1
    else:
      albums[p.song.album.key()] = [1, p.song.album.title, p.song.album.artist]
  songs = [songs[s] for s in songs]
  albums = [albums[a] for a in albums]
  songs.sort()
  songs.reverse()
  albums.sort()
  albums.reverse()
  songs = songs[:song_num]
  albums = albums[:album_num]
  memcache.set("topsongsandalbums", (songs, albums), 60 * 60 * 3)
  return (songs, albums)

def getPrograms():
  """ Get programs from the database
  """
  return Program.all().order("title")


def artistSearchName(a):
  """ Saves names without the word "The" or "A" as the first word so you can find them.
  In other words, allows a search for "Magnetic Fields" to match "The Magnetic Fields".
  """
  a = a.lower()
  if a.startswith("the "):
    a = a[4:]
  if a.startswith("a "):
    a = a[2:]
  return a
