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
from c7n_kube.labels import LabelAction


@resources.register('volume')
class PersistentVolume(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        namespaced = False
        enum_spec = ('list_persistent_volume', 'items', None)


@PersistentVolume.action_registry.register('label')
class LabelPersistentVolume(LabelAction):
    __doc__ = LabelAction.__doc__.format(resource='volume')
    permissions = ('PatchPersistentVolume',)
    method_spec = {'op': 'patch_persistent_volume'}


@resources.register('volume-claim')
class PersistentVolumeClaim(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        namespaced = True
        enum_spec = ('list_persistent_volume_claim_for_all_namespaces', 'items', None)


@PersistentVolumeClaim.action_registry.register('label')
class LabelPersistentVolumeClaim(LabelAction):
    __doc__ = LabelAction.__doc__.format(resource='volume-claim')
    permissions = ('PatchNamespacedPersistentVolumeClaim',)
    method_spec = {'op': 'patch_namespaced_persistent_volume_claim'}
