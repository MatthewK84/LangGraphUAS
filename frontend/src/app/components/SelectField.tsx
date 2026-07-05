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

const SELECT_CLASS =
  "w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500";
const LABEL_CLASS =
  "block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1";

export function SelectField(props: SelectFieldProps): JSX.Element {
  const { id, label, value, options, onChange } = props;
  return (
    <div>
      <label htmlFor={id} className={LABEL_CLASS}>
        {label}
      </label>
      <select
        id={id}
        name={id}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className={SELECT_CLASS}
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
