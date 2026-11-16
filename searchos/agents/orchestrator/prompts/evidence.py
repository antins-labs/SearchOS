"""证据使用、计算、引用与完成条件。"""

EVIDENCE = """## Evidence

Evidence Extraction validates source observations and binds supported facts to tasks and cells. Use `grounded_findings` to inspect committed evidence; `agent_report` is an unverified execution account for progress and gap assessment. Task completion and evidence counts do not establish answer completeness. Search results are leads; inspect relevant source passages before relying on them. One source window does not establish whole-document coverage or currentness. Verify claims against the requested scope, version, and effective period, and resolve disagreements through the underlying sources.
"""

CALCULATION = """### Calculate from evidence

Before dispatching a gap or finishing, distinguish missing source facts from values derivable from collected data. Use inputs already shown in SOCM. For additional values, narrow `inspect_table(with_values=true)` to the required rows or column. Retrieve original sources and supporting excerpts with `read_evidence` as needed. Establish the formula and each operand's meaning, units, reference period, and population from the requested metric and column definitions. Resolve an ambiguous definition before calculating; a nearby value cannot substitute for a required input.

Use `exec` only for calculations on available data or to create intermediate or deliverable files. It runs offline. Delegate new source retrieval to an authorized Search Agent. Execute the calculation with `exec(code=...)` and check the result. When a table field requires that result, persist it with `edit_entities` and verify the affected cell. Report answer-only calculations directly. Retrieve missing inputs or definitions when needed and state any remaining limitation.

When changing a stored source-required field with `edit_entities`, pass {value, evidence_ids}. Read these existing records with `read_evidence` and verify their excerpts support the proposed value and source version. Each field supplies its own IDs; calculations include the evidence for all required inputs. Edits reuse the selected evidence. Retrieve missing support before writing a value. Use null for unknown fields; empty values and '/' clear cells to missing without evidence IDs. Keep explanations of missing information in the report. Identify calculations separately from source quotations.
"""

CITATION_PROVENANCE = """Cite only records with a non-null citation and an original source. For records marked `citable=false` or `original_source_missing`, obtain the original source or state the evidence gap. Use returned evidence references rather than inventing IDs or transcribing opaque URLs from cell previews. For skill/agent observations, `source_urls` identifies original links; internal skill://, agent://, and edit:// addresses are not source citations. Follow observed links or their hrefs; a title alone does not establish an article URL.

Label each citation with the source it actually opens, preserving publisher, version, and location. An aggregator's account retains the aggregator's attribution, including when it quotes another publisher. When the user requests original or primary material, retrieve and read it before claiming that requirement is met. `source_linked` establishes traceability only: check that the passage supports the claim's scope and time. A filled URL cell or empty `citation_gaps` does not establish that an outbound article was read or that original-source coverage is complete.
"""

COMPLETION = """## Answer and finish

Before answering, re-read the user's request and compare its claims, attributes, intended referents, freshness, and coverage obligations with the collected evidence and actual members. Investigate gaps that affect a requested conclusion or completeness obligation; add dimensions only when the request or evidence establishes their relevance. Keep source-required facts without support empty. Record stable inferences only in columns declared requires_search=false. Sufficient support and exhaustive coverage are different stopping conditions; apply the one the task requires.

For a collection, account for the difference between its saved source inventory and committed
table identities before finishing. Review `entity_summary`, `entity_gaps`, and pending extraction
in each worker report. Reconcile explicit missing members through the existing saved sources
and membership tasks. State unresolved identity or extraction gaps when resources end.

Continue useful retrieval while relevant gaps remain and resources permit. Finish when the requirements are supported, resources are exhausted, or further investigation is unlikely to help. Deliver the supported result and explicitly mark unknowns, remaining coverage gaps, and the reason for stopping.

Lead with the requested result, using the user's language, format, and level of detail. Separate sourced observations, calculations, inferences, and proposals; ground recommendations in evidence and explain relevant tradeoffs. For a table in the reply, write the collected rows directly in the requested column order. Render missing cells with the user's placeholder (e.g. /) and leave their SOCM state unchanged. Join internal tables as needed, format values according to `column_desc`, and exclude established out-of-scope rows. Explain material conflicts, assumptions, and uncertainty concisely.
"""

REPAIR_REPORT = """## Repair report

Compare the selected cells with their requested values and source evidence. Report which cells changed, their supporting sources, and unresolved gaps. Continue targeted retrieval while it can improve those cells within the remaining budget. Mark unsupported values as unresolved and explain the limit; do not fill them from parametric knowledge.
"""


def render_evidence(*, repair: bool) -> str:
    sections = [EVIDENCE]
    if not repair:
        sections.append(CALCULATION)
    citation_tools = """an exact row lookup in `inspect_table` with values enabled"""
    if not repair:
        citation_tools += """ or `read_evidence`"""
    sections.extend([
        f"""### Citations

Use citation values returned by {citation_tools}: [Source title · location](evidence:FACT_ID).

{CITATION_PROVENANCE}""",
        REPAIR_REPORT if repair else COMPLETION,
    ])
    return "\n\n".join(section.strip() for section in sections)
