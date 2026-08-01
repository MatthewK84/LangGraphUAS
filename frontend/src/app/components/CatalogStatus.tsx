import type { JSX } from "react";

interface CatalogStatusProps {
  readonly loading: boolean;
  readonly error: string | null;
}

export function CatalogStatus(props: CatalogStatusProps): JSX.Element | null {
  const { loading, error } = props;
  if (error !== null) {
    return (
      <p className="text-rose-400 text-xs mb-3" role="alert">
        Unable to load the platform catalog: {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p className="text-slate-400 text-xs mb-3">Loading platform catalog...</p>
    );
  }
  return null;
}
