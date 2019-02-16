import json
import redis
from c7n_mailer import cache


class Redis(cache.cache.CacheEngine):
    def __init__(self, host, port=6379, db=0):
        super(Redis, self).__init__()
        self.connection = redis.StrictRedis(host=host, port=port, db=db)

    def get(self, key):
        cache_value = self.connection.get(key)
        if cache_value:
            return json.loads(cache_value)

    def set(self, key, value):
        # redis can't write complex python objects like dictionaries as
        # values (the way memcache can) so we turn our dict into a json
        # string when setting, and json.loads when getting

        return self.connection.set(key, json.dumps(value))
