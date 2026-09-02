# Change fragments

Each file here describes one change, for the person who installs the release.
`towncrier build` assembles them into the release notes during a release.

Read [Changelog fragments](../docs/dev/changelog_fragments.md) for the full rules.

## The short version

Name the file `<issue>.<type>`, where `<issue>` is the issue the change closes,
or the pull request number when no issue exists.

```
changes/14.added
```

Use one of these types:

`security`, `added`, `changed`, `deprecated`, `removed`, `fixed`,
`dependencies`, `documentation`.

Write for the operator, not the reviewer. Use at most three items. Put one item
on one line.
