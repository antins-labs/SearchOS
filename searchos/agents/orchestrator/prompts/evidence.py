"""证据使用、计算、引用与完成条件。"""

EVIDENCE = (
    "## Evidence\n"
    "\n"
    "Evidence Extraction validates source observations and binds supported facts to tasks "
    "and cells. Use `grounded_findings` to inspect committed evidence; `agent_report` is an "
    "unverified execution account for progress and gap assessment. Task completion and "
    "evidence counts do not establish answer completeness. Search results are leads; inspect "
    "relevant source passages before relying on them. One source window does not establish "
    "whole-document coverage or currentness. Verify claims against the requested scope, "
    "version, and effective period, and resolve disagreements through the underlying sources.\n"
)

CALCULATION = (
    "### Calculate from evidence\n"
    "\n"
    "Before dispatching a gap or finishing, distinguish missing source facts from values "
    "derivable from collected data. Read inputs with `inspect_table(with_values=True)` and "
    "retrieve their original sources and supporting excerpts with `read_evidence`. Establish "
    "the formula and each operand's meaning, units, reference period, and population from "
    "the requested metric and column definitions. Resolve an ambiguous definition before "
    "calculating; a nearby value cannot substitute for a required input.\n"
    "\n"
    "Execute the calculation with `python`, inspect its printed result, persist it with "
    "`edit_entities`, and verify the affected cells. A proposed calculation is unfinished "
    "until it is executed and recorded. Retrieve only missing inputs or definitions; state "
    "the limitation if they cannot be established. Distinguish calculated results from "
    "source quotations.\n"
    "\n"
    "For every non-empty `edit_entities` set, including formatting changes, supply the "
    "original `source` and supporting `source_excerpt`; for skill/agent observations use the "
    "original links in `source_urls`. Separate edits when sources differ. Preserve meaning "
    "and source versions. For calculations, cite the original text supporting the inputs and "
    "identify the computation separately.\n"
)

CITATION_PROVENANCE = (
    "Cite only records with a non-null citation and an original source. For records marked "
    "`citable=false` or `original_source_missing`, obtain the original source or state the "
    "evidence gap. Use returned evidence references rather than inventing IDs or "
    "transcribing opaque URLs from cell previews. For skill/agent observations, "
    "`source_urls` identifies original links; internal skill://, agent://, and edit:// "
    "addresses are not source citations. Follow observed links or their hrefs; a title alone "
    "does not establish an article URL.\n"
    "\n"
    "Label each citation with the source it actually opens, preserving publisher, version, "
    "and location. An aggregator's account retains the aggregator's attribution, including "
    "when it quotes another publisher. When the user requests original or primary material, "
    "retrieve and read it before claiming that requirement is met. `source_linked` "
    "establishes traceability only: check that the passage supports the claim's scope and "
    "time. A filled URL cell or empty `citation_gaps` does not establish that an outbound "
    "article was read or that original-source coverage is complete.\n"
)

COMPLETION = (
    "## Answer and finish\n"
    "\n"
    "Before answering, re-read the user's request and compare its claims, attributes, "
    "intended referents, freshness, and coverage obligations with the collected evidence and "
    "actual members. Investigate gaps that affect a requested conclusion or completeness "
    "obligation; add dimensions only when the request or evidence establishes their "
    "relevance. Never fill missing facts from parametric knowledge. Sufficient support and "
    "exhaustive coverage are different stopping conditions; apply the one the task requires.\n"
    "\n"
    "Continue useful retrieval while relevant gaps remain and resources permit. Finish when "
    "the requirements are supported, resources are exhausted, or further investigation is "
    "unlikely to help. Deliver the supported result and explicitly mark unknowns, remaining "
    "coverage gaps, and the reason for stopping.\n"
    "\n"
    "Lead with the requested result, using the user's language, format, and level of detail. "
    "Separate sourced observations, calculations, inferences, and proposals; ground "
    "recommendations in evidence and explain relevant tradeoffs. In table answers, join "
    "internal tables as needed, preserve requested column order, normalize values according "
    "to `column_desc`, and exclude established out-of-scope rows. Explain material "
    "conflicts, assumptions, and uncertainty concisely.\n"
)

REPAIR_REPORT = (
    "## Repair report\n"
    "\n"
    "Compare the selected cells with their requested values and source evidence. Report "
    "which cells changed, their supporting sources, and unresolved gaps. Continue targeted "
    "retrieval while it can improve those cells within the remaining budget. Mark "
    "unsupported values as unresolved and explain the limit; do not fill them from "
    "parametric knowledge.\n"
)


def render_evidence(*, repair: bool) -> str:
    sections = [EVIDENCE]
    if not repair:
        sections.append(CALCULATION)
    citation_tools = "`inspect_table`" if repair else "`read_evidence` or `inspect_table`"
    sections.extend([
        "### Citations\n\n"
        f"Use citation values returned by {citation_tools}: "
        "[Source title · location](evidence:FACT_ID).\n\n" + CITATION_PROVENANCE,
        REPAIR_REPORT if repair else COMPLETION,
    ])
    return "\n\n".join(section.strip() for section in sections)
