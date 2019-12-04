from c7n.filters import ValueFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.resources.ec2 import EC2
from c7n.resources.asg import ASG
from c7n.utils import local_session, type_schema, generate_arn


class ComputeOptimizerFilter(RelatedResourceFilter):
    """
    Compute Optimizer Filter

    Filter resources by their recommendations findings
    """

    schema = type_schema('compute-optimizer', rinherit=ValueFilter.schema)
    RelatedResource = 'computeoptimizer'  # dummy related resource

    def validate(self):
        pass

    def get_permissions(self):
        return ('ComputeOptimiser:%s' % self.recommendation_op,)

    def get_related_ids(self, resources):
        arns = []
        for r in resources:
            arns.append(generate_arn(
                service=self.manager.get_model().service,
                resource=r[self.manager.get_model().id],
                region=self.manager.region,
                account_id=self.manager.account_id,
                resource_type=self.manager.get_model().arn_type)
            )
        return arns

    def get_related(self, resources):
        related_ids = self.get_related_ids(resources)
        client = local_session(self.manager.session_factory).client('compute-optimizer')
        op = getattr(client, self.recommendation_op)
        op_kwargs = {
            self.arns_name: related_ids,
            'accountIds': [self.manager.account_id]
        }
        related = {
            r[self.results_arn_key]: r for r in op(**op_kwargs)[self.results_key]}
        model = self.manager.get_model()
        result = {}
        for r in resources:
            resource_arn = self.get_related_ids([r])[0]
            if resource_arn in related:
                result[r[model.id]] = related[resource_arn]
        return result


@EC2.filter_registry.register('compute-optimizer')
class EC2ComputeOptimizerFilter(ComputeOptimizerFilter):

    recommendation_op = 'get_ec2_instance_recommendations'
    arns_name = 'instanceArns'
    results_key = 'instanceRecommendations'
    results_arn_key = 'instanceArn'


@ASG.filter_registry.register('compute-optimizer')
class ASGComputeOptimizerFilter(ComputeOptimizerFilter):

    recommendation_op = 'get_auto_scaling_group_recommendations'
    arns_name = 'autoScalingGroupArns'
    results_key = 'autoScalingGroupRecommendations'
    results_arn_key = 'autoScalingGroupArn'
