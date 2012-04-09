#Secret Access Key: 6oYjAsiXTz8xZzpKZC8zkqXnkYV72CNuCRh9hUsQ
#Access Key ID: AKIAJIXECWA77X5XX4DQ

from __future__ import with_statement

import datetime
import time

from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext import blobstore
from google.appengine.api import files
from passwd_crypto import hash_password, check_password
import logging

from models import *

# class DictModel(db.Model):
#   SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)
#   def to_dict():
#     output = {}

#     for key, prop in self.properties().iteritems():
#       if (isinstance(prop, db.ReferenceProperty) or
#           isinstance(prop, blobstore.BlobReferenceProperty())):
#         output['%s_key'%key] = getattr(self, '%s_key'%key)
#       else:
#         value = getattr(self, key)

#         if value is None or isinstance(value, SIMPLE_TYPES):
#           output[key] = value
#         elif isinstance(value, datetime.date):
#           # Convert date/datetime to ms-since-epoch ("new Date()").
#           ms = time.mktime(value.utctimetuple()) * 1000
#           ms += getattr(value, 'microseconds', 0) / 1000
#           output[key] = int(ms)
#         elif isinstance(value, db.GeoPt):
#           output[key] = {'lat': value.lat, 'lon': value.lon}
#         else:
#           raise ValueError('cannot encode ' + repr(prop))

#     return output

def str_or_none(obj):
  if obj is not None:
    return str(obj)
  else:
    return None

class ApiModel(db.Model):
  def to_json():
    pass




## The following should never need to run again
# However, the idea is that it will remain for educational purposes
# i.e. another example of how we use the Blobstore
# it is somewhat hackish; in order to give the covers a filename
# it is generally bad, bad practice to use underscore-prefixed
# things in other people's code. This is a warning.
def moveCoverToBlobstore(album):
  if not album.small_filetype:
    return

  from slughifi import slughifi
  fn = "%s_%s"%(slughifi(album.artist), slughifi(album.title))
  small_file = files.blobstore.create(mime_type=album.small_filetype,
                                      _blobinfo_uploaded_filename="%s_small.png"%fn)
  large_file = files.blobstore.create(mime_type=album.large_filetype,
                                      _blobinfo_uploaded_filename="%s_big.png"%fn)

  with files.open(small_file, 'a') as small:
    small.write(album.small_cover)
  with files.open(large_file, 'a') as large:
    large.write(album.large_cover)

  files.finalize(small_file)
  files.finalize(large_file)

  album.cover_small = files.blobstore.get_blob_key(small_file)
  album.cover_large = files.blobstore.get_blob_key(large_file)

  del album.small_cover
  del album.large_cover
  del album.large_filetype
  del album.small_filetype

  album.put()

def getEventsAfter(start, num=1000):
  return Event.all().filter("event_date >=", start).order("event_date").fetch(num)

def getLastPlay():
  last_play = memcache.get("last_play")
  if last_play is not None:
    return last_play
  else:
    logging.debug("Updating last_play memcache")
    play = Play.all().order("-play_date").get()
    if not memcache.set("last_play", play):
      logging.error("Memcache set last play failed")

def addNewPlay(song, program, artist,
               play_date=datetime.datetime.now(), isNew=False):
  """
  If a DJ starts playing a song, add it and update the memcache.
  """
  last_play = memcache.get("last_play")
  play = Play(song=song,
              program=program,
              artist=artist,
              play_date=play_date,
              isNew=isNew)
  play.put()
  if last_play is None or play_date > last_play.play_date:
    memcache.set("last_play", play)
    # since we always check last 3 plays, this is hardcoded to update that
    # if you can come up with a better solution, please implement it (TODO)
    last_plays = memcache.get("last_3_plays")
    if last_plays is not None:
        memcache.set("last_3_plays",
                     [play] + last_plays[:2])

def getLastPosts(num):
  return BlogPost.all().order("-post_date").fetch(num)

def artistAutocomplete(prefix):
  prefix = prefix.lower()
  artists_full = ArtistName.all().filter("lowercase_name >=", prefix).filter("lowercase_name <", prefix + u"\ufffd").fetch(10)
  artists_sn = ArtistName.all().filter("search_name >=", prefix).filter("search_name <", prefix + u"\ufffd").fetch(10)
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
  return albums

def getLastNPlays(num):
  last_plays = memcache.get("last_plays")
  if last_plays is not None and len(last_plays) >= num:
    logging.info("Using memcache for last_plays")
    return last_plays[:num]
  else:
    logging.debug("Updating last_%s_plays memcache"%num)
    plays = Play.all().order("-play_date").fetch(num)
    if not memcache.set("last_plays", plays):
      logging.error("Memcache set last num plays failed")
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

def getRetardedNumberOfPlaysForDate(date, program=None):
  plays = Play.all().order("-play_date")
  if program:
    plays.filter("program =", program)

  after = date - datetime.timedelta(hours=72)
  before = date + datetime.timedelta(hours=72)
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
  psa = Psa.all().order("-play_date").get()
  return psa

def getProgramsByDj(dj):
  # TODO - handle a case in which a DJ actually has (and needs) 10 shows
  return Program.all().filter("dj_list =", dj).fetch(10)

def getNewAlbums(num=1000, page=0, byArtist=False):
  albums = Album.all(keys_only=True).filter("isNew =", True)
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
  albums = Album.all().filter("asin =", asin).get()
  return albums

def getArtist(artist):
  artists = ArtistName.all().filter("lowercase_name =", artist.lower()).get()
  return artists

def getProgramBySlug(slug):
  programs = Program.all().filter("slug =", slug).get()
  return programs

def getPSAsInRange(start, end):
  psas = Psa.all().filter("play_date >=", start).filter("play_date <=", end).fetch(1000)
  return psas

def getIDsInRange(start, end):
  ids = StationID.all().filter("play_date >=", start).filter("play_date <=", end).fetch(1000)
  return ids

def getNewPlaysInRange(start, end):
  plays = Play.all().filter("isNew =", True).filter("play_date >=", start).filter("play_date <=", end).fetch(1000)
  return plays

def getPostBySlug(post_date, slug):
  day_start = datetime.datetime(post_date.year, post_date.month, post_date.day)
  day_end = day_start + datetime.timedelta(days=1)
  posts = BlogPost.all().filter("post_date >=", day_start).filter("post_date <=", day_end).filter("slug =", slug).get()
  return posts

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
