# Contributing

Contributions that improve the clarity, safety, accessibility or portability of these workflows are welcome.

## Preserve the Version 1.2.0 boundaries

Changes must preserve both supported briefing approaches:

- Structured Mode accepts the stable eight-field JSON contract and remains the deterministic rendering path.
- Folder Mode adds inventory, source-grounded drafting, provenance and a researcher approval gate before invoking that renderer.

Do not make Folder Mode silently finalise a briefing, treat a file suffix as proof that content was read, infer academic findings without disclosure, trust editable exclusion labels, or weaken digest-bound approval. Evidence Explorer changes must preserve item-to-source validation, absolute-path and unshareable-filename rejection, distinct open, accepted and resolved issue semantics, relative paths, content escaping, offline operation, keyboard access, print output and backward compatibility for Structured Mode.

## Prepare a change

1. Fork the repository and create a focused branch.
2. Make the smallest coherent change and keep the two-workflow public scope intact.
3. Use British English in prose, interface copy, documentation and examples.
4. Add or update tests before changing a validation or rendering contract.
5. Use sanitised synthetic fixtures only. Include duplicates, version ambiguity, exclusions or uncertainty deliberately when a test requires them; never disguise real research material as a fixture.
6. Run the unit, browser, build, archive and publication checks described in [CUSTOMISING.md](CUSTOMISING.md).
7. Open affected HTML through `file://` and a local server at wide and narrow viewports. Check keyboard operation, no-JavaScript reading, print output and every generated item against its approved source.
8. Submit a pull request that explains the purpose, evidence, privacy effect, compatibility effect and any remaining limitation.

## Protect private research material

Never commit or package:

- confidential research notes or unpublished findings;
- participant or supervisor information;
- source inventories, source maps, drafts, unresolved-item reports or excluded-file reports from a real project;
- approval JSON, final briefings or exported meeting state from a real meeting;
- personal details, email addresses, student numbers or private local paths;
- credentials, API keys, tokens or private repository details; or
- browser artefacts, caches and private quality-assurance records.

Keep Folder Mode review and final directories outside the source folder and outside the public repository. An example review set may be committed only when every source and output is purpose-built, sanitised, documented and covered by the publication validator.

Do not add official UWA or OpenAI logos, branding or wording that suggests endorsement or affiliation. Do not modify the bytes of `TeX_Live_Codex_Guide.pdf` merely to update repository metadata.

## Test expectations

A change to Folder Mode should cover the relevant success and failure paths, including atomic failure where applicable. A change to Evidence Explorer should exercise both static validation and a real browser interaction. A change to packaging or privacy validation should include a canary test showing that an unexpected or sensitive file is rejected.

A skipped browser test does not complete release verification. Release tags are created only after automated tests, archive inspection, privacy validation and the live GitHub Pages checks pass.

## Licence agreement

By submitting a contribution, you agree that software and implementation materials are provided under the repository's [MIT licence](LICENSE), while eligible human-readable content is provided under [CC BY 4.0](CONTENT-LICENSE.md). You confirm that you have the right to provide the contribution under those terms.
