export function parseKeywordTermsInput(input: string): string[] {
  return input
    .split(/[\n,，、;；]+/)
    .map((term) => term.trim())
    .filter(Boolean);
}
