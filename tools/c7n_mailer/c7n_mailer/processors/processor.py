import logging


class Processor(object):
    def __init__(self, cache_engine, ldap_lookup, *args, **kwargs):
        self.log = logging.getLogger(__name__)
