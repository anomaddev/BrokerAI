type ParamReadOnlyRowProps = {
  label: string;
  value: string;
  required?: boolean;
  id?: string;
};

export default function ParamReadOnlyRow({ label, value, required, id }: ParamReadOnlyRowProps) {
  return (
    <div className="param-control param-control--readonly">
      <span className="param-control-label" id={id}>
        {label}
        {required ? <span className="param-control-required">Required</span> : null}
      </span>
      <span className="param-control-value param-control-value--locked" aria-labelledby={id}>
        {value}
      </span>
    </div>
  );
}
