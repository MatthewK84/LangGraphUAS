import type { JSX } from "react";

/** The id of the review panel's heading, where the skip link lands. */
export const SIGN_OFF_ID = "sign-off";

/**
 * The first stop after Analyze, before every figure's provenance button:
 * hidden until it has keyboard focus, then shown in the assessment header.
 * Focus moves by hand as well as by the fragment, so it lands on the heading
 * in every browser and the next Tab reaches the review card's first control.
 */
export function SkipToSignOff(): JSX.Element {
  return (
    <a
      href={`#${SIGN_OFF_ID}`}
      className="sr-only text-sm text-accent underline focus:not-sr-only"
      onClick={(event) => {
        event.preventDefault();
        document.getElementById(SIGN_OFF_ID)?.focus();
      }}
    >
      Skip to sign-off
    </a>
  );
}
