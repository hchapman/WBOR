from google.appengine.ext import db

from tracks import Song
from program import Program

class Play(db.Model):
    song = db.ReferenceProperty(Song)
    program = db.ReferenceProperty(Program)
    play_date = db.DateTimeProperty()
    isNew = db.BooleanProperty() # TODO: Change from CamelCase to under_scores
    artist = db.StringProperty()