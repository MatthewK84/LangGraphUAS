// Whether the operator may sign the assessment in front of them, and if not,
// the one reason to show beside the disabled confirm.

export interface ConfirmState {
  readonly busy: boolean;
  readonly advisory: boolean;
  readonly understood: boolean;
  /** The inputs hash the review card displayed when it was opened. */
  readonly reviewedHash: string;
  /** The inputs hash of the assessment the page now holds. */
  readonly currentHash: string;
  /** Any mission input changed after this assessment was computed. */
  readonly inputsEdited: boolean;
}

/** Ordered so the reason shown is the one the operator must act on first. */
export function confirmBlocker(state: ConfirmState): string | null {
  if (state.inputsEdited) {
    return "Inputs edited since this assessment. Analyze again before signing.";
  }
  if (state.reviewedHash !== state.currentHash) {
    return "The assessment changed after it was shown. Review it again.";
  }
  if (state.busy) {
    return "Waiting for the backend.";
  }
  if (state.advisory && !state.understood) {
    return "Tick the advisory acknowledgement to sign.";
  }
  return null;
}
