/** Confidence-Ampel: Score/String -> Level + Farbe + Label. */

export type ConfidenceLevel = "gruen" | "gelb" | "rot";

export interface ConfidenceInfo {
  level: ConfidenceLevel;
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

const CONF_GREEN = 0.7;
const CONF_YELLOW = 0.4;

const INFO: Record<ConfidenceLevel, Omit<ConfidenceInfo, "label">> = {
  gruen: {
    level: "gruen",
    color: "#2f9e44",
    bgColor: "rgba(47,158,68,0.09)",
    borderColor: "rgba(47,158,68,0.28)",
  },
  gelb: {
    level: "gelb",
    color: "#e3a008",
    bgColor: "rgba(227,160,8,0.09)",
    borderColor: "rgba(227,160,8,0.28)",
  },
  rot: {
    level: "rot",
    color: "#f0603a",
    bgColor: "rgba(240,96,58,0.09)",
    borderColor: "rgba(240,96,58,0.28)",
  },
};

export function confidenceFromScore(score: number): ConfidenceInfo {
  const level: ConfidenceLevel =
    score >= CONF_GREEN ? "gruen" : score >= CONF_YELLOW ? "gelb" : "rot";
  const labels: Record<ConfidenceLevel, string> = {
    gruen: "Hohe Konfidenz",
    gelb: "Mittlere Konfidenz",
    rot: "Niedrige Konfidenz",
  };
  return { ...INFO[level], label: labels[level] };
}

export function confidenceFromString(s: string): ConfidenceInfo {
  const level = (s === "gruen" || s === "gelb" || s === "rot" ? s : "rot") as ConfidenceLevel;
  const labels: Record<ConfidenceLevel, string> = {
    gruen: "Hohe Konfidenz",
    gelb: "Mittlere Konfidenz",
    rot: "Niedrige Konfidenz",
  };
  return { ...INFO[level], label: labels[level] };
}
