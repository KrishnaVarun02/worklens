"""Read-only connectors; adapters are fixture-tested, not live-certified."""

from .transport import AccessRevoked, ConnectorError, RecordUnavailable
from .jira import JiraCloudAdapter, JiraDataCenterAdapter
from .bitbucket import BitbucketCloudAdapter, BitbucketDataCenterAdapter
from .confluence import ConfluenceCloudAdapter, ConfluenceDataCenterAdapter
from .fixture import FixtureAdapter

ADAPTERS = {
    ("jira", "cloud"): JiraCloudAdapter,
    ("jira", "data_center"): JiraDataCenterAdapter,
    ("bitbucket", "cloud"): BitbucketCloudAdapter,
    ("bitbucket", "data_center"): BitbucketDataCenterAdapter,
    ("confluence", "cloud"): ConfluenceCloudAdapter,
    ("confluence", "data_center"): ConfluenceDataCenterAdapter,
    ("fixture", "fixture"): FixtureAdapter,
}


def get_adapter(config, secret=None, transport=None):
    key = (
        config.get("kind"),
        config.get("deployment", "fixture" if config.get("kind") == "fixture" else "cloud"),
    )
    if key not in ADAPTERS:
        raise ConnectorError("This source/deployment combination is not implemented.")
    return ADAPTERS[key](config, secret or config.get("credentials"), transport)


__all__ = ["get_adapter", "ADAPTERS", "AccessRevoked", "ConnectorError", "RecordUnavailable"]
