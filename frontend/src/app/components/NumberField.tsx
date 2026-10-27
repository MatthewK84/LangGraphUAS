import type { JSX } from "react";

interface NumberFieldProps {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly placeholder?: string;
  readonly onChange: (value: string) => void;
}

export function NumberField(props: NumberFieldProps): JSX.Element {
  const { id, label, value, placeholder, onChange } = props;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-fg-secondary">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type="number"
        step="any"
        value={value}
        placeholder={placeholder ?? ""}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="field text-right tabular"
        required
      />
    </div>
  );
}
