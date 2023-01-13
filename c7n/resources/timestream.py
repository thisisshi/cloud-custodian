from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import local_session
from c7n.tags import (
    TagDelayedAction,
    TagActionFilter,
    Tag as TagAction,
    RemoveTag as RemoveTagAction
)


class DescribeTimestream(DescribeSource):
    def augment(self, resources):
        for r in resources:
            client = local_session(self.manager.session_factory).client('timestream-write')
            r['Tags'] = client.list_tags_for_resource(ResourceARN=r['Arn'])['Tags']
        return resources


@resources.register('timestream-database')
class TimestreamDatabase(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'timestream-write'
        arn_type = ''
        name = 'DatabaseName'
        id = arn = 'Arn'
        enum_spec = ('list_databases', 'Databases', {})
        permissions = ('timestream-write:ListDatabases', )

    source_mapping = {
        'describe': DescribeTimestream,
    }


@resources.register('timestream-table')
class TimestreamTable(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'timestream-write'
        arn_type = ''
        name = 'TableName'
        id = arn = 'Arn'
        enum_spec = ('list_tables', 'Tables', {})
        permissions = ('timestream-write:ListTables', )

    source_mapping = {
        'describe': DescribeTimestream,
    }


@TimestreamDatabase.action_registry.register('tag')
@TimestreamTable.action_registry.register('tag')
class TimestreamTag(TagAction):
    def process_resource_set(self, client, resource_set, tags):
        for r in resource_set:
            client.tag_resource(ResourceARN=r['Arn'], Tags=tags)


@TimestreamDatabase.action_registry.register('remove-tag')
@TimestreamTable.action_registry.register('remove-tag')
class TimestreamRemoveTag(RemoveTagAction):
    def process_resource_set(self, client, resource_set, tag_keys):
        for r in resource_set:
            client.untag_resource(ResourceARN=r['Arn'], TagKeys=tag_keys)


TimestreamDatabase.action_registry.register('mark-for-op', TagDelayedAction)
TimestreamTable.action_registry.register('mark-for-op', TagDelayedAction)

TimestreamDatabase.filter_registry.register('marked-for-op', TagActionFilter)
TimestreamTable.filter_registry.register('marked-for-op', TagActionFilter)
