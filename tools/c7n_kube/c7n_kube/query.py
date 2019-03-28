# Copyright 2017-2019 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import jmespath
import logging
import six

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session

log = logging.getLogger('custodian.k8s.query')


class ResourceQuery(object):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        session = local_session(self.session_factory)
        client = session.client(m.group, m.version)

        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)
        return self._invoke_client_enum(client, enum_op, params, path)

    def _invoke_client_enum(self, client, enum_op, params, path):
        res = getattr(client, enum_op)(**params).to_dict()
        if path and path in res:
            res = res.get(path)
        return res


@sources.register('describe-kube')
class DescribeSource(object):
    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        if query is None:
            return self.query.filter(self.manager)
        else:
            # k8s list api doesn't allow for filtering on attributes, so we have to do
            # client side filtering ourselves
            resources = self.query.filter(self.manager)
            expr = jmespath.compile(self.manager.get_model().id)
            return [r for r in resources if expr.search(r) in query]

    def get_permissions(self):
        return ()

    def augment(self, resources):
        return resources


class QueryMeta(type):
    """metaclass to have consistent action/filter registry for new resources."""
    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(
                '%s.filters' % name.lower())
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(
                '%s.actions' % name.lower())

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


@six.add_metaclass(QueryMeta)
class QueryResourceManager(ResourceManager):
    def __init__(self, data, options):
        super(QueryResourceManager, self).__init__(data, options)
        self.source = self.get_source(self.source_type)

    def get_permissions(self):
        return ()

    def get_source(self, source_type):
        return sources.get(source_type)(self)

    def get_client(self):
        client = local_session(self.session_factory).client(
            self.resource_type.group,
            self.resource_type.version)
        return client

    def get_model(self):
        return self.resource_type

    def get_cache_key(self, query):
        return {'source_type': self.source_type, 'query': query}

    @property
    def source_type(self):
        return self.data.get('source', 'describe-kube')

    def get_resource_query(self):
        if 'query' in self.data:
            return {'filter': self.data.get('query')}

    def resources(self, query=None):
        q = query or self.get_resource_query()
        key = self.get_cache_key(q)
        resources = self.augment(self.source.get_resources(q))
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def _get_cached_resources(self, ids):
        key = self.get_cache_key(None)
        if self._cache.load():
            resources = self._cache.get(key)
            if resources is not None:
                self.log.debug("Using cached results for get_resources")
                id_set = set(ids)
                expr = jmespath.compile(self.get_model().id)
                breakpoint()
                return [r for r in resources if expr.search(r) in id_set]
        return None

    def get_resources(self, ids, cache=True, augment=True):
        if cache:
            resources = self._get_cached_resources(ids)
            if resources is not None:
                return resources
        try:
            resources = self.source.get_resources(ids)
            if augment:
                resources = self.augment(resources)
            return resources
        except Exception as e:
            self.log.warning("event ids not resolved: %s error:%s" % (ids, e))
            return []

    def augment(self, resources):
        return resources


class TypeMeta(type):
    def __repr__(cls):
        return "<TypeInfo group:%s version:%s>" % (
            cls.group,
            cls.version)


@six.add_metaclass(TypeMeta)
class TypeInfo(object):
    group = None
    version = None
    enum_spec = ()
    namespaced = True
    name = id = 'metadata.name'
