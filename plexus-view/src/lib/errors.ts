/** The message of a thrown value, whether or not it is an Error. */
export const errorMessage = (e: unknown): string => (e instanceof Error ? e.message : String(e));
