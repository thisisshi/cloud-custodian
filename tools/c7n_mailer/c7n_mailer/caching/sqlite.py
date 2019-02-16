import json
import sqlite3
from .cache import CacheEngine


class LocalSqlite(CacheEngine):
    # Use sqlite as a local cache for folks not running the mailer in lambda,
    # avoids extra daemons as dependencies. This normalizes the methods to
    # set/get functions, so you can interchangeable decide which caching system
    # to use, a local file, or memcache, redis, etc If you don't want a redis
    # dependency and aren't running the mailer in lambda this works well

    def __init__(self, file_name):
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
