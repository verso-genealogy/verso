from verso.core.targets.geni.date import GeniDate


class GeniEvent:
    def __init__(self,
                 date: GeniDate | None = None,
                 location: str | None = None):
        self.date = date
        self.location = location

    def to_terraform(self, indent: str = "") -> str:
        """Render `{ date = {...}; location = {...} }` block. `indent` is
        the column offset of the line that contains the opening `{`. Inner
        keys (date, location) get `indent + "  "`; their bodies get
        `indent + "    "`; the closing `}` is at `indent`.
        """
        inner = indent + "  "
        deeper = indent + "    "
        parts = ["{"]
        if self.date:
            parts.append(f"{inner}date = {self.date.to_terraform(indent=inner)}")
        if self.location:
            # The corpus's places store subsequent lines with a fixed prefix
            # (18 or 20 spaces) that no longer aligns with the modern emit
            # path. Strip leading whitespace from each line and re-indent at
            # the correct depth so the block is uniformly aligned.
            loc_lines = [ln.strip() for ln in self.location.split("\n")]
            indented = "\n".join(deeper + ln if ln else "" for ln in loc_lines)
            parts.append(f"{inner}location = {{")
            parts.append(indented)
            parts.append(f"{inner}}}")
        parts.append(f"{indent}}}")
        return "\n".join(parts)

    def __eq__(self, other):
        if not isinstance(other, GeniEvent):
            return NotImplemented
        return (self.date, self.location) == (other.date, other.location)

    def __str__(self):
        return f"GeniEvent(date={self.date}, location={self.location})"
