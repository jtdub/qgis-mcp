# Changelog fragments

`docs/admin/release_notes/` is built, not written. A change adds a small file
under `changes/`, and `towncrier build` assembles those files into the release
notes during a release.

This removes the conflict that two branches used to cause when both edited the
same lines of one changelog.

## Name the file

```
changes/<issue>.<type>
```

`<issue>` is the issue the change closes. Use the pull request number when no
issue exists.

| Type | Use it for |
| --- | --- |
| `security` | A change to the token, the socket, or the `execute_code` gate |
| `added` | A tool, a parameter, or a capability that did not exist |
| `changed` | Behaviour a user already depends on |
| `deprecated` | Something that still works, but will go |
| `removed` | Something taken away |
| `fixed` | A symptom a user reported |
| `dependencies` | A dependency a user must install or upgrade |
| `documentation` | A change a reader of the docs notices |

Split one pull request across the types it touches. The three-item limit below
applies to each file on its own.

## Write for the operator

The reader installs the release and runs it. They did not read the diff, they
will not read the source, and they do not know your class names.

Ask one question of each item: **what does this person do differently now?** If
the answer is nothing, the item does not belong in a fragment.

| Write about | Not about |
| --- | --- |
| A tool, a parameter, or a setting they use | A helper, a mixin, or a private method |
| A step they must take to upgrade | The commit that made it necessary |
| Behaviour they will notice | The implementation that produces it |
| A symptom they reported | The cause in the code |

An internal refactor gets no fragment. Say so in the pull request.

## Keep it short

- Use at most **three** items in one file. Choose the three the reader most
  needs before they upgrade.
- Write **one item on one line**. A blank line or a wrapped line splits the item
  in two.
- Use at most 25 words in an item.
- Do not start the line with `-` or `*`. The template adds the marker.

## Use Simplified Technical English

The rest of the documentation uses ASD-STE100. A fragment does too.

- Use the active voice. Write "The tool returns the count", not "The count is
  returned".
- Use simple tenses. Do not use the present perfect.
- Use one word for one meaning. Do not reach for a synonym.
- Do not use the `-ing` form of a verb as a noun.

## An example

`changes/42.added`

```
`buffer_layer` builds a buffer around every feature of a layer, in metres.
The result is a memory layer in WGS84, added to the project.
```

`changes/42.changed`

```
`filter_layer` takes `output_crs`. The output layer used to be WGS84 always.
```

## Check your work

Render the notes without writing them:

```bash
poetry run towncrier build --version 0.3.0 --draft
```

Read the output. If the template already supplies the `-` marker, and you typed
one as well, you will see it twice.
