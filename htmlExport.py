"""Generate a responsive, self-contained HTML report for Metagoofil results."""

import io
import os

try:
    from html import escape as _html_escape
except ImportError:  # Python 2 compatibility for this legacy application.
    from cgi import escape as _html_escape

try:
    _text_type = unicode
except NameError:
    _text_type = str


def _text(value):
    """Convert values to text safely on both Python 2 and Python 3."""
    if isinstance(value, bytes) and not isinstance(value, _text_type):
        return value.decode("utf-8", "replace")
    try:
        return _text_type(value)
    except UnicodeDecodeError:
        return value.decode("utf-8", "replace")


def _escape(value):
    return _html_escape(_text(value), quote=True)


def _items(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


class htmlExport(object):
    def __init__(self, users, softs, paths, allinfo, fname, dirs, failed,
                 domain, emails):
        self.users = _items(users)
        self.softs = _items(softs)
        self.paths = _items(paths)
        self.allinfo = allinfo or []
        self.fname = fname
        self.dir = dirs
        self.failed = _items(failed)
        self.domain = domain or "Unknown domain"
        self.emails = _items(emails)

    def styler(self):
        """Return the report stylesheet (kept for compatibility with callers)."""
        return """
        <style>
          :root { color-scheme: light; --ink: #17212b; --muted: #64748b;
            --accent: #8b2635; --surface: #fff; --canvas: #f3f6f8;
            --border: #dce3e9; }
          * { box-sizing: border-box; }
          body { margin: 0; background: var(--canvas); color: var(--ink);
            font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif; }
          main { width: min(1120px, calc(100% - 32px)); margin: 36px auto; }
          header { margin-bottom: 24px; }
          h1, h2, h3 { line-height: 1.25; }
          h1 { margin: 0; color: var(--accent); font-size: clamp(2rem, 5vw, 3rem); }
          h2 { margin: 30px 0 14px; font-size: 1.5rem; }
          h3 { margin: 0 0 12px; font-size: 1.1rem; }
          .domain { color: var(--muted); overflow-wrap: anywhere; }
          .summary { display: grid; grid-template-columns: repeat(auto-fit,
            minmax(150px, 1fr)); gap: 14px; margin: 22px 0; }
          .card, .file-card { background: var(--surface); border: 1px solid
            var(--border); border-radius: 12px; padding: 18px;
            box-shadow: 0 4px 14px rgba(23, 33, 43, .05); }
          .card span { display: block; color: var(--muted); font-size: .85rem;
            text-transform: uppercase; letter-spacing: .06em; }
          .card strong { display: block; margin-top: 5px; font-size: 1.8rem; }
          section { margin: 20px 0; }
          ul { margin: 0; padding-left: 22px; }
          li { margin: 5px 0; overflow-wrap: anywhere; }
          .file-card { margin: 14px 0; }
          pre { max-height: 360px; overflow: auto; margin: 12px 0 0;
            padding: 14px; border: 1px solid var(--border); border-radius: 8px;
            background: #f7f9fb; white-space: pre-wrap; overflow-wrap: anywhere;
            font: .88rem/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
          a { color: #155eef; }
          .empty { color: var(--muted); }
          @media (max-width: 600px) { main { width: calc(100% - 20px);
            margin: 20px auto; } .card, .file-card { padding: 14px; } }
        </style>
        """

    def _render_list(self, title, values):
        if not values:
            body = '<p class="empty">0 results</p>'
        else:
            body = "<ul>{}</ul>".format("".join(
                "<li>{}</li>".format(_escape(value)) for value in values
            ))
        return "<section><h2>{}</h2>{}</section>".format(_escape(title), body)

    def _render_file(self, record):
        record = list(record) if isinstance(record, (list, tuple)) else [record]
        record += [None] * (6 - len(record))
        filename, users, paths, software, raw, emails = record[:6]
        filename = filename or "Unknown file"

        local_copy = ""
        if self.dir:
            href = _escape(os.path.join(_text(self.dir), _text(filename)))
            local_copy = '<p><a href="{}">Open local copy</a></p>'.format(href)

        metadata = (
            ("Users", users),
            ("Paths and servers", paths),
            ("Software", software),
            ("Raw metadata", raw),
            ("Emails", emails),
        )
        blocks = []
        for label, value in metadata:
            if value not in (None, "", [], ()):
                blocks.append("<h3>{}</h3><pre>{}</pre>".format(
                    _escape(label), _escape(value)
                ))

        return (
            '<article class="file-card"><h3>{}</h3>{}{}</article>'.format(
                _escape(filename), local_copy, "".join(blocks)
            )
        )

    def writehtml(self):
        counts = (
            ("Usernames", len(self.users)),
            ("Software", len(self.softs)),
            ("Emails", len(self.emails)),
            ("Paths / servers", len(self.paths)),
        )
        summary = '<div class="summary">{}</div>'.format("".join(
            '<div class="card"><span>{}</span><strong>{}</strong></div>'.format(
                _escape(label), count
            ) for label, count in counts
        ))

        analyzed = [record[0] for record in self.allinfo
                    if isinstance(record, (list, tuple)) and record]
        sections = [summary]
        sections.extend((
            self._render_list("User names found", self.users),
            self._render_list("Software versions found", self.softs),
            self._render_list("E-mails found", self.emails),
            self._render_list("Servers and paths found", self.paths),
            self._render_list("Files analyzed", analyzed),
            "<h2>Files and metadata found</h2>",
        ))
        sections.extend(self._render_file(record) for record in self.allinfo)

        if self.failed:
            sections.append("<section><h2>Failed extractions and reasons</h2>{}</section>".format(
                "".join("<pre>{}</pre>".format(_escape(item))
                        for item in self.failed)
            ))

        document = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Metagoofil results</title>
  {style}
</head>
<body>
  <main>
    <header><h1>Metagoofil results</h1>
      <p class="domain">Results for: {domain}</p>
    </header>
    {content}
  </main>
</body>
</html>
""".format(
            style=self.styler(),
            domain=_escape(self.domain),
            content="\n".join(sections),
        )

        output_dir = os.path.dirname(self.fname)
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir)
        with io.open(self.fname, "w", encoding="utf-8") as report:
            report.write(document)
        return "ok"
