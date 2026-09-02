# Licensing decision

This page records why QGIS MCP is licensed the way it is. It is a record, not
legal advice. Ask a lawyer if a real question turns on it.

## The decision

QGIS MCP is licensed under **Apache-2.0**.

## What was checked

| Item | Finding |
| --- | --- |
| This project | Apache-2.0, copyright 2025 James Williams |
| Upstream, BlenderMCP | **MIT**, copyright (c) 2025 Siddharth Ahuja |
| Direct dependency, `mcp` | MIT |
| Runtime host, QGIS | GPL-2.0-or-later |
| PyQGIS, used by the plugin | GPL-2.0-or-later |

## Is Apache-2.0 compatible with the MIT upstream?

Yes, in this direction.

MIT is a permissive licence. It allows a derived work to be distributed under
different terms, including Apache-2.0. The reverse is not true: Apache-2.0 code
cannot be relicensed as MIT.

MIT attaches one condition that survives the change:

> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.

That condition was **not** being met. The repository carried an Apache-2.0
`LICENSE` naming one copyright holder, and no copy of the MIT notice anywhere.
The `README.md` credited BlenderMCP, but a credit is not the notice the licence
asks for.

### What was done about it

A `NOTICE` file now carries the MIT copyright notice and the full permission
notice. Apache-2.0 section 4(d) makes a `NOTICE` file the conventional place for
attribution, and it requires anyone who redistributes the work to carry that
file forward.

`NOTICE` ships inside the wheel and the sdist, through `license-files` in
`pyproject.toml`.

## What about the GPL in QGIS?

QGIS and PyQGIS are GPL-2.0-or-later. That does not make this project GPL.

- The **MCP server** never imports PyQGIS. It is a separate process that speaks
  a socket protocol. It does not link against QGIS in any sense.
- The **QGIS plugin** does import PyQGIS, and it runs inside the QGIS process.

Whether a QGIS Python plugin forms a derivative work of QGIS is a question the
QGIS project answers for its own plugin repository: it requires a plugin to
carry a GPL-compatible licence.

Apache-2.0 is compatible with GPL-3.0, and is **not** compatible with GPL-2.0
alone. QGIS is licensed GPL-2.0-**or-later**, so a distributor may take the
GPL-3.0 option, under which Apache-2.0 combines cleanly. That is the reading
this project relies on.

## Why Apache-2.0 rather than MIT

Three reasons.

- **An explicit patent grant.** Apache-2.0 section 3 grants patent rights from
  every contributor, and terminates that grant for anyone who starts patent
  litigation over the work. MIT is silent on patents.
- **An explicit trademark position.** Section 6 says the licence grants no
  trademark rights.
- **A stated attribution mechanism.** The `NOTICE` file has defined behaviour,
  which is what this project needed for the MIT upstream.

The cost is a longer licence text and a small compliance duty on anyone who
redistributes. That is an acceptable trade for a project that other people are
expected to build on.

## Why there is no `License ::` classifier

`pyproject.toml` declares the licence as an SPDX expression:

```toml
license = "Apache-2.0"
license-files = ["LICENSE", "NOTICE"]
```

[PEP 639](https://peps.python.org/pep-0639/) made that the standard form, and
deprecated the old `License :: OSI Approved :: ...` classifiers alongside it.
Carrying both is redundant, and package indexes have begun to reject the
combination.

The build tool still accepts both. The classifier is left out on purpose.

## The QGIS plugin

`qgis_mcp_plugin/metadata.txt` states the licence in its `about` text. The QGIS
plugin metadata format defines no dedicated licence field, so `about` is where a
reader of the plugin manager sees it.

The plugin ships inside the repository and inside the release zip, so the
top-level `LICENSE` and `NOTICE` cover it.

## If you add code from elsewhere

- Do not paste code whose origin you cannot name.
- MIT, BSD, and ISC code may be brought in. Add its copyright notice to
  `NOTICE`.
- GPL or LGPL code may **not** be brought into this repository. It would force
  the whole work to change licence.
- Record any addition on this page.
