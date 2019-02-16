import logging
import re
from ldap3 import Connection
from ldap3.core.exceptions import LDAPSocketOpenError

from c7n_mailer.cache.cache import CacheEngine


class LdapLookup(object):

    Cache = CacheEngine()

    def __init__(self, uri, user, password, dn, email_key, manager_key, uid_key, uid_regex, cache):
        self.log = logging.getLogger(__name__)
        self.uri = uri
        self.user = user
        self.password = password
        self.email_key = email_key
        self.manager_key = manager_key
        self.uid_key = uid_key
        self.uid_regex = uid_regex
        self.attributes = ['displayName', self.uid_key, self.email_key, self.manager_key]
        self.connection = self.get_connection()

        LdapLookup.Cache = cache
        LdapLookup.Connection = self.connection

    def get_connection(self):
        """
        Initializes LDAP connection
        """
        try:
            return Connection(self.uri, user=self.user, passsword=self.password,
                auto_bind=True, receive_timeout=30, auto_referrals=False,)
        except LDAPSocketOpenError:
            self.log.error('Not able to establish connection with LDAP')
            return None

    @Cache
    def search(self, key):

        if not self.connection:
            return {}, {}

        self.connection.search(self.base_dn, key, attributes=self.attributes)

        if len(self.connection.entries) == 0:
            self.log.warning("user not found. base_dn: %s filter: %s", self.base_dn, key)
            return {}, {key: self.connection.entries[0]}
        elif len(self.connection.entries) > 1:
            self.log.warning("too many results for search %s", key)
            return {}, {key: self.connection.entries[0]}

        return self.connection.entries[0], {key: self.connection.entries[0]}

    @Cache
    def get_metadata_from_dn(self, key):
        metadata = {}
        cache_items = {}

        ldap_filter = '(%s=*)' % self.uid_key
        ldap_results = self.search(key, ldap_filter, attributes=self.attributes)

        if ldap_results:
            metadata = self.get_dict_from_ldap_object(ldap_results)
            cache_items = {key: metadata, metadata[self.uid_key]: metadata}

        return metadata, cache_items

    @Cache
    def get_metadata_from_uid(self, key):
        metadata = {}
        cache_items = {}

        key = key.lower()
        if self.uid_regex and not re.search(self.uid_regex, key):
            self.log.debug('uid does not match regex: %s %s' % (self.uid_regex, key))
            return metadata, cache_items

        ldap_filter = '(%s=%s)' % (self.uid_key, key)
        ldap_results = self.search(self.base_dn, ldap_filter, attributes=self.attributes)

        if ldap_results:
            metadata = self.get_dict_from_ldap_object(ldap_results)
            if metadata.get('dn'):
                cache_items = {metadata['dn']: metadata, key: metadata}
            else:
                cache_items = {key: {}}

        return metadata, cache_items

    def get_email_to_addrs_from_uid(self, uid, manager=False):
        to_addrs = []
        metadata = self.get_metadata_from_uid(uid)
        email = metadata.get(self.email_key, None)

        if email:
            to_addrs.append(email)

        if not manager:
            return to_addrs

        manager_dn = metadata.get(self.manager_key, None)
        if manager_dn:
            manager_email = self.get_metadata_from_dn(manager_dn).get(self.email_key)
            if manager_email:
                to_addrs.append(manager_email)

        return to_addrs

    def get_dict_from_ldap_object(self, ldap_user):
        metadata = {attr.key: attr.value for attr in ldap_user}
        metadata['dn'] = ldap_user.entry_dn

        email = metadata.get(self.email_key, None)
        uid = metadata.get(self.uid_key, None)

        if not email or not uid:
            return {}

        metadata[self.email_key] = email.lower()
        metadata[self.uid_key] = uid.lower()

        return metadata
