import type { JSX } from "react";

interface CatalogStatusProps {
  readonly loading: boolean;
  readonly error: string | null;
}

export function CatalogStatus(props: CatalogStatusProps): JSX.Element | null {
  const { loading, error } = props;
  if (error !== null) {
    return (
      <p
        className="border-l-2 border-critical bg-critical-tint px-2 py-1 text-sm text-fg"
        role="alert"
      >
        Unable to load the platform catalog: {error}
      </p>
    );
  }
  if (loading) {
    return <p className="text-sm text-fg-muted">Loading platform catalog...</p>;
  }
  return null;
}
