/**
 * Defines the possible variants for tags/badges.
 * These should align with the variants defined in the Badge component (e.g., using cva).
 * Based on src/components/ui/index.tsx badgeVariants.
 */
export type TagVariant = 'default' | 'secondary' | 'success' | 'warning' | 'error' | 'outline';

// A predefined map for specific tags to variants.
// Tags are converted to lowercase for case-insensitive matching.
const specificTagToVariantMap: Record<string, TagVariant> = {
  "urgent": "error",
  "important": "warning",
  "bug": "error",
  "fix": "error",
  "work": "default",    // 'default' variant often uses primary colors
  "job": "default",
  "project": "default",
  "meeting": "default",
  "personal": "secondary",
  "home": "secondary",
  "chore": "outline",
  "task": "outline",
  "completed": "success",
  "done": "success",
  "finished": "success",
  "idea": "secondary",
  "research": "secondary",
  "learning": "secondary",
  // Add more specific mappings as needed by the application's domain
};

// A list of available variants to cycle through for unmapped tags.
// This ensures that any tag gets a style.
const availableCycleVariants: TagVariant[] = ['default', 'secondary', 'outline', 'warning', 'error', 'success'];

/**
 * Calculates a consistent style variant for a given tag string.
 * - First, checks a predefined map for common/specific tags.
 * - If not found, it uses a hashing-like approach to distribute other tags
 *   deterministically among the available variants.
 *
 * @param tag The tag string.
 * @returns A TagVariant string (e.g., 'default', 'success').
 */
export function getTagStyle(tag: string): TagVariant {
  if (!tag) {
    return 'default'; // Default for empty or null tags
  }

  const lowerCaseTag = tag.toLowerCase().trim();

  if (specificTagToVariantMap[lowerCaseTag]) {
    return specificTagToVariantMap[lowerCaseTag];
  }

  // For tags not in the specific map, cycle through available variants based on a simple hash
  // to ensure somewhat consistent styling for the same tag.
  let hash = 0;
  for (let i = 0; i < lowerCaseTag.length; i++) {
    const char = lowerCaseTag.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32bit integer
  }

  const index = Math.abs(hash) % availableCycleVariants.length;
  return availableCycleVariants[index];
}
