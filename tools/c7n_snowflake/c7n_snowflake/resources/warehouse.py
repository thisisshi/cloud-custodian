from c7n_snowflake.query import QueryResourceManager
from c7n_snowflake.provider import resources


@resources.register("warehouse")
class Warehouse(QueryResourceManager):
    client = "warehouses"
