import { useTranslation } from "react-i18next";
import { calculateAP } from "./fmea";

interface VerbPattern {
  verb: string;
  patterns: string[];
}

interface FailureChain {
  key: string;
  effects: string[];
  causes: string[];
}

interface MeasureBase {
  prevention: string[];
  detection: string[];
}

interface ModeSpecificMeasures {
  acquisition: MeasureBase;
  sealing: MeasureBase;
  connection: MeasureBase;
}

/**
 * Hook that provides DFMEA rule-based suggestion helpers.
 * All Chinese content is loaded from the `dfmea` namespace so callers
 * stay free of hard-coded CJK strings.
 */
export function useDfmeaRules() {
  const { t } = useTranslation("dfmea");

  const verbPatterns = t("rules.verbPatterns", { returnObjects: true }) as VerbPattern[];
  const failureChains = t("rules.failureChains", { returnObjects: true }) as FailureChain[];
  const defaultEffects = t("rules.defaultEffects", { returnObjects: true }) as string[];
  const defaultCauses = t("rules.defaultCauses", { returnObjects: true }) as string[];
  const measureBases = t("rules.measureBases", { returnObjects: true }) as Record<string, MeasureBase>;
  const modeSpecific = t("rules.modeSpecific", { returnObjects: true }) as ModeSpecificMeasures;
  const fallbackPatterns = t("rules.fallbackPatterns", { returnObjects: true }) as string[];
  const modeRegex = t("rules.modeRegex", { returnObjects: true }) as Record<string, string>;

  /**
   * Generates failure-mode suggestions from a function description.
   * Matches known verb patterns; falls back to generic negations.
   */
  const generateFailureModes = (functionDesc: string): string[] => {
    for (const { verb, patterns } of verbPatterns) {
      if (functionDesc.includes(verb)) {
        return patterns;
      }
    }
    return fallbackPatterns.map((pattern) =>
      pattern.replace(/{{\s*functionDesc\s*}}/g, functionDesc)
    );
  };

  /**
   * Returns suggested failure effects and causes for a given failure mode.
   */
  const suggestFailureChain = (failureMode: string): { effects: string[]; causes: string[] } => {
    for (const { key, effects, causes } of failureChains) {
      if (failureMode.includes(key)) {
        return { effects, causes };
      }
    }
    return { effects: defaultEffects, causes: defaultCauses };
  };

  /**
   * Returns a localized hint about what to optimize based on AP level.
   */
  const getOptimizationHint = (ap: "H" | "M" | "L"): string => {
    return t(`rules.optimizationHint.${ap}`, { defaultValue: "" });
  };

  /**
   * Returns prevention and detection measure suggestions based on failure mode
   * and Action Priority.
   */
  const suggestMeasures = (
    failureMode: string,
    ap: "H" | "M" | "L"
  ): { prevention: string[]; detection: string[] } => {
    const base = measureBases[ap] || { prevention: [], detection: [] };
    const prevention = [...base.prevention];
    const detection = [...base.detection];

    if (modeRegex.acquisition && new RegExp(modeRegex.acquisition).test(failureMode)) {
      prevention.push(...modeSpecific.acquisition.prevention);
      detection.push(...modeSpecific.acquisition.detection);
    }

    if (modeRegex.sealing && new RegExp(modeRegex.sealing).test(failureMode)) {
      prevention.push(...modeSpecific.sealing.prevention);
      detection.push(...modeSpecific.sealing.detection);
    }

    if (modeRegex.connection && new RegExp(modeRegex.connection).test(failureMode)) {
      prevention.push(...modeSpecific.connection.prevention);
      detection.push(...modeSpecific.connection.detection);
    }

    return { prevention, detection };
  };

  /**
   * Composes RPN calculation, AP lookup, and optimization hint.
   */
  const analyzeRisk = (
    s: number,
    o: number,
    d: number
  ): { rpn: number; ap: "H" | "M" | "L" | ""; hint: string } => {
    const rpn = s * o * d;
    const ap = calculateAP(s, o, d);
    const hint = ap ? getOptimizationHint(ap as "H" | "M" | "L") : "";
    return { rpn, ap, hint };
  };

  return {
    generateFailureModes,
    suggestFailureChain,
    getOptimizationHint,
    suggestMeasures,
    analyzeRisk,
  };
}
