import type { JSX } from "react";

export function LegalFooter(): JSX.Element {
  return (
    <footer className="flex h-row shrink-0 items-center border-t border-line bg-panel px-3 text-xs text-fg-muted">
      MIT license. Blue UAS names in the reference data are not an endorsement.
      This is not a flight authorization.
    </footer>
  );
}
