# Copyright 2019 Capital One Services, LLC
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
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register('replication-controller')
class ReplicationController(QueryResourceManager):

    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        namespaced = True
        patch = 'patch_namespaced_replication_controller'
        delete = 'delete_namespaced_replication_controller'
        enum_spec = ('list_replication_controller_for_all_namespaces', 'items', None)
