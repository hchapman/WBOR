from google.appengine.ext import ndb

class Program(ndb.Model):
  title = ndb.StringProperty()
  slug = ndb.StringProperty()
  desc = ndb.StringProperty()
  dj_list = ndb.KeyProperty(repeated=True)
  page_html = ndb.TextProperty()
  top_artists = ndb.StringProperty(repeated=True)
  top_playcounts = ndb.IntegerProperty(repeated=True)
  current = ndb.BooleanProperty(default=False)

class Album(ndb.Model):
  title = ndb.StringProperty(required=True)
  asin = ndb.StringProperty()
  lower_title = ndb.ComputedProperty(lambda self: self.title.lower())
  artist = ndb.StringProperty()
  add_date = ndb.DateTimeProperty()
  isNew = ndb.BooleanProperty(default=False)
  songList = ndb.KeyProperty(repeated=True)
  cover_small = ndb.BlobKeyProperty()
  cover_large = ndb.BlobKeyProperty()

class Song(ndb.Model):
  title = ndb.StringProperty()
  artist = ndb.StringProperty()
  album = ndb.KeyProperty(kind=Album)

class Play(ndb.Model):
  song = ndb.KeyProperty(kind=Song)
  program = ndb.KeyProperty(kind=Program)
  play_date = ndb.DateTimeProperty()
  isNew = ndb.BooleanProperty() # TODO: Change from CamelCase to under_scores
  artist = ndb.StringProperty()

class ArtistName(ndb.Model):
  artist_name = ndb.StringProperty()
  lowercase_name = ndb.StringProperty()
  search_name = ndb.StringProperty()
  search_names = ndb.StringProperty(repeated=True)