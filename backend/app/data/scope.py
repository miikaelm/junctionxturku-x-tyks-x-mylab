"""Population scope: location + filters (VIEW-02), and the fallback hierarchy (STAT-04).

Location hierarchy: ward → institution (hospital / primary_care) → all.
"""

from dataclasses import dataclass, replace

import pandas as pd

INSTITUTION_LABELS = {"hospital": "All hospital wards", "primary_care": "All health centres"}
ALL_LABEL = "All locations"


@dataclass(frozen=True)
class Scope:
    location: str = "all"  # ward code | "hospital" | "primary_care" | "all"
    specimen: str | None = None
    sex: str | None = None
    age_band: str | None = None
    hospital_acquired: bool | None = None
    ward_type: str | None = None  # "in" | "out"
    home_area: str | None = None

    def level(self, wards: pd.DataFrame) -> str:
        if self.location == "all":
            return "all"
        if self.location in INSTITUTION_LABELS:
            return "institution"
        if self.location in set(wards.ward_code):
            return "ward"
        raise ValueError(f"unknown location: {self.location}")

    def label(self, wards: pd.DataFrame) -> str:
        level = self.level(wards)
        if level == "all":
            return ALL_LABEL
        if level == "institution":
            return INSTITUTION_LABELS[self.location]
        return wards.set_index("ward_code").ward_en[self.location]

    def broader(self, wards: pd.DataFrame) -> "Scope | None":
        level = self.level(wards)
        if level == "ward":
            institution = wards.set_index("ward_code").institution[self.location]
            return replace(self, location=institution)
        if level == "institution":
            return replace(self, location="all")
        return None

    def chain(self, wards: pd.DataFrame) -> list["Scope"]:
        """This scope followed by each broader fallback level."""
        out: list[Scope] = [self]
        while (nxt := out[-1].broader(wards)) is not None:
            out.append(nxt)
        return out

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter a culture- or isolate-level frame (needs the joined culture columns)."""
        mask = pd.Series(True, index=df.index)
        if self.location in INSTITUTION_LABELS:
            mask &= df.institution.eq(self.location)
        elif self.location != "all":
            mask &= df.ward_code.eq(self.location)
        if self.specimen:
            mask &= df.specimen.eq(self.specimen)
        if self.sex:
            mask &= df.sex.eq(self.sex)
        if self.age_band:
            mask &= df.age_band.eq(self.age_band)
        if self.hospital_acquired is not None:
            mask &= df.hospital_acquired.eq(self.hospital_acquired)
        if self.ward_type:
            mask &= df.ward_type.eq(self.ward_type)
        if self.home_area:
            mask &= df.home_area.eq(self.home_area)
        return df[mask]

    def ward_codes(self, wards: pd.DataFrame) -> set[str]:
        """The wards this location covers."""
        level = self.level(wards)
        if level == "all":
            return set(wards.ward_code)
        if level == "institution":
            return set(wards.ward_code[wards.institution.eq(self.location)])
        return {self.location}

    def to_dict(self, wards: pd.DataFrame) -> dict:
        return {
            "location": self.location,
            "level": self.level(wards),
            "label": self.label(wards),
            "specimen": self.specimen,
            "sex": self.sex,
            "age_band": self.age_band,
            "hospital_acquired": self.hospital_acquired,
            "ward_type": self.ward_type,
            "home_area": self.home_area,
        }
