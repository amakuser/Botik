export const selectorPriority = [
  "role",
  "label",
  "semantic-text",
  "data-testid",
] as const;

export function foundationSelector(testId: string): string {
  return `[data-testid="${testId}"]`;
}
