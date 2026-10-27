import type { JSX } from "react";

export interface SelectOption {
  readonly value: string;
  readonly label: string;
}

interface SelectFieldProps {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly options: readonly SelectOption[];
  readonly onChange: (value: string) => void;
}

export function SelectField(props: SelectFieldProps): JSX.Element {
  const { id, label, value, options, onChange } = props;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-fg-secondary">
        {label}
      </label>
      <select
        id={id}
        name={id}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="field"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
