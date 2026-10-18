/** A bullet list of plain strings (notes, honesty items, headline). Items are unique, so they are their own keys. */
export function StringList({
  items,
  className,
  ariaLabel,
}: {
  items: readonly string[];
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <ul className={className} aria-label={ariaLabel}>
      {items.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ul>
  );
}
