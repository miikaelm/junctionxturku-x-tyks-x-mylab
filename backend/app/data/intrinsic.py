"""Intrinsic resistance (DATA-07): EUCAST Expected Resistant Phenotypes v1.2.

Only the pairs relevant to the 13 agents in this dataset are listed. These pairs are shown as
"intrinsically resistant" and are never treated as findings or alerts.
"""

INTRINSIC_RESISTANCE: dict[str, frozenset[str]] = {
    "Citrobacter freundii": frozenset({"AMP", "FOX"}),
    "Klebsiella pneumoniae": frozenset({"AMP"}),
    "Klebsiella oxytoca": frozenset({"AMP"}),
    "Proteus mirabilis": frozenset({"NIT"}),
    "Pseudomonas aeruginosa": frozenset({"AMP", "FOX", "CXM", "CRO", "TMP", "NIT"}),
    "Enterococcus faecalis": frozenset({"FOX", "CXM", "CRO", "CAZ", "CLI"}),
}


def is_intrinsic(organism: str, antibiotic_code: str) -> bool:
    return antibiotic_code in INTRINSIC_RESISTANCE.get(organism, frozenset())
