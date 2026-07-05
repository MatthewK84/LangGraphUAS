import type { JSX } from "react";

interface NumberFieldProps {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly placeholder?: string;
  readonly onChange: (value: string) => void;
}

const FIELD_CLASS =
  "w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none focus:border-blue-500";
const LABEL_CLASS =
  "block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1";

export function NumberField(props: NumberFieldProps): JSX.Element {
  const { id, label, value, placeholder, onChange } = props;
  return (
    <div>
      <label htmlFor={id} className={LABEL_CLASS}>
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
        className={FIELD_CLASS}
        required
      />
    </div>
  );
}
