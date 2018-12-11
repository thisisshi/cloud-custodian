# Copyright 2018 Capital One Services, LLC
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

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.tags import Tag, TagDelayedAction, RemoveTag
from c7n.utils import local_session


@resources.register('fsx')
class FSx(QueryResourceManager):
    filter_registry = FilterRegistry('fsx.filters')
    action_registry = ActionRegistry('fsx.actions')
    permissions = ('fsx:ListTagForResource',)

    class resource_type(object):
        service = 'fsx'
        enum_spec = ('describe_file_systems', 'FileSystems', None)
        id = 'FileSystemId'
        date = 'CreationTime'
        dimension = None
        filter_name = None

    def get_tags(self, resources):
        client = local_session(self.session_factory).client('fsx')
        for r in resources:
            r['Tags'] = client.list_tags_for_resource(
                ResourceArn=r['ResourceARN'])['Tags']
        return resources


@FSx.action_registry.register('mark-for-op')
class MarkForOpFileSystem(TagDelayedAction):
    concurrency = 2
    batch_size = 5
    permissions = ('fsx:TagResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('fsx')
        for r in resources:
            client.tag_resource(ResourceARN=r['ResourceARN'], Tags=tags)


@FSx.action_registry.register('tag')
class TagFileSystem(Tag):
    concurrency = 2
    batch_size = 5
    permissions = ('fsx:TagResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('fsx')
        for r in resources:
            client.tag_resource(ResourceARN=r['ResourceARN'], Tags=tags)


@FSx.action_registry.register('remove-tag')
class UnTagFileSystem(RemoveTag):
    concurrency = 2
    batch_size = 5
    permissions = ('fsx:UntagResource',)

    def process_resource_set(self, resources, tag_keys):
        client = local_session(self.manager.session_factory).client('fsx')
        for r in resources:
            client.untag_resource(ResourceARN=r['ResourceARN'], TagKeys=tag_keys)
