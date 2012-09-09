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
  # Amazon is kind of obnoxious with the API and there's very
  # little available online to help.
  # their page is like a maze.
  # hopefully this won't have to change any time soon - Seth
  # I agree - Harrison.
  pairs = [
    "Service=AWSECommerceService",
    "AWSAccessKeyId=AKIAJIXECWA77X5XX4DQ",
    "AssociateTag=w0c3d-20",
    "Operation=ItemSearch",
    "Keywords=" + keywords,
    "ResponseGroup=Images%2CTracks%2CItemAttributes",
    "SearchIndex=Music",
    "Version=2011-08-01",
    "Timestamp=" + urllib.quote_plus(datetime.datetime.now()
                                     .strftime("%Y-%m-%dT%H:%M:%SZ")),
  ]
  # It's been broken for the past few months because I didn't realize
  # that you have to sort the pairs first. Don't make the same mistake
  #   - Harrison
  pairs.sort()
  string = "&".join(pairs)
  hashstring = "GET\nwebservices.amazon.com\n/onca/xml\n" + string
  dig = hmac.new("6oYjAsiXTz8xZzpKZC8zkqXnkYV72CNuCRh9hUsQ",
                 msg=hashstring,
                 digestmod=hashlib.sha256).digest()
  coded = dig.encode("base64").strip()
  finalurl = ("http://webservices.amazon.com/onca/xml?" + string +
              "&Signature=" + urllib.quote_plus(coded))
  logging.warning(hashstring)
  logging.warning("Final URL: " + finalurl)
  xmldata = urlfetch.fetch(unicode(finalurl)).content
  logging.warning("XML Data: " + xmldata)
  xmldoc = minidom.parseString(xmldata)
  items = xmldoc.getElementsByTagName("Item")
  # makes sure we only look at items with images,
  # otherwise bad things can happen
  items = filter(lambda i: len(i.getElementsByTagName("SmallImage")) > 0, items)
  # same with medium image
  items = filter(lambda i: len(i.getElementsByTagName("MediumImage")) > 0,
                 items)
  # same with large image
  items = filter(lambda i: len(i.getElementsByTagName("LargeImage")) > 0, items)
  # and track
  items = filter(lambda i: len(i.getElementsByTagName("Track")) > 0, items)
  # and artist
  items = filter(lambda i: len(i.getElementsByTagName("Artist")) > 0, items)
  # and title
  items = filter(lambda i: len(i.getElementsByTagName("Title")) > 0, items)
  return items
