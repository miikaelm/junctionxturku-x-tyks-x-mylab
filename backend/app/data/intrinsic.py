"""Intrinsic resistance (DATA-07): EUCAST Expected Resistant Phenotypes v1.2.

Only the pairs relevant to the 13 agents in this dataset are listed. These pairs are shown as
"intrinsically resistant" and are never treated as findings or alerts. Gram-negatives are also
intrinsically resistant to glycopeptides and lincosamides (VAN, CLI); those pairs are never
tested in the data, but the therapy helper (V2) needs to know they don't cover.
"""

INTRINSIC_RESISTANCE: dict[str, frozenset[str]] = {
    "Escherichia coli": frozenset({"VAN", "CLI"}),
    "Citrobacter freundii": frozenset({"AMP", "FOX", "VAN", "CLI"}),
    "Klebsiella pneumoniae": frozenset({"AMP", "VAN", "CLI"}),
    "Klebsiella oxytoca": frozenset({"AMP", "VAN", "CLI"}),
    "Proteus mirabilis": frozenset({"NIT", "VAN", "CLI"}),
    "Pseudomonas aeruginosa": frozenset({"AMP", "FOX", "CXM", "CRO", "TMP", "NIT", "VAN", "CLI"}),
    "Enterococcus faecalis": frozenset({"FOX", "CXM", "CRO", "CAZ", "CLI"}),
}


def is_intrinsic(organism: str, antibiotic_code: str) -> bool:
    return antibiotic_code in INTRINSIC_RESISTANCE.get(organism, frozenset())
