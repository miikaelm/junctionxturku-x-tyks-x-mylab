"""First-isolate rule (DATA-02, CLSI M39 / THL Finres).

Keep only the earliest isolate per patient × organism × specimen type in the frame passed in.
Callers filter to the analysis stratum and window first, so "first" means first within that
stratum and period (e.g. a patient counts once for GER and once for URO).
"""

import pandas as pd

FIRST_ISOLATE_KEY = ["patient_id", "organism", "specimen"]


def first_isolates(isolates: pd.DataFrame) -> pd.DataFrame:
    # Dataset.isolates is pre-sorted by sample_date, and filtering preserves that order.
    return isolates.drop_duplicates(FIRST_ISOLATE_KEY, keep="first")
