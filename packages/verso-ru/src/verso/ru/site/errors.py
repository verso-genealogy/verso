"""What stops a site from being built: one family of refusals, which `verso site` answers with exit 2."""
from __future__ import annotations


class SiteError(ValueError):
    """A site that cannot be built of what it was given; its text says of what and why."""
