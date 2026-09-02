# Release checklist

A release ships two things that must agree: the `qgis-mcp` package on PyPI, and
the QGIS plugin. The two check each other's protocol version at run time, so a
user who updates one and not the other gets a clear error. Release them together.

## One time setup

Do these once, before the first release. A release fails without them.

- [ ] Register the `qgis-mcp` name on [PyPI](https://pypi.org/).
- [ ] Add a **Trusted Publisher** on PyPI for this repository. Set the workflow
      to `release.yml` and the environment to `pypi`. No API token is stored.
- [ ] Create a GitHub environment named `pypi`. The `publish-pypi` job names it,
      and the job holds the `id-token: write` permission that Trusted Publishing
      needs.
- [ ] Create a GitHub environment named `osgeo`. Leave it empty to skip the QGIS
      Plugin Repository upload.
- [ ] Seed `main` from `develop`, once. `main` starts as an orphan branch with
      no shared history, so the `advance-main` job cannot move it until someone
      does this by hand.

To publish to the QGIS Plugin Repository as well:

- [ ] Create an [OSGeo account](https://www.osgeo.org/community/getting-started-osgeo/osgeo_userid/).
- [ ] Add `OSGEO_USERNAME` and `OSGEO_PASSWORD` to the `osgeo` environment.

The upload step is skipped when `OSGEO_USERNAME` is empty, so the release still
succeeds without an account.

## Before you release

- [ ] Every pull request in the release carries a fragment under `changes/`, or
      the `no-changelog` label.
- [ ] CI is green on `develop`.
- [ ] Read the draft notes:

      ```bash
      poetry run towncrier build --version <new version> --draft
      ```

## Prepare the release

1. Run the **Prepare Release** workflow from the Actions tab. Choose the bump
   rule: `prerelease`, `patch`, `minor`, or `major`.

   The workflow:

   - bumps the version with `poetry version`;
   - writes the same version into `qgis_mcp_plugin/metadata.txt` and
     `PLUGIN_VERSION`, because a test asserts the three agree;
   - builds the release notes from `changes/` with towncrier;
   - starts a new `docs/admin/release_notes/version_X.Y.md` for a new minor
     series, and points towncrier at it;
   - regenerates `poetry.lock`;
   - opens a release pull request into `develop`;
   - creates a draft GitHub release for tag `v<version>`.

2. Review the release pull request. Read the built notes as a user would.
3. Merge it. CI must be green.

## Publish

4. Open the draft release, check the tag is `v<version>`, and publish it.

   The **Release** workflow then:

   - builds the wheel, the sdist, and the QGIS plugin zip;
   - checks the tag matches `poetry version -s`, and that the plugin agrees;
   - attaches all three files to the GitHub release;
   - publishes the wheel and the sdist to PyPI;
   - uploads the plugin to plugins.qgis.org, when the OSGeo secrets exist;
   - moves `main` to the released commit.

## After you release

- [ ] `pip install qgis-mcp==<version>` works from a clean environment.
- [ ] The GitHub release holds the wheel, the sdist, and the plugin zip.
- [ ] `main` points at the released commit.
- [ ] Install the plugin zip in QGIS with **Install from ZIP**, start the
      server, and call `get_qgis_info`. Confirm `plugin_version` and
      `server_version` both read the new version.

## If the release fails

The jobs are independent after `build`. A failure in one does not undo another.

| Failure | What to do |
| --- | --- |
| The tag does not match the version | Delete the tag and the release. Fix `pyproject.toml`. Prepare again. |
| PyPI rejects the upload | A version cannot be replaced on PyPI. Bump to the next patch and release again. |
| The QGIS upload fails | Upload the plugin zip by hand at plugins.qgis.org. The rest of the release stands. |
| `advance-main` fails | `main` shares no history with the release. Seed it once by hand, then move it. |
