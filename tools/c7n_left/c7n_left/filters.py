# Copyright The Cloud Custodian Authors.  # SPDX-License-Identifier: Apache-2.0
#
import subprocess
import json
import itertools

from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter, ValueFilter, OPERATORS
from c7n.utils import type_schema


class Traverse(Filter):
    """Traverse the resource graph.

    This filter allows going from a source node across multiple hops
    to a set of related nodes with multi attributes matching at
    destination.


    .. code-block:: yaml

      policies:
        - name: s3-encryption
          description: ensure buckets are using kms encryption
          resource: terraform.aws_s3_bucket
          filters:
            - not:
               - type: traverse
                 resources: aws_s3_bucket_server_side_encryption_configuration
                 attrs:
                  - rule.apply_server_side_encryption_by_default.sse_algorithm: aws:kms


    This example will traverse multiple hops from and verify attributes at the destination.

    .. code-block:: yaml

      policies:
        - name: app-runner-check-vpc
          description: ensure app runner instances are only connected to the dev vpc
          resource: terraform.aws_app_runner
          filters:
            - network_configuration: present
            - type: traverse
              resources: [aws_apprunner_vpc_connector, aws_subnet, aws_vpc]
              attrs:
               - type: value
                 key: tag:Env
                 value: Dev
                 op: not-equal
    """

    schema = type_schema(
        "traverse",
        resources={
            "oneOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "string"},
            ]
        },
        count={"type": "integer"},
        attrs={
            "type": "array",
            "items": {
                "oneOf": [
                    {"$ref": "#/definitions/filters/valuekv"},
                    {"$ref": "#/definitions/filters/value"},
                ]
            },
        },
        required=("resources",),
        **{"count-op": {"$ref": "#/definitions/filters_common/comparison_operators"}},
    )

    _vfilters = None

    @property
    def annotation_key(self):
        return "c7n:%s" % ("-".join(self.type_chain))

    @property
    def type_chain(self):
        type_chain = self.data["resources"]
        if isinstance(type_chain, str):
            type_chain = [type_chain]
        return type_chain

    def process(self, resources, event):
        results = []
        for r in resources:
            working_set = (r,)
            for target_type in self.type_chain:
                working_set = self.resolve_refs(
                    target_type, working_set, event["graph"]
                )
            matched = self.match_attrs(working_set)
            if not self.match_cardinality(matched):
                continue
            if matched:
                r[self.annotation_key] = matched
            results.append(r)
        return results

    def get_attr_filters(self):
        if self._vfilters:
            return self._vfilters
        vfilters = []
        filter_class = ValueFilter
        for v in self.data.get("attrs", []):
            if isinstance(v, dict) and v.get("type"):
                filter_class = self.manager.filter_registry[v["type"]]
            vf = filter_class(v, self.manager)
            vf.annotate = False
            vfilters.append(vf)
        self._vfilters = vfilters
        return vfilters

    def match_cardinality(self, matched):
        count = self.data.get("count", None)
        if count is None:
            if not matched:
                return False
            return True
        op = OPERATORS[self.data.get("count-op", "eq")]
        if op(len(matched), count):
            return True
        return False

    def match_attrs(self, working_set):
        vfilters = self.get_attr_filters()
        found = True
        results = []
        for w in working_set:
            for v in vfilters:
                if not v(w):
                    found = False
                    break
            if not found:
                continue
            results.append(w)
        return results

    def resolve_refs(self, target_type, working_set, graph):
        return itertools.chain(*[graph.get_refs(w, target_type) for w in working_set])


class Infracost(ValueFilter):
    """
    Infracost filter

    Filter by totalMonthlyCost, totalHourlyCost, or individual attributes
    from a Infracost breakdown. These costs are estimations that do not
    take into consideration usage, savings plans, or discounts, etc.

    :example:

    .. code-block:: yaml

       policies:
         - name: find-high-cost-instances
           resource: terraform.aws_instance
           metadata:
             severity: high
           filters:
             - type: infracost
               key: monthlyCost
               value: 1000
               op: gt

    .. code-block:: hcl

        data "aws_ami" "ubuntu" {
          most_recent = true

          filter {
            name   = "name"
            values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
          }

          filter {
            name   = "virtualization-type"
            values = ["hvm"]
          }

          owners = ["099720109477"] # Canonical
        }

        resource "aws_instance" "web" {
          ami           = data.aws_ami.ubuntu.id
          instance_type = "p3dn.24xlarge"

          tags = {
            Name = "HelloWorld"
          }
        }

    """

    schema = type_schema("infracost", rinherit=ValueFilter.schema)
    annotation_key = "Infracost"
    cost_map = {}

    def validate(self):
        try:
            subprocess.check_output(
                ['infracost'],
                stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            raise PolicyValidationError(
                "infracost command not found, ensure that infracost is available in $PATH"
            )

    def _cast_costs(self, entry):
        """
        Cost/Quantity/Price values are all strings, so we need to
        cast them to floats to be able to do meaningful value filter
        operations on the resulting infracost breakdown
        """
        for k, v in entry.items():
            if isinstance(v, dict):
                entry[k] = self._cast_costs(v)
            if isinstance(v, list):
                for idx, l in enumerate(v):
                    if isinstance(l, dict):
                        v[idx] = self._cast_costs(l)
            k_l = k.lower()
            if (
                k_l.endswith("cost")
                or k_l.endswith("price")
                or k_l.endswith("quantity")
            ):
                if not v:
                    continue
                entry[k] = float(v)
        return entry

    def get_infracost_breakdown(self, source_dir):
        # cache it here in memory cache so we dont have to call infracost
        # more than once per source directory
        cache_key = f"infracost-filter-breakdown-{source_dir}"
        breakdown = self.manager._cache.get(cache_key)
        if breakdown:
            return breakdown

        breakdown = subprocess.check_output(
            [
                "infracost",
                "breakdown",
                "--path",
                source_dir,
                "--include-all-paths",
                "--format=json",
            ],
            # suppress infracost logging
            stderr=subprocess.DEVNULL,
        )
        breakdown = json.loads(breakdown.decode("utf-8"))
        self.manager._cache.save(cache_key, breakdown)
        return breakdown

    def get_cost_map(self):
        source_dir = str(self.manager.ctx.options.source_dir)
        res = self.get_infracost_breakdown(source_dir)

        # cache the cost map so we dont have to remap resources to
        # their infracost results
        cache_key = f"infracost-filter-breakdown-cost-map-{source_dir}"
        cost_map = self.manager._cache.get(cache_key)

        if cost_map:
            return cost_map

        cost_map = {}
        extra_keys = (
            'totalHourlyCost',
            'totalMonthlyCost',
            'pastTotalHourlyCost',
            'pastTotalMonthlyCost',
            'diffTotalHourlyCost',
            'diffTotalMonthlyCost',
        )

        for r in res["projects"]:
            for i in r["breakdown"].get("resources", []):
                # add all the extra keys
                for key in extra_keys:
                    i[key] = float(res.get(key, 0))
                cost_map[i["name"]] = i

        cost_map = self._cast_costs(cost_map)
        self.manager._cache.save(cache_key, cost_map)
        return cost_map

    def process(self, resources, event=None):
        cost_map = self.get_cost_map()
        for r in resources:
            r[f"c7n:{self.annotation_key}"] = cost_map.get(
                r["__tfmeta"]["path"], {})

        return super().process(resources)

    def __call__(self, r):
        return self.match(r.get(f"c7n:{self.annotation_key}", {}))
