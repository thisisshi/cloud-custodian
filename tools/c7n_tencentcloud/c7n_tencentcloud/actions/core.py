# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import BaseAction


class TencentCloudBaseAction(BaseAction):
    t_api_method_name: str = ""  # api method name

    def __init__(self, data=None, manager=None, log_dir=None):
        super().__init__(data, manager, log_dir)
        self.resource_type = self.manager.get_model()

    def get_client(self):
        return self.manager.get_client()

    def process(self, resources):
        pass

    def get_request_params(self, resources):
        pass

    def get_permissions(self):
        pass
