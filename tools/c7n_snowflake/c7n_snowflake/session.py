import os
from snowflake.connector import connect
from snowflake.core import Root
from snowflake.connector.errors import DatabaseError
from c7n.exceptions import CustodianError


class SessionFactory:

    required_env_vars = (
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_API_KEY",
    )

    def __init__(self):
        self.ensure_required_env_vars()
        pass

    def ensure_required_env_vars(self):
        missing = []
        for ev in self.required_env_vars:
            if ev not in os.environ:
                missing.append(ev)
        if missing:
            raise Exception("Missing the following env vars:%s" % missing)

    def config(self):
        return self._config

    def __call__(self):
        try:
            connection = connect(
                **{
                    "account": os.environ["SNOWFLAKE_ACCOUNT"],
                    "user": os.environ["SNOWFLAKE_USER"],
                    "password": os.environ["SNOWFLAKE_API_KEY"],
                }
            )
        except DatabaseError:
            raise CustodianError("Unable to connect to Snowflake, check your Network Policies")

        return Root(connection)
