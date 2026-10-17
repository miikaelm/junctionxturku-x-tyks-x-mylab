"""National reference values (DATA-08): Finland, from THL's annual Finres report.

Reference only: a "Finland level" line next to local figures, never used for alerts or flags.
Values are copied from Finres 2023 (THL working paper 63/2024), the newest report checked. Finres
counts the first isolate of each species per patient per year and specimen type, from all Finnish
clinical microbiology laboratories, and reports a % only when more than half of the isolates were
tested. That is close to our own rule, but not identical (our 12-month windows roll; theirs are
calendar years), so a small gap is not a finding. Our "wound" specimens are compared with Finres
"pus" (märkä) specimens. Urine E. coli is reported for women and men separately; without a sex
filter the two are pooled, weighted by the number tested.
"""

SOURCE = {
    "label": "THL Finres 2023",
    "publisher": "Finnish Institute for Health and Welfare (THL)",
    "title": "Bakteerien mikrobilääkeresistenssi Suomessa – Finres 2023 (Työpaperi 63/2024)",
    "year": 2023,
    "url": "https://urn.fi/URN:ISBN:978-952-408-414-7",
    "portal": "https://www3.thl.fi/finres",
}

# (organism, specimen or None for all specimens, antibiotic code, sex or None) → (tested, % R, table)
# FOX stands for MRSA: the cefoxitin screen is how MRSA is detected (FOX R ⇔ MRSA).
_ROWS: list[tuple[str, str | None, str, str | None, int, float, str]] = [
    # Taulukko 11–12: E. coli, urine, women / men
    *[
        ("Escherichia coli", "urine", code, "F", n, pct, "Taulukko 11")
        for code, n, pct in [
            ("TMP", 70884, 16.0),
            ("NIT", 67578, 0.4),
            ("MEC", 70886, 2.4),
            ("CXM", 70870, 6.3),
            ("CIP", 70869, 6.5),
        ]
    ],
    *[
        ("Escherichia coli", "urine", code, "M", n, pct, "Taulukko 12")
        for code, n, pct in [
            ("TMP", 9879, 16.4),
            ("NIT", 9414, 0.7),
            ("MEC", 9877, 3.0),
            ("CXM", 9879, 10.5),
            ("CIP", 9877, 11.9),
        ]
    ],
    # Taulukko 10: E. coli, blood
    *[
        ("Escherichia coli", "blood", code, None, n, pct, "Taulukko 10")
        for code, n, pct in [
            ("TZP", 4240, 5.6),
            ("MEM", 4265, 0.0),
            ("CXM", 4262, 11.3),
            ("CRO", 4258, 6.3),
            ("CIP", 3432, 10.1),
            ("CAZ", 4257, 5.9),
        ]
    ],
    # Taulukko 19: K. oxytoca, all specimen types
    *[
        ("Klebsiella oxytoca", None, code, None, n, pct, "Taulukko 19")
        for code, n, pct in [("TMP", 3730, 9.2), ("CXM", 4222, 14.0), ("CIP", 4135, 5.2)]
    ],
    # Taulukko 20–21: K. pneumoniae, blood / urine
    *[
        ("Klebsiella pneumoniae", "blood", code, None, n, pct, "Taulukko 20")
        for code, n, pct in [
            ("TZP", 723, 13.3),
            ("MEM", 725, 0.0),
            ("CXM", 726, 12.4),
            ("CRO", 725, 7.3),
            ("CIP", 594, 9.1),
            ("CAZ", 724, 8.3),
        ]
    ],
    *[
        ("Klebsiella pneumoniae", "urine", code, None, n, pct, "Taulukko 21")
        for code, n, pct in [
            ("TMP", 9638, 13.7),
            ("MEC", 8813, 5.6),
            ("CXM", 9637, 7.3),
            ("CIP", 9638, 5.1),
        ]
    ],
    # Taulukko 30–32: P. aeruginosa, blood / urine / pus
    *[
        ("Pseudomonas aeruginosa", spec, code, None, n, pct, table)
        for spec, table, values in [
            ("blood", "Taulukko 30", [(364, 4.4), (365, 3.3), (307, 7.5), (367, 3.0)]),
            ("urine", "Taulukko 31", [(3432, 5.8), (3487, 1.7), (3485, 7.8), (3487, 3.4)]),
            ("wound", "Taulukko 32", [(2567, 3.5), (2761, 1.4), (2777, 5.7), (2761, 2.7)]),
        ]
        for code, (n, pct) in zip(("TZP", "MEM", "CIP", "CAZ"), values)
    ],
    # Taulukko 35–36: S. aureus, blood / pus (MRSA share and clindamycin)
    ("Staphylococcus aureus", "blood", "FOX", None, 2180, 2.8, "Taulukko 35"),
    ("Staphylococcus aureus", "blood", "CLI", None, 2177, 5.6, "Taulukko 35"),
    ("Staphylococcus aureus", "wound", "FOX", None, 22667, 3.3, "Taulukko 36"),
    ("Staphylococcus aureus", "wound", "CLI", None, 22619, 5.6, "Taulukko 36"),
    # Taulukko 7–8: E. faecalis
    ("Enterococcus faecalis", "blood", "AMP", None, 364, 0.0, "Taulukko 7"),
    ("Enterococcus faecalis", "urine", "AMP", None, 9768, 0.1, "Taulukko 7"),
    ("Enterococcus faecalis", "urine", "NIT", None, 10122, 0.3, "Taulukko 7"),
    ("Enterococcus faecalis", "wound", "AMP", None, 911, 0.2, "Taulukko 7"),
    ("Enterococcus faecalis", None, "VAN", None, 11315, 0.0, "Taulukko 8"),
]

SPECIMEN_LABEL = {"urine": "urine", "blood": "blood", "wound": "pus", None: "all specimens"}
SEX_LABEL = {"F": "women", "M": "men", None: "women and men"}


def table() -> list[dict]:
    """Every reference value, as published."""
    return [
        {
            "organism": o,
            "specimen": s,
            "antibiotic_code": c,
            "sex": sex,
            "n": n,
            "pct": pct,
            "table": t,
        }
        for o, s, c, sex, n, pct, t in _ROWS
    ]


def lookup(organism: str, specimen: str | None, code: str, sex: str | None = None) -> dict | None:
    """The Finland figure for this organism × specimen × antibiotic (and sex, when the national
    table splits by it), or None. A specimen-specific value wins over an all-specimens one."""
    rows = [
        r
        for r in _ROWS
        if r[0] == organism and r[2] == code and r[1] in (specimen, None) and specimen is not None
    ]
    if not rows:
        return None
    best = min(r[1] is None for r in rows)
    rows = [r for r in rows if (r[1] is None) == best]
    split = any(r[3] is not None for r in rows)
    if split and sex is not None:
        rows = [r for r in rows if r[3] == sex]
    if not rows:
        return None
    n = sum(r[4] for r in rows)
    pct = round(sum(r[4] * r[5] for r in rows) / n, 1)
    spec = rows[0][1]
    group = SEX_LABEL[sex if split else None] if split else None
    return {
        "pct": pct,
        "n": n,
        "year": SOURCE["year"],
        "source": SOURCE["label"],
        "url": SOURCE["url"],
        "tables": sorted({r[6] for r in rows}),
        "specimen_label": SPECIMEN_LABEL[spec],
        "group": group,
        "pooled": split and sex is None,
        "label": f"Finland {SOURCE['year']}"
        + (f", {group}" if group else "")
        + f" ({SPECIMEN_LABEL[spec]}, {SOURCE['label']})",
    }
