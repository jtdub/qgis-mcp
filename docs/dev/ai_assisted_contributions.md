# AI assisted contributions

Much of this project was written with an AI assistant. That is allowed, and it
is expected. This page states what the project asks of you when you use one, and
what a reviewer checks.

None of it lowers the bar. It exists because an assistant fails in ways a person
does not, and the review has to catch those failures.

## Disclose it

Say in the pull request whether an assistant wrote part of the change, and which
part. The template carries a checklist line for this.

"Written with Claude Code" is enough. Naming the files it touched is better.
A reviewer reads a generated diff differently: more slowly, and with different
suspicions.

Do not hide it. Do not apologise for it either.

## You own every line

You are the author. The assistant is a tool you used.

- Read every line before you open the pull request.
- Understand why each line is there.
- Defend it in review on its merits.

"The model wrote it" is not an answer to a review comment. If you cannot explain
a line, delete it or work out what it does before you post.

If you do not understand a change well enough to maintain it, it is not ready.

## Never let a model invent a PyQGIS call

This is the failure that costs this project the most.

An assistant will produce `QgsVectorLayer.someMethodThatSoundsRight()` with total
confidence. The name is plausible, the argument list is plausible, and it does
not exist. `mypy` cannot catch it, because PyQGIS is untyped here. `pylint`
cannot catch it, because `qgis.*` is in its ignore list. The unit suite cannot
catch it, because it replaces `qgis.*` with mocks that answer any attribute.

Only two things catch it:

- The [QGIS API documentation](https://qgis.org/pyqgis/3.34/) for the LTR the
  project declares.
- The integration suite, which runs against a real QGIS.

So:

- Check every PyQGIS call you did not write yourself against that documentation.
- Add an integration test for any handler you add or change. A handler with no
  integration test is a handler nobody has run.

The same applies to the MCP SDK. Check a `FastMCP` behaviour against the
installed package, not against what the assistant remembers.

## Test it as though a stranger wrote it

Generated code needs the same tests as hand-written code. One extra rule:

**A test the model wrote must fail when the code is broken.** Break the code on
purpose, run the test, and confirm it goes red. An assistant writes tests that
pass; that is not the same as a test that tests something.

Watch for these:

- A test that asserts a mock was called, when the real question is what the code
  produced.
- A test whose assertion restates the implementation line above it.
- A test with no assertion at all, that only checks nothing raised.

## Provenance and licence

QGIS MCP is Apache-2.0, and it carries a `NOTICE` file for its MIT upstream.
Read [Licensing](licensing.md).

- Do not paste code you cannot trace. If you do not know where it came from, you
  cannot know its licence.
- An assistant that reproduces a chunk of a well-known project is a real risk.
  If a block looks like it came from somewhere, find out where.
- GPL or LGPL code cannot come into this repository.

## Never paste a secret into a prompt

The plugin generates a token each time you start the server, and writes it to a
session file in your QGIS profile. It is a credential.

- Do not paste a token into a prompt, an issue, or a pull request.
- Do not paste a `session.json`.
- Do not paste customer data, or any file you would not attach to a public
  issue.

An assistant transcript can be logged and retained. Treat it as public.

## `CLAUDE.md` is the working agreement

`CLAUDE.md` at the repository root tells an assistant how this project works:
the commands, the architecture, the two-file rule for a tool, and the design
conventions.

- If you use Claude Code, it is loaded for you. Follow it.
- If you use another assistant, read it and give it the same instructions.
- When a convention changes, change `CLAUDE.md` in the same pull request. A
  stale working agreement teaches the next assistant the wrong thing, and it
  will do so confidently.

`CLAUDE.md` is for the assistant. This page is for you. Where the two overlap,
they must agree.

## What a reviewer does

A reviewer treats an AI assisted pull request the same as any other. Size is not
an excuse for a shallow review. A large generated diff gets more scrutiny, not
less.

A reviewer checks:

- Every PyQGIS call exists, and takes those arguments.
- Each new handler has an integration test.
- Each new test would fail if the code were wrong.
- No invented configuration key, environment variable, or file path.
- The change does what the pull request says, and nothing else. An assistant
  will happily reformat a file it had no reason to touch.
- The docstrings describe the contract, not the implementation.

## Where an assistant helps most

For balance, this is not a warning notice. An assistant is good at:

- The mechanical half of the two-file rule: a handler and its tool, with the
  conventions already in place.
- Test coverage across a matrix of cases.
- Finding an inconsistency across many files.
- Writing documentation from code that already exists.

It is weakest exactly where this project is unusual: the PyQGIS surface, the
two-process protocol, and the fact that the plugin runs under a Python it does
not choose.
