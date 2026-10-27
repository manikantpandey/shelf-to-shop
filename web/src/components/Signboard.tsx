/** The shop's painted name board: the one bold element of the app (docs/design-plan.md, section 2). */
export function Signboard({ name, compact = false, as: Tag = "h1" }: { name: string; compact?: boolean; as?: "h1" | "p" }) {
  return (
    <div className={`signboard${compact ? " compact" : ""}`}>
      <Tag className="signboard-name">{name}</Tag>
    </div>
  );
}
