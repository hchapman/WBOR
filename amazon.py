import urllib
import time
import hmac
import base64
import datetime
import urllib
import hashlib
import logging
from xml.dom import minidom
from google.appengine.api import urlfetch

def productSearch(keywords):
  # Amazon is kind of obnoxious with the API and there's very little available online to help.
  # their page is like a maze.
  # hopefully this won't have to change any time soon.
  pairs = [
    'AWSAccessKeyId=AKIAJIXECWA77X5XX4DQ',
    "Keywords=" + keywords,
    "Operation=ItemSearch",
    "ResponseGroup=Images%2CTracks%2CItemAttributes",
    "SearchIndex=Music",
    "Service=AWSECommerceService",
    "Timestamp=" + urllib.quote_plus(datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")),
    "Version=2005-03-23",
  ]
  string = "&".join(pairs)
  hashstring = "GET\necs.amazonaws.com\n/onca/xml\n" + string
  dig = hmac.new("6oYjAsiXTz8xZzpKZC8zkqXnkYV72CNuCRh9hUsQ", msg=hashstring, digestmod=hashlib.sha256).digest()
  coded = base64.b64encode(dig).decode()
  finalurl = "http://ecs.amazonaws.com/onca/xml?" + string + "&Signature=" + urllib.quote_plus(coded)
  logging.warning("Final URL: " + finalurl)
  xmldata = urlfetch.fetch(finalurl).content
  logging.warning("XML Data: " + xmldata)
  xmldoc = minidom.parseString(xmldata)
  items = xmldoc.getElementsByTagName("Item")
  # makes sure we only look at items with images, otherwise bad things can happen
  items = filter(lambda i: len(i.getElementsByTagName("SmallImage")) > 0, items)
  # same with medium image
  items = filter(lambda i: len(i.getElementsByTagName("MediumImage")) > 0, items)
  # same with large image
  items = filter(lambda i: len(i.getElementsByTagName("LargeImage")) > 0, items)
  # and track
  items = filter(lambda i: len(i.getElementsByTagName("Track")) > 0, items)
  # and artist
  items = filter(lambda i: len(i.getElementsByTagName("Artist")) > 0, items)
  # and title
  items = filter(lambda i: len(i.getElementsByTagName("Title")) > 0, items)
  return items