"""Backward-compatible test entry point aggregating split test modules."""

from dgenies.pytest.api_core import *  # noqa: F401,F403
from dgenies.pytest.api_extended import *  # noqa: F401,F403
from dgenies.pytest.api_runtime import *  # noqa: F401,F403
from dgenies.pytest.bin_tools_suite import *  # noqa: F401,F403
from dgenies.pytest.bootstrap_suite import *  # noqa: F401,F403
from dgenies.pytest.config_suite import *  # noqa: F401,F403
from dgenies.pytest.core_models import *  # noqa: F401,F403
from dgenies.pytest.database_suite import *  # noqa: F401,F403
from dgenies.pytest.functions_core import *  # noqa: F401,F403
from dgenies.pytest.integrations_suite import *  # noqa: F401,F403
from dgenies.pytest.job_helpers_suite import *  # noqa: F401,F403
from dgenies.pytest.job_manager_suite import *  # noqa: F401,F403
from dgenies.pytest.maintenance_suite import *  # noqa: F401,F403
from dgenies.pytest.paf_suite import *  # noqa: F401,F403
from dgenies.pytest.upload_validation import *  # noqa: F401,F403
from dgenies.pytest.views_suite import *  # noqa: F401,F403
