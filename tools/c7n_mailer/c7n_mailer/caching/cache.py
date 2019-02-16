import logging
import json
import redis


class CacheEngine(object):
    def __init__(self):
        """
        Cache Engine

        engine_type is one of: 'redis' or 'sqlite'
        engine_config is one of:
          - redis:
            {'redis_host': str, 'redis_port: int}
          - sqlite:
            {'ldap_cache_file': str}
        """
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.INFO)
        self.connection = None

    def set_connection(self, engine_type, engine_config):
        if engine_type == 'redis':
            self.connection = Redis(
                host=engine_config['redis_host'],
                port=engine_config['redis_port'],
                db=0
            )
        elif engine_type == 'sqlite':
            try:
                import sqlite3 # noqa
            except ImportError:
                raise RuntimeError('No sqlite available: stackoverflow.com/q/44058239')
            self.connection = LocalSqlite(engine_config['ldap_cache_file'])

    def __call__(self, f):
        """
        Any decorated function must return their values in the format:

        return_value, items_to_cache

        And must have a `key` arg in the function signature

        where items_to_cache is a dictionary of values to cache in key value pairs

        e.g. 'returnvalue', {'key': 'value', 'key2': 'value2'}
        """
        def call(*args, **kwargs):
            self.log.info('Getting cached value with key: %s' % kwargs['key'])
            result = self.get(kwargs['key'])
            if result:
                self.log.info('Found cached value: %s' % result)
                return result
            result, cache = f(*args, **kwargs)
            for k, v in cache.items():
                self.log.info('Setting cache, key:%s value:%s' % (k, v))
                try:
                    self.set(k, v)
                except Exception:
                    self.log.error('Unable to set cache for %s, %s. Skipping.' % (k, v))
            return result

        if not self.connection:
            return f

        return call

    def get(self, key):
        if not hasattr(self.connection, 'get'):
            return None
        return self.connection.get(key)

    def set(self, key, value):
        if not hasattr(self.connection, 'set'):
            return None
        return self.connection.set(key, value)


class Redis(CacheEngine):
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


class LocalSqlite(CacheEngine):
    # Use sqlite as a local cache for folks not running the mailer in lambda,
    # avoids extra daemons as dependencies. This normalizes the methods to
    # set/get functions, so you can interchangeable decide which caching system
    # to use, a local file, or memcache, redis, etc If you don't want a redis
    # dependency and aren't running the mailer in lambda this works well

    def __init__(self, file_name):
        import sqlite3
        super(LocalSqlite, self).__init__()
        self.connection = sqlite3.connect(file_name)
        self.connection.execute('''CREATE TABLE IF NOT EXISTS ldap_cache(key text, value text)''')

    def get(self, key):
        sqlite_result = self.connection.execute("select * FROM ldap_cache WHERE key=?", (key,))
        result = sqlite_result.fetchall()
        if len(result) != 1:
            self.log.error(
                'Did not get 1 result from sqlite, something went wrong with key: %s' % key)
            return None
        return json.loads(result[0][1])

    def set(self, key, value):
        # note, the ? marks are required to ensure escaping into the database.
        self.connection.execute("INSERT INTO ldap_cache VALUES (?, ?)", (key, json.dumps(value)))
