/**
 * Class-name composition.
 *
 * The project deliberately avoids `clsx`/`tailwind-merge` (see `package.json`),
 * so this is the single shared helper every component uses instead of
 * hand-rolled template literals. Falsy values are dropped.
 */
export function cn(
  ...values: Array<string | false | null | undefined>
): string {
  return values.filter(Boolean).join(" ");
}
