import logging
from c7n_mailer.caching.cache import CacheEngine


cache = CacheEngine()
cache.set_connection(
    'redis',
    {'redis_host': 'localhost', 'redis_port': 6379}
)
log = logging.getLogger('c7n_mailer.cache.cache')
log.setLevel(logging.INFO)


@cache
def example_func(key):
    return key, {key: key}


val = example_func(key='asdfasdf')
print(val)
