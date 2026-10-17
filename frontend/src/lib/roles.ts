import type { Role } from "../api/client";
import type { Route } from "./route";

type View = Route["view"];

export interface RoleInfo {
  label: string;
  who: string;
  question: string;
  /** Where the role lands (VIEW-08, UX-01): the clinician's ward, Tyks, or Varha. */
  home: Route;
  homeLabel: string;
  nav: { view: View; label: string }[];
  /** Patient-level data (line lists, carriers, patient paths) is for these roles only (NF-03). */
  patientLevel: boolean;
  /** Notification settings (UX-06): delivery is configured here, not a main view. */
  settings: boolean;
}

/** The three roles (PROJECT.md §3) and what each sees first (VIEW-08, UX-01). */
export const ROLES: Record<Role, RoleInfo> = {
  clinician: {
    label: "Clinician",
    who: "Ward or on-call doctor, health-centre GP",
    question: "Is there a reason not to use the antibiotic I have in mind, here, now?",
    home: { view: "ward" },
    homeLabel: "My ward: what to avoid, what's going on",
    nav: [
      { view: "ward", label: "My Ward" },
      { view: "alerts", label: "Alerts" },
    ],
    patientLevel: false,
    settings: false,
  },
  infection_control: {
    label: "Infection control",
    who: "Infection-control nurse, hygienist, infection physician",
    question: "Is something spreading? Which wards, which patients?",
    home: { view: "area", id: "tyks" },
    homeLabel: "Tyks: only the wards with something going on",
    nav: [
      { view: "area", label: "Overview" },
      { view: "alerts", label: "Alerts" },
      { view: "spread", label: "Spread" },
      { view: "patients", label: "Carriers" },
    ],
    patientLevel: true,
    settings: true,
  },
  lab: {
    label: "Lab & stewardship",
    who: "Clinical microbiologist; stewardship and annual reporting",
    question: "Are alerts real? Is data arriving? What are the long-term trends?",
    home: { view: "area" },
    homeLabel: "Varha: anomalies across the county",
    nav: [
      { view: "area", label: "Overview" },
      { view: "alerts", label: "Alerts" },
      { view: "trends", label: "Stewardship" },
      { view: "heatmap", label: "Heatmap" },
      { view: "feed", label: "Feed" },
      { view: "spread", label: "Spread" },
      { view: "patients", label: "Carriers" },
    ],
    patientLevel: true,
    settings: true,
  },
};

export interface RoleSetting {
  role: Role;
  /** The clinician's own ward: My Ward opens on it and the alert list filters to it. */
  ward?: string;
}
