import type { Role } from "../api/client";
import type { Route } from "./route";

type View = Route["view"];

export interface RoleInfo {
  label: string;
  who: string;
  question: string;
  home: View;
  nav: { view: View; label: string }[];
  /** Patient-level data (line lists, carriers, patient paths) is for these roles only (NF-03). */
  patientLevel: boolean;
}

/** The three roles (PROJECT.md §3) and what each sees first (VIEW-08). */
export const ROLES: Record<Role, RoleInfo> = {
  clinician: {
    label: "Clinician",
    who: "Ward or on-call doctor, health-centre GP",
    question: "Which antibiotic is likely to work on my ward right now?",
    home: "ward",
    nav: [
      { view: "ward", label: "My Ward" },
      { view: "alerts", label: "Alerts" },
    ],
    patientLevel: false,
  },
  infection_control: {
    label: "Infection control",
    who: "Infection-control nurse, hygienist, infection physician",
    question: "Is something spreading? Which wards, which patients?",
    home: "alerts",
    nav: [
      { view: "alerts", label: "Alerts" },
      { view: "overview", label: "Overview" },
      { view: "spread", label: "Spread" },
      { view: "patients", label: "Carriers" },
      { view: "ward", label: "Wards" },
      { view: "notifications", label: "Notifications" },
    ],
    patientLevel: true,
  },
  lab: {
    label: "Lab & stewardship",
    who: "Clinical microbiologist; stewardship and annual reporting",
    question: "Are alerts real? Is data arriving? What are the long-term trends?",
    home: "feed",
    nav: [
      { view: "feed", label: "Feed status" },
      { view: "alerts", label: "Alerts" },
      { view: "trends", label: "Trends" },
      { view: "overview", label: "Overview" },
      { view: "spread", label: "Spread" },
      { view: "patients", label: "Carriers" },
      { view: "ward", label: "Wards" },
      { view: "notifications", label: "Notifications" },
    ],
    patientLevel: true,
  },
};

export interface RoleSetting {
  role: Role;
  /** The clinician's own ward: their alerts badge and default alert filter (NOTIF-03). */
  ward?: string;
}
