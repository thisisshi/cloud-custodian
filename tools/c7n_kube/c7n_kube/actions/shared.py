from c7n_kube.actions.core import DeleteResource
from c7n_kube.actions.labels import LabelAction
from c7n_kube.provider import resources as kube_resources

SHARED_ACTIONS = (DeleteResource, LabelAction)


for action in SHARED_ACTIONS:
    kube_resources.subscribe(kube_resources.EVENT_REGISTER, action.register_resources)
