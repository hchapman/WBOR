from base_models import *

from google.appengine.ext import db, ndb

import logging

# Children have a cache of most-recently added elements.
# This is like LastCacheable, but does not include any time data
@accepts_raw
class NewCacheable(CachedModel):
  NEW = None

  def __init__(self, _new=False, **kwargs):
    logging.error(kwargs)
    super(NewCacheable, self).__init__(**kwargs)
    self._new = _new

  def put(self):
    super(NewCacheable, self).put()
    self._new = False

  @quantummethod
  def add_to_new_cache(obj, key=None, new=None):
    logging.info("Maybe Newcache %s %s %s"%(key, new, obj))
    key = obj.key if key is None else key
    try:
      new = obj._new if new is None else new
    except AttributeError:
      new = False
    logging.info("Maybe Newcache %s %s %s"%(key, new, obj))
    if not new:
      return

    cached = QueryCache.fetch(obj.NEW)
    logging.info("Newcached %s"%obj)
    cached.prepend(key)
    cached.save()

  @classmethod
  def purge_from_new_cache(cls, key):
    cached = QueryCache.fetch(cls.NEW)
    try:
      cached.remove(key)
      cached.save()
    except:
      pass

  @classmethod
  def get_new(cls, num=-1, keys_only=False):
    if num != -1 and num < 1:
      return None

    only_one = False
    if num == -1:
      only_one = True
      num = 1

    cached = QueryCache.fetch(cls.NEW)

    new_objs = []
    cached_keys = ()

    if cached.need_fetch(num):
      if cached.cursor:
        try:
          num_to_fetch = num - len(cached)
          new_objs,cursor,more = cls.get(order=(-ndb.Model.key),
            num=num_to_fetch, page=True, cursor=cached.cursor)
          cached_keys = tuple(cached.results)
          cached.extend_by([obj.key for obj in new_objs],
                           cursor=cursor, more=more)
        except db.BadRequestError:
          new_objs,cursor,more = cls.get(order=(-ndb.Model.key),
            num=num, page=True, cursor=None)
          cached_keys = tuple()
          cached.set([obj.key for obj in new_objs],
                     cursor=cursor, more=more)
      else:
        new_objs,cursor,more = cls.get(order=(-ndb.Model.key),
                                       num=num, page=True, cursor=None)
        cached_keys = tuple()
        cached.set([obj.key for obj in new_objs],
                   cursor=cursor, more=more)
      cached.save()
    else:
      cached_keys = tuple(cached.results)

    if not cached:
      return [] if not only_one else None

    if keys_only:
      return cached.results[0] if only_one else cached.results[:num]
    else:
      if only_one:
        return cls.get(cached.results[0])
      return (cls.get(cached_keys) + new_objs)[:num]

@accepts_raw
class Searchable(CachedModel):
  def __init__(self, **kwargs):
    logging.error(kwargs)
    super(Searchable, self).__init__(**kwargs)

  def _search_fields(self):
    raise NotImplementedError()

  def has_prefix(self, prefix):
    prefixes = prefix.split()

    for search_field in self._autocomplete_fields:
      check_prefixes = prefixes
      for prefix in check_prefixes:
        if search_field.startswith(prefix):
          prefixes.remove(prefix)
          if len(prefixes) == 0:
            return True
          break
    return False

  @classmethod
  def _autocomplete_query(cls, field, prefix):
    return cls._RAW.query().filter(
      ndb.AND(field >= prefix,
              field < (prefix + u"\ufffd")))

  # As it is now, autocomplete is a little wonky. One thing worth
  # noting is that we search cache a bit more effectively than the
  # datastore: for example, if you've got a cached prefix "b" and
  # bear in heaven was there, then you're able to just search "b i
  # h" and cut out other stragglers like "Best Band Ever". Right
  # now, we can't search datastore this efficiently, so this is kind
  # of hit or miss.
  @classmethod
  def autocomplete(cls, prefix):
    prefix = prefix.lower().strip()

    # Go into memory and grab all (some?) of the caches for this
    # prefix and earlier
    cache_list = [SetQueryCache.fetch(cls.COMPLETE %prefix[:i+1]) for
                  i in range(len(prefix))]

    best_data = set()
    for prelen, cached_query in enumerate(cache_list):
      if len(cached_query) > 0:
        best_data = cached_query.results
      else:
        best_data = set(
          filter(lambda obj: cls.get(obj).has_prefix(prefix[:prelen+1]),
                 best_data))
        cached_query.set(best_data)
        cached_query.save()

    cached = cache_list.pop() # Get the cache for the relevant prefix
    if cached.need_fetch(cls.AC_FETCH_NUM):
      # We have to fetch some keys from the datastore
      if cached.cursor is None:
        cursors = dict()
      else:
        cursors = cached.cursor

      cache_results = set()
      add_objs = set()
      more_results = False
      for (query, key) in cls._autocomplete_queries(prefix):
        cursor = cursors.get(key)
        try:
          # Try to continue an older query
          num = cls.AC_FETCH_NUM - len(cached)

          obj_keys, new_cursor, more = query.fetch_page(
            num, start_cursor=cursor,
            keys_only=True)

          cache_results |= cached.results

        except db.BadRequestError:
          # Unable to continue the older query. Run a new one.
          obj_keys, new_cursor, more = query.fetch_page(
            num, keys_only=True)

        cursors[key] = new_cursor
        add_objs |= set(obj_keys)
        more_results = more_results or more

      obj_keys = cached.results | add_objs

      # We've got a bunch of artistnames for this prefix, so let's
      # update all of our cached queries: this one, and all supqueries
      cached.extend_by(add_objs, cursors, more)
      cached.save()

      for cached_query in reversed(cache_list):
        cached_query.extend(add_objs)
        cached_query.save()
    else:
      # We don't have to fetch anything!
      obj_keys = cached.results

    return cls.get(obj_keys)

  # TODO: Real searching (possibly using experimental Search API)
  @classmethod
  def search(cls, query):
    return cls.autocomplete(query)