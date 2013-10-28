from base_models import SetQueryCache
from google.appengine.ext import ndb

# TODO: Extend SetQueryCache so that cursor is a dict not a cursor
class AutocompleteCache(SetQueryCache):
  pass

def prefixize(term, sep=None):
  term = term.strip().lower()
  prefixes = [term[:i+1] for i in range(len(term))]
  # TODO: Improve this.
  return prefixes

def add_to_autocomplete_caches(key, cachekey_base, prefixes):
  for cache in [SetQueryCache.fetch(cachekey_base % prefix) for
                prefix in prefixes]:
    cache.add(key)
    cache.save()

def purge_from_autocomplete_caches(key, cachekey_base, prefixes):
  for cache in [SetQueryCache.fetch(cachekey_base % prefix) for
                prefix in prefixes]:
    try:
      cache.remove(key)
      cache.save()
    except KeyError:
      pass

def autocomplete_query(ndbcls, ndbprop, prefix):
  return nbscls.query().filter(
    ndb.AND(ndbprop >= prefix,
            ndbprop < (prefix + u"\ufffd")))